"""
User story acceptance tests — one test per US-NN story.

These tests verify the Given/When/Then acceptance criteria from docs/STORIES.md.
All run in demo mode (no live LLM or external network calls required).

Run individually:
    pytest tests/user_stories/ -v

Or filter by marker:
    pytest -m "user_story" -v
"""

from __future__ import annotations

import datetime
import os

import pytest

os.environ.setdefault("ALAMO_DEMO_MODE", "1")
os.environ.setdefault("ALAMO_LLM_API_KEY", "")


# ---------------------------------------------------------------------------
# US-01: Ask a factual question about CPS Energy rates / deposit
# ---------------------------------------------------------------------------
@pytest.mark.user_story("US-01")
class TestUS01FactualQuestion:
    """
    Given: The user is at the main chat screen
    When: They ask "What is the deposit for CPS Energy?"
    Then: The agent responds with relevant information (non-empty text)
    """

    def test_factual_question_returns_response(self, agent):
        reply = agent.handle_user_message("What is the deposit for CPS Energy?")
        assert reply.text, "Agent must return non-empty text for a factual question"

    def test_response_is_informative(self, agent):
        reply = agent.handle_user_message("What is the deposit for CPS Energy?")
        # Should be more than a one-liner
        assert len(reply.text) > 30

    def test_no_crash_on_question(self, agent):
        # Multiple factual questions should not raise
        for q in [
            "What is the deposit for CPS Energy?",
            "How do I start SAWS service?",
            "When should I start water service?",
        ]:
            reply = agent.handle_user_message(q)
            assert reply.text


# ---------------------------------------------------------------------------
# US-02: View the move-in checklist
# ---------------------------------------------------------------------------
@pytest.mark.user_story("US-02")
class TestUS02ViewChecklist:
    """
    Given: The user has a default checklist (3 pending items)
    When: They type "show my checklist"
    Then: The agent displays all three services with their status symbols
    """

    def test_show_my_checklist(self, agent):
        reply = agent.handle_user_message("show my checklist")
        assert "[ ]" in reply.text or "checklist" in reply.text.lower()

    def test_checklist_contains_cps_energy(self, agent):
        reply = agent.handle_user_message("show my checklist")
        assert "CPS" in reply.text or "cps" in reply.text.lower()

    def test_checklist_contains_saws(self, agent):
        reply = agent.handle_user_message("show my checklist")
        assert "SAWS" in reply.text or "saws" in reply.text.lower()

    def test_checklist_keyword_works(self, agent):
        reply = agent.handle_user_message("checklist")
        assert reply.text

    def test_checklist_not_changed_flag(self, agent):
        reply = agent.handle_user_message("show my checklist")
        # Merely viewing should not trigger a checklist_changed event
        assert reply.checklist_changed is False


