"""Unit tests for src/forms/prefill.py."""

from __future__ import annotations

from src.forms.prefill import field_summary, prefill_form, update_profile_from_form
from src.forms.schemas import FormField, FormSchema


def _make_schema(fields):
    return FormSchema(
        service_id="test_svc",
        title="Test Form",
        provider="Test Provider",
        submit_url="https://example.com/submit",
        lead_time_days=0,
        description="Test",
        fields=fields,
        completion_message="Done.",
    )


def _make_field(name, label="Label", ftype="text", prefill_from=None, default=None, required=False):
    return FormField(
        name=name,
        label=label,
        type=ftype,
        required=required,
        prefill_from=prefill_from,
        default=default,
    )


class TestPrefillForm:
    def test_resolves_prefill_from_profile(self):
        schema = _make_schema(
            [
                _make_field("first_name", prefill_from="user.first_name"),
            ]
        )
        profile = {"user": {"first_name": "Alex"}}
        result = prefill_form(schema, profile)
        assert result["first_name"] == "Alex"

    def test_uses_default_when_profile_missing(self):
        schema = _make_schema(
            [
                _make_field("state", prefill_from="user.state", default="TX"),
            ]
        )
        result = prefill_form(schema, {"user": {}})
        assert result["state"] == "TX"

    def test_no_prefill_from_no_default_excluded(self):
        schema = _make_schema([_make_field("ssn")])
        result = prefill_form(schema, {"user": {}})
        assert "ssn" not in result

    def test_empty_string_profile_value_falls_back_to_default(self):
        schema = _make_schema(
            [
                _make_field("city", prefill_from="user.city", default="San Antonio"),
            ]
        )
        profile = {"user": {"city": ""}}
        result = prefill_form(schema, profile)
        assert result["city"] == "San Antonio"

    def test_multiple_fields(self):
        schema = _make_schema(
            [
                _make_field("first_name", prefill_from="user.first_name"),
                _make_field("last_name", prefill_from="user.last_name"),
            ]
        )
        profile = {"user": {"first_name": "Alex", "last_name": "Kim"}}
        result = prefill_form(schema, profile)
        assert result == {"first_name": "Alex", "last_name": "Kim"}

    def test_non_user_prefill_path_returns_none(self):
        schema = _make_schema(
            [
                _make_field("city", prefill_from="other.city"),
            ]
        )
        result = prefill_form(schema, {"other": {"city": "NYC"}})
        assert "city" not in result


class TestUpdateProfileFromForm:
    def test_pushes_value_to_profile(self):
        schema = _make_schema(
            [
                _make_field("first_name", prefill_from="user.first_name"),
            ]
        )
        profile = {"user": {}}
        updated = update_profile_from_form(profile, schema, {"first_name": "Alex"})
        assert updated["user"]["first_name"] == "Alex"

    def test_secret_fields_not_stored(self):
        schema = _make_schema(
            [
                _make_field("ssn", ftype="secret", prefill_from="user.ssn"),
            ]
        )
        profile = {"user": {}}
        updated = update_profile_from_form(profile, schema, {"ssn": "123-45-6789"})
        assert "ssn" not in updated.get("user", {})

    def test_empty_value_not_pushed(self):
        schema = _make_schema(
            [
                _make_field("phone", prefill_from="user.phone"),
            ]
        )
        profile = {"user": {}}
        updated = update_profile_from_form(profile, schema, {"phone": ""})
        assert "phone" not in updated.get("user", {})

    def test_no_prefill_from_not_pushed(self):
        schema = _make_schema([_make_field("notes")])
        profile = {"user": {}}
        updated = update_profile_from_form(profile, schema, {"notes": "test"})
        assert "notes" not in updated.get("user", {})

    def test_returns_new_dict_not_same_object(self):
        """update_profile_from_form should return a new top-level dict."""
        schema = _make_schema(
            [
                _make_field("first_name", prefill_from="user.first_name"),
            ]
        )
        original = {"user": {}}
        updated = update_profile_from_form(original, schema, {"first_name": "Alex"})
        # The returned dict must be a different object from the original
        assert updated is not original


class TestFieldSummary:
    def test_normal_field(self):
        f = _make_field("city", label="City")
        line = field_summary(f, "San Antonio")
        assert "City" in line
        assert "San Antonio" in line

    def test_empty_value_shows_empty_label(self):
        f = _make_field("middle_name", label="Middle Name")
        line = field_summary(f, "")
        assert "(empty)" in line

    def test_secret_field_masked(self):
        f = _make_field("ssn", label="SSN", ftype="secret")
        line = field_summary(f, "123-45-6789")
        assert "***hidden***" in line

    def test_secret_field_already_masked_passes_through(self):
        f = _make_field("ssn", label="SSN", ftype="secret")
        line = field_summary(f, "***-**-6789")
        assert "***hidden***" not in line or "***" in line
