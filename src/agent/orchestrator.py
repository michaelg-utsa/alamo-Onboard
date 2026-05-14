"""Top-level agent orchestrator.

The orchestrator coordinates four pieces:

    1. The LLM client, which decides what to say or which tool to call.
    2. The toolbox, which executes those tool calls (retrieval, checklist
       updates, profile updates, and starting form workflows).
    3. The form workflow, which owns the conversation field-by-field once
       a signup has been started.
    4. The checklist tracker, which is the single source of truth for the
       persisted user state.

The orchestrator's contract is one method, ``handle_user_message``, that
takes a raw user string and returns the assistant's reply plus a flag
telling the UI to refresh the checklist sidebar.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.agent.llm_client import LLMClient
from src.agent.prompts import SYSTEM_PROMPT, TOOL_DEFINITIONS
from src.agent.tools import ToolBox
from src.checklist.tracker import ChecklistTracker
from src.forms.schemas import load_schemas
from src.forms.workflow import FormWorkflow, WorkflowState
from src.indexer.retriever import HybridRetriever
from src.utils.logging_utils import get_logger, set_request_id

logger = get_logger(__name__)

MAX_TOOL_HOPS = 4


@dataclass
class AgentReply:
    """One assistant turn."""

    text: str
    checklist_changed: bool = False


class AlamoAgent:
    """The conversational entry point used by the UI."""

    def __init__(
        self,
        retriever: HybridRetriever | None = None,
        tracker: ChecklistTracker | None = None,
        llm: LLMClient | None = None,
    ):
        self.retriever = retriever or HybridRetriever()
        if not self.retriever.load():
            logger.info("no on-disk index found; building from SA Utilities pipeline output")
            self.retriever.build_from_sa_utilities()
        self.tracker = tracker or ChecklistTracker()
        self.llm = llm or LLMClient()
        self.toolbox = ToolBox(self.retriever, self.tracker)
        self.schemas = load_schemas()
        self._pending_workflow: str | None = None
        self._restore_workflow_if_any()

    def _restore_workflow_if_any(self) -> None:
        """Reload an in-progress workflow from persisted state."""
        wf_state = self.tracker.state.active_workflow
        self.workflow: FormWorkflow | None = None
        if not wf_state:
            return
        sid = wf_state.get("service_id")
        for schema in self.schemas.values():
            if schema.service_id == sid:
                self.workflow = FormWorkflow(schema, WorkflowState.from_dict(wf_state))
                return

    # Main entry point
    def handle_user_message(self, user_text: str) -> AgentReply:
        import uuid

        set_request_id(uuid.uuid4().hex[:8])
        logger.info("user message received, len=%d", len(user_text or ""))

        text = (user_text or "").strip()
        if not text:
            return AgentReply(text="Tell me what you'd like to set up next.")

        self.tracker.append_history("user", text)

        # Pending-workflow confirmation: if the LLM staged a workflow on
        # the previous turn, the user's next reply decides whether to
        # actually enter it.
        if self._pending_workflow is not None:
            import re

            normalized = re.sub(r"[^a-z]", "", text.lower())
            if normalized in (
                "yes",
                "y",
                "yeah",
                "yep",
                "sure",
                "ok",
                "okay",
                "begin",
                "start",
                "go",
            ):
                reply = self._commit_pending_workflow()
                self.tracker.append_history("assistant", reply.text)
                return reply
            # Anything else: discard the staged workflow and let the
            # message flow through normal handling.
            self._pending_workflow = None
            reply = AgentReply(text="No problem! Feel free to ask your question.")
            self.tracker.append_history("assistant", reply.text)
            return reply

        # Checklist display is always handled directly — never routed through the LLM.
        if text.lower().strip() in ("show checklist", "show my checklist", "checklist"):
            reply = AgentReply(text=self.tracker.render_checklist())
            self.tracker.append_history("assistant", reply.text)
            return reply

        # Resume a previously paused workflow if the user asks for it.
        if self.workflow is None and self._looks_like_resume(text):
            wf_state = self.tracker.state.active_workflow
            if wf_state:
                sid = wf_state.get("service_id", "your previous form")
                for schema in self.schemas.values():
                    if schema.service_id == wf_state.get("service_id"):
                        self.workflow = FormWorkflow(schema, WorkflowState.from_dict(wf_state))
                        msg = (
                            f"Resuming the {sid} signup. "
                            f"{self.workflow._next_prompt_or_summary()}"  # noqa: SLF001
                        )
                        self.tracker.append_history("assistant", msg)
                        return AgentReply(text=msg)

        # Cancel a paused (detached) workflow — workflow is None but
        # active_workflow is still set, so the normal cancel handler inside
        # _handle_workflow_input never fires.  Catch it here so the user
        # gets a clean idle state instead of a confused LLM reply.
        if self.workflow is None and text.lower().strip() in ("cancel", "abort"):
            if self.tracker.state.active_workflow:
                sid = (self.tracker.state.active_workflow or {}).get("service_id", "the form")
                self.tracker.set_active_workflow(None)
                reply = AgentReply(
                    text=(
                        f"Cancelled the {sid} signup. Nothing was saved. "
                        "The checklist still shows it as pending; just say the word "
                        "when you'd like to start it again."
                    ),
                    checklist_changed=True,
                )
                self.tracker.append_history("assistant", reply.text)
                return reply

        # Active form workflow takes priority
        if self.workflow is not None and not self.workflow.is_complete():
            reply = self._handle_workflow_input(text)
            self.tracker.append_history("assistant", reply.text)
            return reply

        # If a workflow is sitting on its summary, accept summary commands
        if self.workflow is not None and self.workflow.is_complete():
            summary_reply = self._handle_workflow_summary(text)
            if summary_reply is not None:
                self.tracker.append_history("assistant", summary_reply.text)
                return summary_reply

        # Otherwise, run the LLM with tools
        reply = self._llm_turn(text)
        self.tracker.append_history("assistant", reply.text)
        return reply

    def _looks_like_resume(self, text: str) -> bool:
        """Match phrases like 'resume saws', 'resume signup', 'continue form'."""
        lowered = text.lower().strip()
        for verb in ("resume", "continue", "pick up", "go back"):
            if lowered == verb or lowered.startswith(verb + " "):
                return True
        return False

    # Form-workflow input
    _GREETINGS = (
        "hi",
        "hello",
        "hey",
        "yo",
        "howdy",
        "good morning",
        "good afternoon",
        "good evening",
        "how are you",
        "how's it going",
        "what's up",
        "whats up",
        "thanks",
        "thank you",
        "ok",
        "okay",
    )
    # Phrases that are clearly directed at the agent, not answering a field.
    _COMMAND_PREFIXES = (
        "show ",
        "what ",
        "what'",
        "how ",
        "tell me",
        "explain",
        "help",
        "resume ",
        "cancel ",
        "start ",
        "sign me",
    )

    def _looks_off_topic(self, text: str) -> bool:
        """Heuristic: does this user message look like something other than a
        form-field answer?

        We use this during an active workflow to avoid silently treating a
        question or greeting as a literal value for the current field.
        """
        lowered = text.lower().strip()
        if not lowered:
            return False
        # Any explicit pause command.
        if lowered in ("pause", "wait", "hold on", "stop"):
            return True
        # Direct question.
        if lowered.endswith("?"):
            return True
        # Common greetings / small talk.
        if any(
            lowered == g or lowered.startswith(g + " ") or lowered.startswith(g + ",")
            for g in self._GREETINGS
        ):
            return True
        # Agent-directed commands that are never valid field values.
        if any(lowered.startswith(p) for p in self._COMMAND_PREFIXES):
            return True
        return False

    def _handle_workflow_input(self, text: str) -> AgentReply:
        assert self.workflow is not None
        lower = text.lower().strip()

        # Keep all remaining pre-filled values at once
        if lower == "keep all":
            msg = self.workflow.keep_all()
            self.tracker.set_active_workflow(self.workflow.state.to_dict())
            return AgentReply(text=msg)

        # Undo: step back one field
        if lower in ("undo", "go back", "back"):
            msg = self.workflow.undo()
            self.tracker.set_active_workflow(self.workflow.state.to_dict())
            return AgentReply(text=msg)

        # Let checklist queries work even mid-workflow
        if lower in ("show checklist", "show my checklist", "checklist"):
            field_name = (
                self.workflow.current_field.name if self.workflow.current_field else "(summary)"
            )
            return AgentReply(
                text=(
                    f"{self.tracker.render_checklist()}\n\n"
                    f"_Still mid-signup for **{self.workflow.schema.title}** on `{field_name}`. "
                    f"Say `pause` to step away or `cancel` to quit._"
                )
            )

        # Hard exits
        if lower in ("cancel", "abort", "quit form", "quit"):
            sid = self.workflow.schema.service_id
            self.workflow = None
            self.tracker.set_active_workflow(None)
            return AgentReply(
                text=(
                    f"Cancelled the {sid} signup. Nothing was saved. "
                    "The checklist still shows it as pending; just say the word "
                    "when you'd like to start it again."
                ),
                checklist_changed=True,
            )

        # Soft pause: keep workflow state on disk but step out of guided mode
        # so the user can ask something else. They can resume by saying so.
        if lower in ("pause", "wait", "hold on", "stop"):
            sid = self.workflow.schema.service_id
            field_name = (
                self.workflow.current_field.name if self.workflow.current_field else "summary"
            )
            self.workflow = None  # detach from the agent for now
            return AgentReply(
                text=(
                    f"Paused the {sid} signup at field `{field_name}`. Ask whatever "
                    f"you need; when you're ready, say 'resume {sid}' to pick up where "
                    f"we left off, or 'cancel' to discard the in-progress data."
                ),
            )

        # If the message clearly isn't a field answer, ask first instead of
        # accepting it as the value.
        if self._looks_off_topic(text):
            return AgentReply(
                text=(
                    f"We're mid-signup for **{self.workflow.schema.title}**. "
                    f"Reply `pause` to step away and ask questions (progress is saved), "
                    f"or `cancel` to quit the form entirely."
                ),
            )

        advanced, message = self.workflow.submit_value(text)
        # Persist mid-flight state
        self.tracker.set_active_workflow(self.workflow.state.to_dict())
        return AgentReply(text=message)

    def _handle_workflow_summary(self, text: str) -> AgentReply | None:
        assert self.workflow is not None
        lowered = text.lower().strip()
        if lowered in ("undo", "back", "go back"):
            last_field = self.workflow.schema.fields[-1]
            reply = self.workflow.edit_field(last_field.name)
            self.tracker.set_active_workflow(self.workflow.state.to_dict())
            return AgentReply(text=f"Went back. {reply}")
        if lowered == "submit":
            sid = self.workflow.schema.service_id
            new_profile = self.workflow.commit(self.tracker.state.profile)
            self.tracker.update_profile(new_profile)
            self.tracker.set_status(sid, "completed", notes="Submitted via AlamoOnboard prototype.")
            self.tracker.set_active_workflow(None)
            completion = self.workflow.schema.completion_message
            self.workflow = None
            return AgentReply(
                text=(
                    f"Marked **{sid}** as completed on your checklist.\n\n"
                    f"{completion}\n\n"
                    "Reminder: this prototype does not actually transmit your form to the "
                    "provider; use the listed submit URL or phone number to finalize."
                ),
                checklist_changed=True,
            )
        if lowered.startswith("edit "):
            field_name = text[5:].strip()
            return AgentReply(text=self.workflow.edit_field(field_name))
        if lowered in ("cancel", "abort"):
            self.workflow = None
            self.tracker.set_active_workflow(None)
            return AgentReply(
                text="Cancelled. Nothing was submitted; the service is still pending.",
                checklist_changed=True,
            )
        return None  # fall through to LLM

    # LLM turn with tool dispatch
    def _llm_turn(self, text: str) -> AgentReply:
        messages = self._build_messages(text)
        checklist_changed = False

        for _hop in range(MAX_TOOL_HOPS):
            result = self.llm.chat(messages, tools=TOOL_DEFINITIONS)
            tool_calls = result.get("tool_calls") or []
            if not tool_calls:
                content = result.get("content") or ""
                if not content.strip():
                    content = "Could you tell me a bit more about what you'd like to do?"
                return AgentReply(text=content, checklist_changed=checklist_changed)

            # Append the assistant tool-request and each tool result
            messages.append(
                {
                    "role": "assistant",
                    "content": result.get("content") or "",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": _to_json(tc["arguments"]),
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                tool_out = self.toolbox.call(tc["name"], tc["arguments"] or {})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_out.get("content", ""),
                    }
                )
                if tool_out.get("checklist_changed"):
                    checklist_changed = True
                if tool_out.get("start_workflow"):
                    sid = tool_out["start_workflow"]
                    msg = self._begin_workflow(sid)
                    return AgentReply(text=msg, checklist_changed=True)

        return AgentReply(
            text="I tried a few tool calls but couldn't reach a final answer. "
            "Could you rephrase the question?",
            checklist_changed=checklist_changed,
        )

    # Workflow lifecycle helpers
    def _begin_workflow(self, service_id: str) -> str:
        """Stage a workflow and ask the user for explicit confirmation.

        The LLM may decide that the user wants to sign up, but starting
        the workflow locks them into a 14-field guided flow. We require
        an explicit "yes" before committing them to it.
        """
        schema = next((s for s in self.schemas.values() if s.service_id == service_id), None)
        if schema is None:
            return f"I don't have a workflow defined for service '{service_id}'."

        self._pending_workflow = service_id
        return (
            f"Heads up: the **{schema.title}** signup is a step-by-step flow with "
            f"{len(schema.fields)} fields. Once we start, you'll answer them one at a "
            f"time until you submit or cancel.\n\n"
            f"Reply **`yes`** to begin, or anything else to keep just chatting."
        )

    def _commit_pending_workflow(self) -> AgentReply:
        """Actually start the workflow that was previously staged."""
        sid = self._pending_workflow
        self._pending_workflow = None
        if sid is None:
            return AgentReply(text="I lost track of which workflow to start.")
        schema = next((s for s in self.schemas.values() if s.service_id == sid), None)
        if schema is None:
            return AgentReply(text="I lost track of which workflow to start.")
        self.workflow = FormWorkflow(schema)
        opener = self.workflow.start(self.tracker.state.profile)
        self.tracker.set_active_workflow(self.workflow.state.to_dict())
        self.tracker.set_status(sid, "in_progress")
        return AgentReply(text=opener, checklist_changed=True)

    # Message construction
    def _build_messages(self, current_user_text: str) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Provide a tiny snapshot of the user's profile and checklist so the
        # model can ground its answers without a tool call for trivial cases.
        msgs.append(
            {
                "role": "system",
                "content": (
                    "Current user profile (may be partial):\n"
                    f"{self.tracker.state.profile}\n\n"
                    "Current checklist:\n"
                    f"{self.tracker.render_checklist()}"
                ),
            }
        )
        # Replay the last few turns of conversation history for short-term memory
        for turn in self.tracker.state.history[-12:]:
            role = turn["role"]
            if role not in ("user", "assistant"):
                continue
            msgs.append({"role": role, "content": turn["content"]})
        msgs.append({"role": "user", "content": current_user_text})
        return msgs


def _to_json(obj) -> str:
    import json

    try:
        return json.dumps(obj or {})
    except Exception:
        return "{}"
