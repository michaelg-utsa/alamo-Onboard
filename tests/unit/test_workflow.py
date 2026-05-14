"""Unit tests for src/forms/workflow.py."""

from __future__ import annotations

from src.forms.workflow import FormWorkflow, WorkflowState


def _make_workflow(cps_schema):
    return FormWorkflow(cps_schema)


class TestWorkflowStart:
    def test_start_returns_intro(self, cps_schema):
        wf = _make_workflow(cps_schema)
        opener = wf.start({})
        assert cps_schema.title in opener
        assert "fields" in opener.lower() or str(len(cps_schema.fields)) in opener

    def test_start_prefills_from_profile(self, cps_schema):
        profile = {"user": {"first_name": "Alex", "last_name": "Kim"}}
        wf = _make_workflow(cps_schema)
        wf.start(profile)
        assert wf.state.values.get("first_name") == "Alex"
        assert wf.state.values.get("last_name") == "Kim"

    def test_not_complete_after_start(self, cps_schema):
        wf = _make_workflow(cps_schema)
        wf.start({})
        assert wf.is_complete() is False


class TestSubmitValue:
    def test_valid_text_advances(self, cps_schema):
        wf = _make_workflow(cps_schema)
        wf.start({})
        # first_name field is index 0
        advanced, msg = wf.submit_value("Alex")
        assert advanced is True
        assert wf.state.current_field_index == 1

    def test_keep_uses_prefilled(self, cps_schema):
        profile = {"user": {"first_name": "Alex"}}
        wf = _make_workflow(cps_schema)
        wf.start(profile)
        assert wf.state.values.get("first_name") == "Alex"
        advanced, msg = wf.submit_value("keep")
        assert advanced is True
        assert wf.state.values["first_name"] == "Alex"

    def test_skip_optional_field(self, cps_schema):
        wf = _make_workflow(cps_schema)
        wf.start({})
        # Navigate to an optional field (is_military_relocation is index 11)
        wf.state.current_field_index = 11
        advanced, msg = wf.submit_value("skip")
        assert advanced is True
        assert wf.state.values.get("is_military_relocation") == ""

    def test_skip_required_field_fails(self, cps_schema):
        wf = _make_workflow(cps_schema)
        wf.start({})
        # first_name is required (index 0)
        advanced, msg = wf.submit_value("skip")
        assert advanced is False
        assert "required" in msg.lower()

    def test_invalid_email_rejected(self, cps_schema):
        wf = _make_workflow(cps_schema)
        wf.start({})
        # Navigate to email field (index 4)
        wf.state.current_field_index = 4
        advanced, msg = wf.submit_value("notanemail")
        assert advanced is False
        assert "email" in msg.lower()
        assert wf.state.current_field_index == 4  # did not advance


class TestUndo:
    def test_undo_from_second_field(self, cps_schema):
        wf = _make_workflow(cps_schema)
        wf.start({})
        wf.submit_value("Alex")  # first_name → index 1
        msg = wf.undo()
        assert wf.state.current_field_index == 0
        assert "first_name" not in wf.state.values or wf.state.values.get("first_name") is None
        assert "went back" in msg.lower()

    def test_undo_at_start_returns_message(self, cps_schema):
        wf = _make_workflow(cps_schema)
        wf.start({})
        msg = wf.undo()
        assert "first field" in msg.lower()
        assert wf.state.current_field_index == 0


class TestKeepAll:
    def test_keep_all_skips_prefilled(self, cps_schema):
        profile = {"user": {"first_name": "Alex", "last_name": "Kim"}}
        wf = _make_workflow(cps_schema)
        wf.start(profile)
        # first_name and last_name are prefilled; keep_all should advance past both
        wf.keep_all()
        assert wf.state.current_field_index >= 2

    def test_keep_all_stops_at_gap(self, cps_schema):
        profile = {"user": {"first_name": "Alex"}}  # only first_name prefilled
        wf = _make_workflow(cps_schema)
        wf.start(profile)
        wf.keep_all()
        # Should stop at last_name (index 1) since it is not prefilled
        assert wf.state.current_field_index == 1


class TestWorkflowState:
    def test_to_dict_and_from_dict(self, cps_schema):
        wf = _make_workflow(cps_schema)
        wf.start({})
        wf.submit_value("Alex")
        d = wf.state.to_dict()
        restored = WorkflowState.from_dict(d)
        assert restored.service_id == wf.state.service_id
        assert restored.current_field_index == wf.state.current_field_index
        assert restored.values == wf.state.values
