"""Tool implementations.

Each tool returns a dict with a ``content`` string the LLM can read and
optional structured fields the orchestrator uses to update UI state
(open a form workflow, refresh the checklist, etc.).
"""

from __future__ import annotations

from typing import Any

from src.agent.prompts import build_grounding_block
from src.checklist.tracker import ChecklistTracker
from src.indexer.retriever import HybridRetriever
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class ToolBox:
    """All tools the orchestrator exposes to the LLM."""

    def __init__(self, retriever: HybridRetriever, tracker: ChecklistTracker):
        self.retriever = retriever
        self.tracker = tracker

    # dispatch
    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        method = getattr(self, f"_tool_{name}", None)
        if method is None:
            return {"content": f"No tool named '{name}'."}
        try:
            return method(**arguments)
        except TypeError as exc:
            return {"content": f"Bad arguments to {name}: {exc}"}
        except Exception as exc:  # pragma: no cover
            logger.exception("tool %s failed", name)
            return {"content": f"Tool {name} raised an error: {exc}"}

    # knowledge retrieval
    def _tool_retrieve_knowledge(
        self,
        query: str,
        k: int = 5,
        source_filter: list[str] | None = None,
    ) -> dict[str, Any]:
        passages = self.retriever.search(query, k=k, source_filter=source_filter)
        return {
            "content": build_grounding_block(passages),
            "passages": [
                {
                    "title": p.title,
                    "source": p.source,
                    "url": p.url,
                    "text": p.text,
                    "score": p.score,
                }
                for p in passages
            ],
        }

    # checklist
    def _tool_show_checklist(self) -> dict[str, Any]:
        return {"content": self.tracker.render_checklist()}

    def _tool_mark_service_status(
        self, service_id: str, status: str, notes: str = ""
    ) -> dict[str, Any]:
        if status not in {"pending", "in_progress", "completed", "skipped"}:
            return {"content": f"Unknown status: {status}"}
        self.tracker.set_status(service_id, status, notes)
        return {
            "content": f"Marked {service_id} as {status}.",
            "checklist_changed": True,
        }

    # form workflow
    def _tool_start_form_workflow(self, service_id: str) -> dict[str, Any]:
        # The orchestrator handles the actual workflow object; this tool just
        # signals intent and returns a confirmation string.
        return {
            "content": f"Starting the signup workflow for {service_id}.",
            "start_workflow": service_id,
        }

    # profile
    def _tool_update_profile(self, field: str, value: str) -> dict[str, Any]:
        profile = self.tracker.state.profile
        profile.setdefault("user", {})
        profile["user"][field] = value
        self.tracker.update_profile(profile)
        return {"content": f"Saved {field} to your profile."}
