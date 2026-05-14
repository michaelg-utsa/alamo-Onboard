"""Gradio chat interface with a live checklist sidebar.

The UI is intentionally simple: a chat panel on the left and a markdown
checklist + retrieved-source panel on the right. The agent backs the
chat so the sidebar updates whenever a tool call changes status.
"""

from __future__ import annotations

import gradio as gr

from config import banner
from src.agent.orchestrator import AlamoAgent
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


WELCOME = (
    "Welcome to **AlamoOnboard**, your San Antonio move-in concierge. "
    "I can answer questions about CPS Energy, SAWS, and City of San Antonio services, "
    "or walk you through signing up for any of them. Try:\n"
    "- *What's the deposit for SAWS water service?*\n"
    "- *Help me start CPS Energy at 123 Main St San Antonio TX 78205.*\n"
    "- *Show my checklist.*\n"
)

# LOADING_MSG = (                                       # loading message saying we are downloading embedding model
#     "⏳ **Getting AlamoOnboard ready...**\n\n"
#     "Downloading the sentence embedding model from Hugging Face "
#     "(`sentence-transformers/all-MiniLM-L6-v2`). "
#     "This model is used to search local knowledge about CPS Energy, SAWS, and City of San Antonio services. "
#     "It takes **30–60 seconds** on first run while the files are cached locally.\n\n"
#     "_The chat will become active automatically once loading is complete._"
# )

LOADING_MSG = (
    "⏳ **Getting AlamoOnboard ready...**\n\n"
    "Downloading everything we need to find you the most up-to-date "
    "local knowledge about CPS Energy, SAWS, and City of San Antonio services. "
    "It takes **30–60 seconds** on first run while the files are cached locally.\n\n"
    "_The chat will become active automatically once loading is complete._"
)


MAX_CMDS = 16

# Human-readable labels for command buttons.
# Keys are the exact command strings that get pasted into the chat input.
# Edit the values here to change what the buttons say.
COMMAND_LABELS: dict[str, str] = {
    "yes": "Yes",
    "no": "No",
    "keep": "Keep pre-filled value",
    "keep all": "Keep all remaining pre-filled values",
    "skip": "Skip this field (optional)",
    "undo": "Undo last answer",
    "pause": "Pause form to ask a question",
    "cancel": "Cancel & discard current form",
    "submit": "Submit form",
    "show my checklist": "Show my checklist",
    "start cps_energy": "Start CPS Energy signup",
    "start saws": "Start SAWS signup",
    "start cosa_solid_waste": "Start City of SA trash signup",
}


