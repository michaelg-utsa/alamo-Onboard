"""Pre-fill logic.

When a user has already provided their name, address, etc. through one
form, the next form should suggest those values automatically. The
profile lives in the user state file and is the single source of truth
for cross-form pre-fill.
"""

from __future__ import annotations

from typing import Any

from src.forms.schemas import FormField, FormSchema


def _resolve_path(profile: dict, dotted_path: str) -> Any:
    """Resolve a dotted path like ``user.first_name`` against ``profile``.

    The path is rooted at ``profile`` itself, so the first segment ("user")
    is looked up in ``profile`` rather than skipped.
    """
    if not dotted_path:
        return None
    parts = dotted_path.split(".")
    if parts[0] != "user":
        return None
    cursor: Any = profile
    for part in parts:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def prefill_form(schema: FormSchema, profile: dict) -> dict[str, Any]:
    """Return a dict of {field_name: prefilled_value} for the given schema."""
    out: dict[str, Any] = {}
    for f in schema.fields:
        val = _resolve_path(profile, f.prefill_from) if f.prefill_from else None
        if val in (None, ""):
            val = f.default
        if val is not None:
            out[f.name] = val
    return out


def update_profile_from_form(profile: dict, schema: FormSchema, form_values: dict) -> dict:
    """Push form values back into the user profile so other forms can reuse them."""
    profile = dict(profile)
    profile.setdefault("user", {})
    for f in schema.fields:
        if not f.prefill_from or f.prefill_from == "" or not f.prefill_from.startswith("user."):
            continue
        # Don't store secret fields cross-form
        if f.type == "secret":
            continue
        key = f.prefill_from.split(".", 1)[1]
        if f.name in form_values and form_values[f.name] not in (None, ""):
            profile["user"][key] = form_values[f.name]
    return profile


def field_summary(field: FormField, value: Any) -> str:
    """Render a human-readable summary line for a single field."""
    display = "(empty)" if value in (None, "") else str(value)
    if field.type == "secret":
        display = display if display.startswith(("***", "DL ")) else "***hidden***"
    return f"  - {field.label}: {display}"
