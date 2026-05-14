"""User checklist tracker.

Tracks which services the user has completed, which are in progress,
and which are still pending. Backed by a single JSON file on disk so
state survives between sessions.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config import USER_STATE_PATH
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# The default checklist for someone moving into a single-family home or
# apartment inside San Antonio city limits.
DEFAULT_CHECKLIST: list[dict[str, Any]] = [
    {
        "service_id": "cps_energy",
        "name": "CPS Energy electric & gas",
        "status": "pending",
        "lead_time_days": 2,
        "form_id": "cps_energy_start",
    },
    {
        "service_id": "saws",
        "name": "SAWS water & sewer",
        "status": "pending",
        "lead_time_days": 5,
        "form_id": "saws_start",
    },
    {
        "service_id": "cosa_solid_waste",
        "name": "Trash, recycling & organics",
        "status": "pending",
        "lead_time_days": 0,
        "form_id": "cosa_solid_waste",
    },
]


@dataclass
class ChecklistItem:
    """A single line on the user's move-in checklist."""

    service_id: str
    name: str
    status: str  # pending | in_progress | completed | skipped
    lead_time_days: int
    form_id: str
    completed_at: str | None = None
    notes: str = ""


@dataclass
class UserState:
    """The full persisted state for one user."""

    profile: dict[str, Any] = field(default_factory=dict)
    checklist: list[ChecklistItem] = field(default_factory=list)
    active_workflow: dict | None = None  # serialized WorkflowState
    history: list[dict] = field(default_factory=list)  # chat transcript

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "checklist": [asdict(c) for c in self.checklist],
            "active_workflow": self.active_workflow,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, d: dict) -> UserState:
        return cls(
            profile=d.get("profile", {}),
            checklist=[ChecklistItem(**c) for c in d.get("checklist", [])],
            active_workflow=d.get("active_workflow"),
            history=d.get("history", []),
        )

    @classmethod
    def fresh(cls) -> UserState:
        return cls(
            profile={"user": {}},
            checklist=[ChecklistItem(**item) for item in DEFAULT_CHECKLIST],
            active_workflow=None,
            history=[],
        )


class ChecklistTracker:
    """Load/save user state and run convenience updates against the checklist."""

    def __init__(self, path: Path = USER_STATE_PATH):
        self.path = Path(path)
        self.state: UserState = self._load()

    # io
    def _load(self) -> UserState:
        if self.path.exists():
            try:
                return UserState.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning("could not read user state %s: %s", self.path, exc)
        return UserState.fresh()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset(self) -> None:
        self.state = UserState.fresh()
        self.save()

    # checklist ops
    def get_item(self, service_id: str) -> ChecklistItem | None:
        for item in self.state.checklist:
            if item.service_id == service_id:
                return item
        return None

    def set_status(self, service_id: str, status: str, notes: str = "") -> None:
        item = self.get_item(service_id)
        if item is None:
            return
        item.status = status
        if status == "completed":
            item.completed_at = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")
        if notes:
            item.notes = notes
        self.save()

    def render_checklist(self) -> str:
        symbol = {
            "pending": "\n[ ]",
            "in_progress": "\n[~]",
            "completed": "\n[x]",
            "skipped": "\n[-]",
        }
        lines = ["### Move-in checklist", ""]
        for item in self.state.checklist:
            sym = symbol.get(item.status, "[?]")
            line = f"{sym} **{item.name}** ({item.status})"
            if item.completed_at:
                line += f" - completed {item.completed_at}"
            lines.append(line)
            if item.notes:
                lines.append(f"    _{item.notes}_")
        lines.append("")
        return "\n".join(lines)

    # profile ops
    def update_profile(self, profile: dict) -> None:
        self.state.profile = profile
        self.save()

    # workflow ops
    def set_active_workflow(self, workflow_state: dict | None) -> None:
        self.state.active_workflow = workflow_state
        self.save()

    # history
    def append_history(self, role: str, content: str) -> None:
        self.state.history.append(
            {
                "role": role,
                "content": content,
                "ts": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
            }
        )
        # Cap history at 200 messages to keep state file small
        if len(self.state.history) > 200:
            self.state.history = self.state.history[-200:]
        self.save()