def build_app() -> gr.Blocks:
    """Construct the Gradio Blocks app."""

    # agent is initialized lazily inside app.load() so the UI renders
    # immediately with a loading message rather than blocking on startup.
    agent: AlamoAgent | None = None

    def _label_for(cmd: str) -> str:
        if cmd.startswith("start ") and agent is not None:
            sid = cmd[6:]
            item = agent.tracker.get_item(sid)
            base = COMMAND_LABELS.get(cmd, f"Start {sid.replace('_', ' ')}")
            if item and item.status in ("completed", "skipped"):
                return base.replace("Start ", "Restart ")
            return base
        if cmd in COMMAND_LABELS:
            return COMMAND_LABELS[cmd]
        if cmd.startswith("edit "):
            return "Edit: " + cmd[5:].replace("_", " ")
        if cmd.startswith("resume "):
            return "Resume " + cmd[7:].replace("_", " ")
        return cmd

    def _get_available_commands() -> list[str]:
        if agent is None:
            return []
        if agent._pending_workflow:
            return ["yes", "no"]
        if agent.workflow is not None:
            wf = agent.workflow
            if wf.is_complete():
                cmds = ["submit"]
                for f in wf.schema.fields:
                    cmds.append(f"edit {f.name}")
                cmds.append("cancel")
                return cmds
            field = wf.current_field
            cmds = []
            if field and wf.state.values.get(field.name) is not None:
                cmds.append("keep")
            if field and not field.required:
                cmds.append("skip")
            if any(
                wf.state.values.get(f.name) not in (None, "")
                for f in wf.schema.fields[wf.state.current_field_index :]
            ):
                cmds.append("keep all")
            if wf.state.current_field_index > 0:
                cmds.append("undo")
            cmds += ["pause", "cancel"]
            return cmds
        active = agent.tracker.state.active_workflow
        if active and active.get("service_id"):
            sid = active["service_id"]
            return [f"resume {sid}", "cancel"]
        return [
            "start cps_energy",
            "start saws",
            "start cosa_solid_waste",
            "show my checklist",
        ]

    def _compute_button_updates() -> list:
        cmds = _get_available_commands()
        return [
            (
                gr.update(value=_label_for(cmds[i]), visible=True)
                if i < len(cmds)
                else gr.update(value="", visible=False)
            )
            for i in range(MAX_CMDS)
        ]

    def respond(user_message: str, history: list[dict]):
        history = history or []
        if not user_message or agent is None:
            return history, ""
        history.append({"role": "user", "content": user_message})
        reply = agent.handle_user_message(user_message)
        history.append({"role": "assistant", "content": reply.text})
        return history, agent.tracker.render_checklist()

    def reset_state():
        if agent is None:
            return (
                [{"role": "assistant", "content": LOADING_MSG}],
                "",
                *[gr.update(visible=False)] * MAX_CMDS,
            )
        agent.tracker.reset()
        agent.workflow = None
        agent._pending_workflow = None
        return (
            [{"role": "assistant", "content": WELCOME}],
            agent.tracker.render_checklist(),
            *_compute_button_updates(),
        )

    with gr.Blocks(title="AlamoOnboard") as app:
        gr.Markdown("# 🏛️ AlamoOnboard\n*San Antonio utilities & city-services concierge*")
        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(
                    value=[{"role": "assistant", "content": LOADING_MSG}],
                    height=520,
                )
                with gr.Row():
                    msg = gr.Textbox(
                        placeholder="Loading model — please wait...",
                        scale=8,
                        show_label=False,
                        container=False,
                        interactive=False,
                    )
                    send = gr.Button("Send", scale=1, variant="primary", interactive=False)
                    clear = gr.Button("Reset", scale=1, interactive=False)
                    confirm_reset = gr.Button(
                        "⚠️ Confirm Reset", scale=1, visible=False, variant="stop"
                    )

            with gr.Column(scale=2):
                gr.Markdown("### Status")
                checklist_md = gr.Markdown(value="_Loading..._")
                gr.Markdown("---\n### Available Commands")
                cmd_btns = [gr.Button("", visible=False, size="sm") for _ in range(MAX_CMDS)]
                gr.Markdown("_Click to paste into chat, then press Enter._")
                gr.Markdown(
                    "_The checklist is persisted to `output/user_state.json`. "
                    "Reset clears your profile and progress for a fresh demo._"
                )

        # def _send(user_message, history):
        #     history = history or []
        #     if not user_message or agent is None:
        #         yield ("", history, agent.tracker.render_checklist() if agent else "", *_compute_button_updates())
        #         return
        #     history = history + [{"role": "user", "content": user_message}]
        #     yield ("", history, agent.tracker.render_checklist(), *_compute_button_updates())
        #     reply = agent.handle_user_message(user_message)
        #     history = history + [{"role": "assistant", "content": reply.text}]
        #     yield ("", history, agent.tracker.render_checklist(), *_compute_button_updates())

        def _send(user_message, history):
            history = history or []
            if not user_message or agent is None:
                yield (
                    "",
                    history,
                    agent.tracker.render_checklist() if agent else "",
                    *_compute_button_updates(),
                )
                return
            history = history + [{"role": "user", "content": user_message}]
            # Show user message immediately with a thinking indicator
            thinking_history = history + [{"role": "assistant", "content": "⏳ _Thinking..._"}]
            yield (
                "",
                thinking_history,
                agent.tracker.render_checklist(),
                *_compute_button_updates(),
            )
            reply = agent.handle_user_message(user_message)
            history = history + [{"role": "assistant", "content": reply.text}]
            yield ("", history, agent.tracker.render_checklist(), *_compute_button_updates())

        def _on_load():
            nonlocal agent
            agent = AlamoAgent()
            # Force the lazy embedder to download/load now so the first query is instant.
            agent.retriever.embedder.encode(["warmup"])
            logger.info(banner())
            return (
                [{"role": "assistant", "content": WELCOME}],
                agent.tracker.render_checklist(),
                gr.update(
                    placeholder="Ask a question, request a signup, or say 'show my checklist'.",
                    interactive=True,
                ),
                gr.update(interactive=True),
                gr.update(interactive=True),
                *_compute_button_updates(),
            )

        for i in range(MAX_CMDS):

            def make_handler(idx):
                def handler():
                    cmds = _get_available_commands()
                    return cmds[idx] if idx < len(cmds) else ""

                return handler

            cmd_btns[i].click(fn=make_handler(i), inputs=[], outputs=[msg])

        app.load(_on_load, inputs=[], outputs=[chatbot, checklist_md, msg, send, clear, *cmd_btns])
        send.click(_send, [msg, chatbot], [msg, chatbot, checklist_md, *cmd_btns], api_name="chat")
        msg.submit(_send, [msg, chatbot], [msg, chatbot, checklist_md, *cmd_btns])
        clear.click(fn=lambda: gr.update(visible=True), inputs=[], outputs=[confirm_reset])
        confirm_reset.click(
            fn=reset_state, inputs=[], outputs=[chatbot, checklist_md, *cmd_btns]
        ).then(fn=lambda: gr.update(visible=False), inputs=[], outputs=[confirm_reset])

    return app


def main() -> None:
    import os

    app = build_app()
    app.launch(
        server_name=os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", "7860")),
        inbrowser=False,
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    main()
