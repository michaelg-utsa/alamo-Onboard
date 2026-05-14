"""Unit tests for src/checklist/tracker.py."""

from __future__ import annotations

import json

from src.checklist.tracker import ChecklistTracker, UserState


class TestChecklistTrackerInit:
    def test_fresh_state_has_three_items(self, tmp_state_file):
        tracker = ChecklistTracker(path=tmp_state_file)
        assert len(tracker.state.checklist) == 3

    def test_loads_existing_file(self, tmp_state_file):
        """If the file already exists it should be loaded, not overwritten."""
        state = UserState.fresh()
        state.profile = {"user": {"first_name": "Alex"}}
        tmp_state_file.write_text(json.dumps(state.to_dict(), ensure_ascii=False), encoding="utf-8")
        tracker = ChecklistTracker(path=tmp_state_file)
        assert tracker.state.profile["user"]["first_name"] == "Alex"

    def test_corrupted_file_falls_back_to_fresh(self, tmp_state_file):
        tmp_state_file.write_text("not json", encoding="utf-8")
        tracker = ChecklistTracker(path=tmp_state_file)
        assert len(tracker.state.checklist) == 3


class TestSaveAndLoad:
    def test_round_trip(self, tmp_state_file):
        tracker = ChecklistTracker(path=tmp_state_file)
        tracker.set_status("cps_energy", "completed", notes="done")
        tracker2 = ChecklistTracker(path=tmp_state_file)
        item = tracker2.get_item("cps_energy")
        assert item is not None
        assert item.status == "completed"
        assert item.notes == "done"

    def test_save_creates_parent_dirs(self, tmp_path):
        deep = tmp_path / "nested" / "dir" / "state.json"
        tracker = ChecklistTracker(path=deep)
        tracker.save()
        assert deep.exists()


class TestSetStatus:
    def test_set_pending_to_in_progress(self, tracker):
        tracker.set_status("saws", "in_progress")
        assert tracker.get_item("saws").status == "in_progress"

    def test_completed_sets_completed_at(self, tracker):
        tracker.set_status("saws", "completed")
        item = tracker.get_item("saws")
        assert item.completed_at is not None
        assert "T" in item.completed_at  # ISO timestamp

    def test_unknown_service_id_is_noop(self, tracker):
        # Should not raise
        tracker.set_status("nonexistent", "completed")

    def test_notes_stored(self, tracker):
        tracker.set_status("cosa_solid_waste", "skipped", notes="Not applicable")
        assert tracker.get_item("cosa_solid_waste").notes == "Not applicable"


class TestRenderChecklist:
    def test_contains_service_names(self, tracker):
        rendered = tracker.render_checklist()
        assert "CPS Energy" in rendered
        assert "SAWS" in rendered

    def test_shows_pending_symbol(self, tracker):
        rendered = tracker.render_checklist()
        assert "[ ]" in rendered

    def test_shows_completed_symbol(self, tracker):
        tracker.set_status("cps_energy", "completed")
        rendered = tracker.render_checklist()
        assert "[x]" in rendered

    def test_shows_in_progress_symbol(self, tracker):
        tracker.set_status("saws", "in_progress")
        rendered = tracker.render_checklist()
        assert "[~]" in rendered


class TestProfileOps:
    def test_update_profile(self, tracker):
        tracker.update_profile({"user": {"first_name": "Alex"}})
        assert tracker.state.profile["user"]["first_name"] == "Alex"

    def test_profile_persists_across_instances(self, tmp_state_file):
        t1 = ChecklistTracker(path=tmp_state_file)
        t1.update_profile({"user": {"city": "San Antonio"}})
        t2 = ChecklistTracker(path=tmp_state_file)
        assert t2.state.profile["user"]["city"] == "San Antonio"


class TestWorkflowOps:
    def test_set_and_clear_active_workflow(self, tracker):
        tracker.set_active_workflow({"service_id": "cps_energy", "current_field_index": 2})
        assert tracker.state.active_workflow is not None
        tracker.set_active_workflow(None)
        assert tracker.state.active_workflow is None


class TestHistoryOps:
    def test_append_history(self, tracker):
        tracker.append_history("user", "Hello")
        tracker.append_history("assistant", "Hi there")
        assert len(tracker.state.history) == 2
        assert tracker.state.history[0]["role"] == "user"
        assert tracker.state.history[1]["content"] == "Hi there"

    def test_history_capped_at_200(self, tracker):
        for i in range(210):
            tracker.append_history("user", f"msg {i}")
        assert len(tracker.state.history) <= 200

    def test_history_has_timestamp(self, tracker):
        tracker.append_history("user", "test")
        assert "ts" in tracker.state.history[0]


class TestReset:
    def test_reset_clears_state(self, tmp_state_file):
        tracker = ChecklistTracker(path=tmp_state_file)
        tracker.set_status("cps_energy", "completed")
        tracker.reset()
        assert tracker.get_item("cps_energy").status == "pending"