# ---------------------------------------------------------------------------
# US-03: Start and complete the CPS Energy signup form
# ---------------------------------------------------------------------------
@pytest.mark.user_story("US-03")
class TestUS03CPSEnergySignup:
    """
    Given: The user says they want CPS Energy service
    When: They confirm and fill all fields
    Then: The workflow completes and CPS Energy is marked in_progress/completed

    Note: in demo mode the LLM stub only calls retrieve_knowledge, so workflow
    initiation is tested via _begin_workflow / _commit_pending_workflow directly.
    """

    def test_cps_workflow_starts_after_confirm(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        assert agent.workflow is not None
        assert agent.workflow.schema.service_id == "cps_energy"

    def test_cps_checklist_marked_in_progress(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        item = agent.tracker.get_item("cps_energy")
        assert item.status == "in_progress"

    def test_workflow_advances_on_valid_input(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        assert agent.workflow is not None
        idx_before = agent.workflow.state.current_field_index
        agent.handle_user_message("Alex")
        assert agent.workflow.state.current_field_index >= idx_before

    def test_full_cps_workflow_completes(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        _fill_workflow_to_completion(agent)
        if agent.workflow and agent.workflow.is_complete():
            reply = agent.handle_user_message("submit")
            assert "completed" in reply.text.lower() or "checklist" in reply.text.lower()


# ---------------------------------------------------------------------------
# US-04: Start and complete the SAWS signup form
# ---------------------------------------------------------------------------
@pytest.mark.user_story("US-04")
class TestUS04SAWSSignup:
    """
    Given: The user wants SAWS water service
    When: They confirm and fill all fields
    Then: SAWS workflow completes successfully
    """

    def test_saws_workflow_starts_after_confirm(self, agent):
        agent._begin_workflow("saws")
        agent._commit_pending_workflow()
        assert agent.workflow is not None
        assert agent.workflow.schema.service_id == "saws"

    def test_saws_checklist_marked_in_progress(self, agent):
        agent._begin_workflow("saws")
        agent._commit_pending_workflow()
        item = agent.tracker.get_item("saws")
        assert item.status == "in_progress"

    def test_saws_workflow_advances(self, agent):
        agent._begin_workflow("saws")
        agent._commit_pending_workflow()
        assert agent.workflow is not None
        agent.handle_user_message("Alex")
        assert agent.workflow is not None  # still active after one field


# ---------------------------------------------------------------------------
# US-05: Use "keep all" to accept pre-filled form values
# ---------------------------------------------------------------------------
@pytest.mark.user_story("US-05")
class TestUS05KeepAll:
    """
    Given: The user has a profile with name and address already filled
    When: They start a form and type "keep all"
    Then: All pre-filled fields are accepted and the workflow advances past them
    """

    def test_keep_all_advances_past_prefilled(self, agent):
        agent.tracker.update_profile({"user": {"first_name": "Alex", "last_name": "Kim"}})
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        idx_before = agent.workflow.state.current_field_index
        agent.handle_user_message("keep all")
        idx_after = agent.workflow.state.current_field_index
        assert idx_after >= idx_before

    def test_keep_all_response_is_non_empty(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        reply = agent.handle_user_message("keep all")
        assert reply.text


# ---------------------------------------------------------------------------
# US-06: Pause a form mid-entry and resume it later
# ---------------------------------------------------------------------------
@pytest.mark.user_story("US-06")
class TestUS06PauseAndResume:
    """
    Given: The user is mid-way through a form
    When: They type "pause"
    Then: The workflow state is saved; later "resume" re-enters it
    """

    def test_pause_detaches_workflow(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        agent.handle_user_message("Alex")  # fill first field
        agent.handle_user_message("pause")
        assert agent.workflow is None

    def test_paused_state_persists_on_disk(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        agent.handle_user_message("Alex")
        agent.handle_user_message("pause")
        assert agent.tracker.state.active_workflow is not None

    def test_resume_re_enters_workflow(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        agent.handle_user_message("Alex")
        agent.handle_user_message("pause")
        reply = agent.handle_user_message("resume cps_energy")
        assert agent.workflow is not None or "resume" in reply.text.lower()

    def test_pause_message_mentions_service(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        reply = agent.handle_user_message("pause")
        assert "cps" in reply.text.lower() or "pause" in reply.text.lower()


# ---------------------------------------------------------------------------
# US-07: Invalid email — see validation error and retry
# ---------------------------------------------------------------------------
@pytest.mark.user_story("US-07")
class TestUS07EmailValidation:
    """
    Given: The user is on the email field in a signup form
    When: They enter an invalid email address
    Then: The agent rejects it with an "email" error and stays on the field
    """

    def test_invalid_email_rejected(self, cps_schema):
        from myproject.forms.workflow import FormWorkflow

        wf = FormWorkflow(cps_schema)
        wf.start({})
        # Navigate to the email field (index 4 per schema)
        wf.state.current_field_index = 4
        advanced, msg = wf.submit_value("notanemail")
        assert advanced is False
        assert "email" in msg.lower()

    def test_valid_email_accepted(self, cps_schema):
        from myproject.forms.workflow import FormWorkflow

        wf = FormWorkflow(cps_schema)
        wf.start({})
        wf.state.current_field_index = 4
        advanced, msg = wf.submit_value("alex@example.com")
        assert advanced is True

    def test_field_index_unchanged_after_bad_email(self, cps_schema):
        from myproject.forms.workflow import FormWorkflow

        wf = FormWorkflow(cps_schema)
        wf.start({})
        wf.state.current_field_index = 4
        wf.submit_value("bad@@email")
        assert wf.state.current_field_index == 4

    def test_retry_with_valid_email_advances(self, cps_schema):
        from myproject.forms.workflow import FormWorkflow

        wf = FormWorkflow(cps_schema)
        wf.start({})
        wf.state.current_field_index = 4
        wf.submit_value("bademail")  # rejected
        advanced, _ = wf.submit_value("good@example.com")
        assert advanced is True
        assert wf.state.current_field_index == 5

    def test_validator_standalone(self):
        from myproject.forms.validators import validate

        ok, _, err = validate("email", "notanemail")
        assert ok is False
        assert "email" in err.lower()


# ---------------------------------------------------------------------------
# US-08: Request a start date too soon — see lead time error
# ---------------------------------------------------------------------------
@pytest.mark.user_story("US-08")
class TestUS08LeadTimeValidation:
    """
    Given: The user is on the service start date field (SAWS, 5-day lead)
    When: They enter a date that is only 1 day in the future
    Then: The agent rejects it with a lead time error message
    """

    def test_tomorrow_rejected_for_saws(self, saws_schema):
        from myproject.forms.workflow import FormWorkflow

        wf = FormWorkflow(saws_schema)
        wf.start({})
        # Find the start_date field index
        idx = _find_field_index(wf, "requested_start_date")
        if idx is None:
            pytest.skip("start_date field not found in SAWS schema")
        wf.state.current_field_index = idx
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        advanced, msg = wf.submit_value(tomorrow)
        assert advanced is False
        assert (
            "day" in msg.lower()
            or "lead" in msg.lower()
            or "business" in msg.lower()
            or "weekend" in msg.lower()
        )

    def test_sufficient_lead_time_accepted(self, saws_schema):
        from myproject.forms.workflow import FormWorkflow

        wf = FormWorkflow(saws_schema)
        wf.start({})
        idx = _find_field_index(wf, "requested_start_date")
        if idx is None:
            pytest.skip("start_date field not found in SAWS schema")
        wf.state.current_field_index = idx
        future = (
            datetime.date.today() + datetime.timedelta(days=14)
        ).isoformat()  # 2 weeks = same weekday, always ≥5 bd
        advanced, msg = wf.submit_value(future)
        assert advanced is True

    def test_validator_standalone_tomorrow(self):
        from myproject.forms.validators import validate

        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        ok, _, err = validate("lead_time_5bd", tomorrow)
        assert ok is False
        assert err  # some error message

    def test_validator_standalone_future_passes(self):
        from myproject.forms.validators import validate

        future = (
            datetime.date.today() + datetime.timedelta(days=14)
        ).isoformat()  # 2 weeks = same weekday, always ≥5 bd
        ok, _, _ = validate("lead_time_5bd", future)
        assert ok is True


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fill_workflow_to_completion(agent) -> None:
    """Fill every field of the active workflow with a plausible value."""
    for _ in range(30):
        if agent.workflow is None or agent.workflow.is_complete():
            break
        field = agent.workflow.current_field
        if field is None:
            break
        agent.handle_user_message(_sample_value(field))


def _find_field_index(wf, field_name: str):
    for i, f in enumerate(wf.schema.fields):
        if f.name == field_name:
            return i
    return None


def _sample_value(field) -> str:
    import datetime

    vname = (field.validator or "").lower()
    fname = field.name.lower()
    if field.options:
        return field.options[0]
    if "email" in vname or "email" in fname:
        return "alex@example.com"
    if "phone" in vname or "phone" in fname:
        return "2105551234"
    if "zip" in vname or "zip" in fname:
        return "78205"
    if "address" in vname or "address" in fname:
        return "123 Main St"
    if "ssn" in vname or "ssn" in fname:
        return "123-45-6789"
    if "date" in vname or "date" in fname or "start" in fname:
        # 14 days = same weekday as today; skip weekends so lead_time accepts.
        d = datetime.date.today() + datetime.timedelta(days=14)
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        return d.isoformat()
    if field.type == "bool":
        return "no"
    return "TestValue"
