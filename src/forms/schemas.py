"""Form schema loader and small data classes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import FORM_SCHEMAS_PATH


@dataclass
class FormField:
    """A single field in a service signup form."""

    name: str
    label: str
    type: str
    required: bool = False
    validator: str | None = None
    prefill_from: str | None = None
    default: Any = None
    options: list[str] = field(default_factory=list)
    help: str = ""


@dataclass
class FormSchema:
    """The full schema for one service signup form."""

    service_id: str
    title: str
    provider: str
    submit_url: str
    lead_time_days: int
    description: str
    fields: list[FormField]
    completion_message: str

    @classmethod
    def from_dict(cls, d: dict) -> FormSchema:
        fields = [
            FormField(
                name=f["name"],
                label=f["label"],
                type=f["type"],
                required=f.get("required", False),
                validator=f.get("validator"),
                prefill_from=f.get("prefill_from"),
                default=f.get("default"),
                options=f.get("options", []),
                help=f.get("help", ""),
            )
            for f in d["fields"]
        ]
        return cls(
            service_id=d["service_id"],
            title=d["title"],
            provider=d["provider"],
            submit_url=d["submit_url"],
            lead_time_days=d.get("lead_time_days", 0),
            description=d.get("description", ""),
            fields=fields,
            completion_message=d.get("completion_message", ""),
        )


def load_schemas(path: Path = FORM_SCHEMAS_PATH) -> dict[str, FormSchema]:
    """Load all form schemas from disk, keyed by service_id."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {sid: FormSchema.from_dict(s) for sid, s in raw["forms"].items()}
