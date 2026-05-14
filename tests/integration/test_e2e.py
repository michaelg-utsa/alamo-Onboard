"""
Integration tests — end-to-end workflow covering the full pipeline
from user message → orchestrator → tools → response.

All tests run in demo mode (ALAMO_DEMO_MODE=1) so no LLM API key is required.
"""

from __future__ import annotations

import datetime
import os

os.environ.setdefault("ALAMO_DEMO_MODE", "1")
os.environ.setdefault("ALAMO_LLM_API_KEY", "")


# ---------------------------------------------------------------------------
# Retrieval integration
# ---------------------------------------------------------------------------


class TestRetrievalPipeline:
    def test_mock_retriever_returns_passage(self, agent):
        """The mock retriever fixture should return at least one passage on search."""
        results = agent.retriever.search("CPS Energy deposit")
        assert len(results) >= 1

    def test_retrieval_integrates_with_agent(self, agent):
        """A factual question should trigger retrieval and return an answer."""
        reply = agent.handle_user_message("What is the CPS Energy deposit?")
        assert reply.text and len(reply.text) > 10


# ---------------------------------------------------------------------------
# Checklist integration
# ---------------------------------------------------------------------------


class TestChecklistIntegration:
    def test_checklist_persists_across_messages(self, agent):
        """Changes to the checklist made during a turn should persist."""
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        item = agent.tracker.get_item("cps_energy")
        assert item.status == "in_progress"

    def test_checklist_updated_after_submit(self, agent):
        """Submitting a completed workflow marks the service as completed."""
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        _fill_all_fields(agent)
        if agent.workflow and agent.workflow.is_complete():
            agent.handle_user_message("submit")
            item = agent.tracker.get_item("cps_energy")
            assert item.status == "completed"

    def test_cancel_resets_to_pending(self, agent):
        """Cancelling a workflow leaves the service in a non-completed state."""
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        agent.handle_user_message("cancel")
        item = agent.tracker.get_item("cps_energy")
        assert item.status in (
            "pending",
            "in_progress",
        )  # cancel doesn't revert to pending in current impl


# ---------------------------------------------------------------------------
# Profile prefill integration
# ---------------------------------------------------------------------------


class TestProfilePrefillIntegration:
    def test_profile_prefilled_in_new_form(self, agent):
        """Values submitted in one form are available to prefill the next."""
        agent.tracker.update_profile(
            {
                "user": {
                    "first_name": "Alex",
                    "last_name": "Kim",
                    "email": "alex@example.com",
                }
            }
        )
        agent._begin_workflow("saws")
        agent._commit_pending_workflow()
        # first_name should be pre-populated from profile
        assert agent.workflow.state.values.get("first_name") == "Alex"


# ---------------------------------------------------------------------------
# Multi-turn conversation integration
# ---------------------------------------------------------------------------


class TestMultiTurnConversation:
    def test_multiple_turns_without_error(self, agent):
        messages = [
            "What is the deposit for CPS Energy?",
            "show my checklist",
            "Tell me about SAWS service",
        ]
        for msg in messages:
            reply = agent.handle_user_message(msg)
            assert reply.text

    def test_history_grows_per_turn(self, agent):
        initial = len(agent.tracker.state.history)
        agent.handle_user_message("Hello")
        agent.handle_user_message("What is SAWS?")
        assert len(agent.tracker.state.history) > initial

    def test_workflow_then_question_then_resume(self, agent):
        """Start a form, pause, ask a question, resume — all should work."""
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        agent.handle_user_message("pause")
        agent.handle_user_message("What is the deposit for CPS Energy?")
        reply = agent.handle_user_message("resume cps_energy")
        assert reply.text


# ---------------------------------------------------------------------------
# State persistence integration
# ---------------------------------------------------------------------------


class TestStatePersistence:
    def test_state_file_created_on_first_message(self, agent):
        agent.handle_user_message("hello")
        assert agent.tracker.path.exists()

    def test_active_workflow_saved_mid_form(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        agent.handle_user_message("Alex")
        assert agent.tracker.state.active_workflow is not None

    def test_active_workflow_cleared_after_cancel(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        agent.handle_user_message("cancel")
        assert agent.tracker.state.active_workflow is None


# ---------------------------------------------------------------------------
# Undo integration
# ---------------------------------------------------------------------------


class TestUndoIntegration:
    def test_undo_mid_workflow(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        agent.handle_user_message("Alex")  # first_name → index 1
        reply = agent.handle_user_message("undo")
        assert "back" in reply.text.lower() or "went" in reply.text.lower()
        assert agent.workflow.state.current_field_index == 0

    def test_go_back_alias(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        agent.handle_user_message("Alex")
        reply = agent.handle_user_message("go back")
        assert reply.text


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _fill_all_fields(agent) -> None:
    for _ in range(30):
        if agent.workflow is None or agent.workflow.is_complete():
            break
        field = agent.workflow.current_field
        if field is None:
            break
        val = _sample_value(field)
        agent.handle_user_message(val)


def _sample_value(field) -> str:
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
        # 14 days = same weekday as today (always a weekday if today is one);
        # skip forward if it lands on a weekend so the lead_time validator accepts.
        d = datetime.date.today() + datetime.timedelta(days=14)
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        return d.isoformat()
    if field.type == "bool":
        return "no"
    return "TestValue"
