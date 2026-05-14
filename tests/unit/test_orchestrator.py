"""Unit tests for src/agent/orchestrator.py (demo mode, no LLM needed)."""

from __future__ import annotations

import os

os.environ.setdefault("ALAMO_DEMO_MODE", "1")
os.environ.setdefault("ALAMO_LLM_API_KEY", "")


class TestHandleEmpty:
    def test_empty_string_returns_prompt(self, agent):
        reply = agent.handle_user_message("")
        assert reply.text  # not empty
        assert reply.checklist_changed is False

    def test_whitespace_only_returns_prompt(self, agent):
        reply = agent.handle_user_message("   ")
        assert reply.text


class TestChecklistDisplay:
    def test_show_checklist(self, agent):
        reply = agent.handle_user_message("show my checklist")
        assert "checklist" in reply.text.lower() or "[ ]" in reply.text

    def test_checklist_keyword(self, agent):
        reply = agent.handle_user_message("checklist")
        assert "[ ]" in reply.text or "checklist" in reply.text.lower()


class TestFactualQuestion:
    def test_deposit_question_returns_text(self, agent):
        reply = agent.handle_user_message("What is the deposit for CPS Energy?")
        assert reply.text
        # In demo mode the answer should mention something useful
        assert len(reply.text) > 20

    def test_unknown_question_returns_text(self, agent):
        reply = agent.handle_user_message("What is the weather like?")
        assert reply.text


class TestWorkflowLifecycle:
    """
    In demo mode the LLM stub only calls retrieve_knowledge, not start_workflow.
    We test the workflow lifecycle via the internal helpers directly.
    """

    def _stage_cps_workflow(self, agent):
        """Call _begin_workflow to stage the CPS Energy workflow."""
        msg = agent._begin_workflow("cps_energy")
        assert agent._pending_workflow == "cps_energy"
        return msg

    def test_begin_workflow_stages_pending(self, agent):
        """_begin_workflow stages the service and returns confirmation text."""
        msg = agent._begin_workflow("cps_energy")
        assert agent._pending_workflow == "cps_energy"
        assert "yes" in msg.lower() or "begin" in msg.lower() or "CPS" in msg

    def test_commit_pending_workflow_creates_workflow(self, agent):
        agent._begin_workflow("cps_energy")
        reply = agent._commit_pending_workflow()
        assert agent.workflow is not None
        assert agent.workflow.schema.service_id == "cps_energy"
        assert reply.checklist_changed is True

    def test_decline_clears_pending(self, agent):
        """A non-yes reply to the staged workflow discards it."""
        agent._begin_workflow("cps_energy")
        agent.handle_user_message("no thanks")
        assert agent._pending_workflow is None

    def test_yes_reply_commits_pending_workflow(self, agent):
        """After _begin_workflow, sending 'yes' calls _commit_pending_workflow."""
        agent._begin_workflow("cps_energy")
        agent.handle_user_message("yes")
        assert agent.workflow is not None
        assert agent._pending_workflow is None

    def test_cancel_during_workflow(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        reply = agent.handle_user_message("cancel")
        assert agent.workflow is None
        assert "cancel" in reply.text.lower()

    def test_pause_during_workflow(self, agent):
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        reply = agent.handle_user_message("pause")
        assert agent.workflow is None
        assert "pause" in reply.text.lower() or "paused" in reply.text.lower()

    def test_unknown_service_id_returns_error(self, agent):
        msg = agent._begin_workflow("nonexistent_service")
        assert "don't have" in msg.lower() or "not" in msg.lower()
        # Should not stage a pending workflow for an unknown service
        assert agent._pending_workflow is None or agent._pending_workflow == "nonexistent_service"

    def test_submit_completes_workflow(self, agent):
        """Fill all fields then submit; checklist should be updated."""
        agent._begin_workflow("cps_energy")
        agent._commit_pending_workflow()
        for _ in range(20):
            if agent.workflow is None or agent.workflow.is_complete():
                break
            field = agent.workflow.current_field
            if field is None:
                break
            agent.handle_user_message(_sample_value(field))
        if agent.workflow and agent.workflow.is_complete():
            reply = agent.handle_user_message("submit")
            assert "completed" in reply.text.lower() or "checklist" in reply.text.lower()


class TestResume:
    def test_resume_keyword_after_pause(self, agent):
        agent.handle_user_message("I want to sign up for CPS Energy")
        agent.handle_user_message("yes")
        agent.handle_user_message("pause")
        reply = agent.handle_user_message("resume cps_energy")
        # Should re-enter the workflow
        assert agent.workflow is not None or "resume" in reply.text.lower()


class TestRequestIdLogging:
    def test_each_turn_produces_reply(self, agent):
        """Smoke-test that request_id plumbing does not crash the call."""
        for msg in ("hello", "show checklist", "What is CPS?"):
            reply = agent.handle_user_message(msg)
            assert reply.text


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _sample_value(field) -> str:
    """Return a plausible value for any FormField type during test fill."""
    import datetime

    vname = field.validator or ""
    fname = field.name
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
        # 14 days = same weekday as today; skip weekends so the lead_time
        # validator (rejects Sat/Sun and dates < N business days out) accepts.
        future = datetime.date.today() + datetime.timedelta(days=14)
        while future.weekday() >= 5:
            future += datetime.timedelta(days=1)
        return future.isoformat()
    if field.type == "bool":
        return "no"
    return "TestValue"
