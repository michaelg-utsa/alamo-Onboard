"""Step-by-step form workflow.

The workflow walks the user through one form's fields one at a time,
runs validators, supports pre-fill, and produces a final summary at the
end. State is intentionally serializable so it can be saved to the user
state file and resumed across sessions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.forms.prefill import field_summary, prefill_form, update_profile_from_form
from src.forms.schemas import FormField, FormSchema
from src.forms.validators import validate
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class WorkflowState:
    """Serializable state for an in-progress form workflow."""

    service_id: str
    current_field_index: int = 0
    values: dict[str, Any] = field(default_factory=dict)
    completed: bool = False
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> WorkflowState:
        return cls(**d)


class FormWorkflow:
    """Drive a single form to completion."""

    def __init__(self, schema: FormSchema, state: WorkflowState | None = None):
        self.schema = schema
        self.state = state or WorkflowState(service_id=schema.service_id)

    # Lifecycle
    def start(self, profile: dict) -> str:
        """Initialize values from profile pre-fill and return the opening prompt."""
        prefilled = prefill_form(self.schema, profile)
        for k, v in prefilled.items():
            self.state.values.setdefault(k, v)
        return self._intro_message()

    def is_complete(self) -> bool:
        return self.state.completed

    # Per-field interaction
    @property
    def current_field(self) -> FormField | None:
        if self.state.current_field_index >= len(self.schema.fields):
            return None
        return self.schema.fields[self.state.current_field_index]

    def prompt_for_current_field(self) -> str:
        """Return the assistant-facing prompt for the next field needing input."""
        f = self.current_field
        if f is None:
            return self._summary_message()

        prefilled = self.state.values.get(f.name)
        prefilled_text = ""
        if prefilled not in (None, ""):
            if f.type == "secret":
                prefilled_text = " (a value is already on file - reply 'keep' to use it)"
            else:
                prefilled_text = f" (we have '{prefilled}' on file - reply 'keep' to use it)"

        line = f"**{f.label}**{prefilled_text}"
        if f.help:
            line += f"\n_{f.help}_"
        if f.options:
            numbered = "\n".join(f"  {i + 1}. {opt}" for i, opt in enumerate(f.options))
            line += "\nOptions:\n" + numbered
        if not f.required:
            line += "\n(Optional - reply 'skip' to leave blank.)"
        return line

    def submit_value(self, raw_value: str) -> tuple[bool, str]:
        """Submit the user's value for the current field.

        Returns a tuple ``(advanced, message)``. ``advanced`` is True when
        the workflow moved on to the next field; the message is the text
        to show the user (an error or the next prompt).
        """
        f = self.current_field
        if f is None:
            return True, self._summary_message()

        raw = (raw_value or "").strip()
        lowered = raw.lower()

        # Special commands
        if lowered == "keep" and self.state.values.get(f.name) not in (None, ""):
            self.state.current_field_index += 1
            return True, self._next_prompt_or_summary()

        if lowered == "skip":
            if f.required:
                return False, "That field is required - please provide a value."
            self.state.values[f.name] = ""
            self.state.current_field_index += 1
            return True, self._next_prompt_or_summary()

        # Type coercion for boolean fields
        value: Any = raw
        if f.type == "boolean":
            if lowered in ("y", "yes", "true", "1"):
                value = True
            elif lowered in ("n", "no", "false", "0", ""):
                value = False
            else:
                return False, "Please answer yes or no."

        # Handle select-style fields: accept index or text
        if f.type == "select":
            if value in f.options:
                pass
            elif raw.isdigit() and 1 <= int(raw) <= len(f.options):
                value = f.options[int(raw) - 1]
            else:
                return False, "Pick one of: " + ", ".join(f.options)

        # Run the named validator if any
        if f.validator and f.type not in ("boolean", "select"):
            ok, cleaned, err = validate(f.validator, str(value))
            if not ok:
                self.state.errors[f.name] = err
                return False, err
            value = cleaned

        # Required check
        if f.required and (value is None or value == ""):
            return False, "That field is required - please provide a value."

        self.state.values[f.name] = value
        self.state.errors.pop(f.name, None)
        self.state.current_field_index += 1
        return True, self._next_prompt_or_summary()

    # Summarization
    def _next_prompt_or_summary(self) -> str:
        if self.current_field is None:
            self.state.completed = True
            return self._summary_message()
        return self.prompt_for_current_field()

    def _intro_message(self) -> str:
        return (
            f"### {self.schema.title}\n\n"
            f"_Provider: {self.schema.provider}_\n\n"
            f"{self.schema.description}\n\n"
            f"I'll walk you through {len(self.schema.fields)} fields. "
            f"You can reply 'keep' to accept any pre-filled value, 'skip' to skip an "
            f"optional field, 'pause' to pause the form to ask a question or "
            f"try a different form, or 'undo' to go back to the previous form section.\n\n"
            f"---\n\n"
            f"{self.prompt_for_current_field()}"
        )

    def _summary_message(self) -> str:
        lines = [f"### Review: {self.schema.title}", ""]
        for f in self.schema.fields:
            lines.append(field_summary(f, self.state.values.get(f.name)))
        lines += [
            "",
            f"Submit URL: {self.schema.submit_url}",
            "",
            self.schema.completion_message,
            "",
            "Reply **submit** to mark this service complete, **edit <field>** to change a value, "
            "or **cancel** to abandon this workflow.",
        ]
        return "\n".join(lines)

    def keep_all(self) -> str:
        """Accept every remaining pre-filled value, stopping at the first unfilled field."""
        while self.current_field is not None:
            val = self.state.values.get(self.current_field.name)
            if val is not None and val != "":
                self.state.current_field_index += 1
            else:
                break
        return self._next_prompt_or_summary()

    def undo(self) -> str:
        """Step back one field, clearing its stored value so the user can re-enter it."""
        if self.state.current_field_index == 0:
            return "You're already on the first field — nothing to undo."
        self.state.current_field_index -= 1
        if self.state.completed:
            self.state.completed = False
        prev = self.schema.fields[self.state.current_field_index]
        self.state.values.pop(prev.name, None)
        self.state.errors.pop(prev.name, None)
        return f"Went back. {self.prompt_for_current_field()}"

    # Post-summary commands
    def edit_field(self, field_name: str) -> str:
        for i, f in enumerate(self.schema.fields):
            if f.name.lower() == field_name.lower() or f.label.lower() == field_name.lower():
                self.state.current_field_index = i
                self.state.completed = False
                return self.prompt_for_current_field()
        return f"No field named '{field_name}'. Try one of: " + ", ".join(
            f.name for f in self.schema.fields
        )

    def commit(self, profile: dict) -> dict:
        """Push values back into the profile and return the updated profile."""
        return update_profile_from_form(profile, self.schema, self.state.values)
