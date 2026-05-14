"""Unit tests for src/agent/tools.py and additional validators coverage."""

from __future__ import annotations

import datetime
import os
from unittest.mock import MagicMock

os.environ.setdefault("ALAMO_DEMO_MODE", "1")
os.environ.setdefault("ALAMO_LLM_API_KEY", "")


# ---------------------------------------------------------------------------
# ToolBox
# ---------------------------------------------------------------------------


class TestToolBox:
    def _make_toolbox(self):
        from src.agent.tools import ToolBox
        from src.indexer.retriever import RetrievedPassage

        mock_retriever = MagicMock()
        mock_retriever.search.return_value = [
            RetrievedPassage(
                text="CPS requires a $200 deposit.",
                title="Deposit Policy",
                source="CPS Energy",
                url="https://cpsenergy.com",
                score=0.9,
            )
        ]
        mock_tracker = MagicMock()
        mock_tracker.render_checklist.return_value = "[ ] CPS Energy\n[ ] SAWS"
        mock_tracker.state.profile = {}
        return ToolBox(retriever=mock_retriever, tracker=mock_tracker)

    def test_unknown_tool_returns_error(self):
        tb = self._make_toolbox()
        result = tb.call("nonexistent_tool", {})
        assert "No tool named" in result["content"]

    def test_bad_arguments_returns_error(self):
        tb = self._make_toolbox()
        # _tool_mark_service_status requires service_id and status
        result = tb.call("mark_service_status", {"wrong_arg": "x"})
        assert "Bad arguments" in result["content"]

    def test_retrieve_knowledge_returns_content(self):
        tb = self._make_toolbox()
        result = tb.call("retrieve_knowledge", {"query": "CPS deposit"})
        assert "content" in result
        assert result["content"]

    def test_retrieve_knowledge_includes_passages(self):
        tb = self._make_toolbox()
        result = tb.call("retrieve_knowledge", {"query": "CPS deposit"})
        assert "passages" in result
        assert len(result["passages"]) == 1
        assert result["passages"][0]["source"] == "CPS Energy"

    def test_show_checklist_returns_content(self):
        tb = self._make_toolbox()
        result = tb.call("show_checklist", {})
        assert "[ ]" in result["content"] or "CPS" in result["content"]

    def test_mark_service_status_completed(self):
        tb = self._make_toolbox()
        result = tb.call("mark_service_status", {"service_id": "cps_energy", "status": "completed"})
        assert "completed" in result["content"]
        assert result.get("checklist_changed") is True

    def test_mark_service_status_invalid_status(self):
        tb = self._make_toolbox()
        result = tb.call("mark_service_status", {"service_id": "cps_energy", "status": "flying"})
        assert "Unknown status" in result["content"]

    def test_start_form_workflow_returns_service_id(self):
        tb = self._make_toolbox()
        result = tb.call("start_form_workflow", {"service_id": "cps_energy"})
        assert "cps_energy" in result["content"]
        assert result.get("start_workflow") == "cps_energy"

    def test_update_profile_stores_value(self):
        tb = self._make_toolbox()
        tb.tracker.state.profile = {}
        result = tb.call("update_profile", {"field": "first_name", "value": "Alex"})
        assert "first_name" in result["content"]


# ---------------------------------------------------------------------------
# Additional validator coverage
# ---------------------------------------------------------------------------


class TestDateField:
    def test_iso_format_accepted(self):
        from src.forms.validators import date_field

        ok, cleaned, _ = date_field("2026-06-01")
        assert ok is True
        assert cleaned == "2026-06-01"

    def test_slash_format_accepted(self):
        from src.forms.validators import date_field

        ok, cleaned, _ = date_field("06/01/2026")
        assert ok is True

    def test_invalid_date_rejected(self):
        from src.forms.validators import date_field

        ok, _, err = date_field("not-a-date")
        assert ok is False
        assert err

    def test_empty_date_rejected(self):
        from src.forms.validators import date_field

        ok, _, err = date_field("")
        assert ok is False


class TestLeadTimeValidators:
    def test_lead_time_2bd_weekend_rejected(self):
        from src.forms.validators import validate

        # Find nearest upcoming Saturday
        today = datetime.date.today()
        days_until_sat = (5 - today.weekday()) % 7
        if days_until_sat < 3:
            days_until_sat += 7
        saturday = today + datetime.timedelta(days=days_until_sat)
        ok, _, err = validate("lead_time_2bd", saturday.isoformat())
        assert ok is False
        assert err

    def test_lead_time_2bd_far_future_accepted(self):
        from src.forms.validators import validate

        future = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()
        # Adjust if it's a weekend
        d = datetime.date.fromisoformat(future)
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        ok, _, _ = validate("lead_time_2bd", d.isoformat())
        assert ok is True

    def test_lead_time_5bd_far_future_accepted(self):
        from src.forms.validators import validate

        future = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()
        d = datetime.date.fromisoformat(future)
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        ok, _, _ = validate("lead_time_5bd", d.isoformat())
        assert ok is True


class TestCpsAccount:
    def test_empty_cps_account_passes(self):
        from src.forms.validators import validate

        ok, _, _ = validate("cps_account", "")
        assert ok is True  # optional field

    def test_valid_cps_account(self):
        from src.forms.validators import validate

        ok, _, _ = validate("cps_account", "1234567890")
        assert ok is True

    def test_too_short_cps_account(self):
        from src.forms.validators import validate

        ok, _, err = validate("cps_account", "123")
        assert ok is False


class TestSsnMasking:
    def test_ssn_masked_in_summary(self):
        from src.forms.prefill import field_summary
        from src.forms.schemas import FormField

        field = FormField(
            name="ssn_or_dl",
            label="SSN or Driver License",
            type="secret",
            required=True,
        )
        line = field_summary(field, "123-45-6789")
        # type=secret means the value should be masked
        assert "123-45-6789" not in line
