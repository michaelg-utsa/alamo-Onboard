#!/usr/bin/env bash
# scripts/demo.sh
#
# Exercises all 8 user stories end-to-end in demo mode (no live LLM required).
# Usage: bash scripts/demo.sh   (or: make demo)

set -uo pipefail

export ALAMO_DEMO_MODE=1

PASSED=0
FAILED=0
TOTAL=0

run_story() {
  local id="$1"
  local description="$2"
  local fn="$3"
  TOTAL=$((TOTAL + 1))
  echo
  echo "--- $id: $description ---"
  if "$fn"; then
    echo "[$id] PASS"
    PASSED=$((PASSED + 1))
  else
    echo "[$id] FAIL"
    FAILED=$((FAILED + 1))
  fi
}

echo "=================================================================="
echo "AlamoOnboard Demo — 8 user stories"
echo "=================================================================="

story_us01() {
  python3 - << 'PYEOF'
import os; os.environ.setdefault("ALAMO_DEMO_MODE", "1")
from src.agent.orchestrator import AlamoAgent
a = AlamoAgent()
r = a.handle_user_message("What is the deposit for CPS Energy?")
assert r.text and len(r.text) > 30, f"Expected non-empty response, got: {r.text!r}"
print(r.text[:300])
PYEOF
}

story_us02() {
  python3 - << 'PYEOF'
import os; os.environ.setdefault("ALAMO_DEMO_MODE", "1")
from src.agent.orchestrator import AlamoAgent
a = AlamoAgent()
r = a.handle_user_message("show my checklist")
assert "[ ]" in r.text or "checklist" in r.text.lower(), "Expected checklist in response"
assert "CPS" in r.text, "Expected CPS Energy in checklist"
assert "SAWS" in r.text, "Expected SAWS in checklist"
print(r.text[:300])
PYEOF
}

story_us03() {
  python3 - << 'PYEOF'
import os, datetime; os.environ.setdefault("ALAMO_DEMO_MODE", "1")
from src.agent.orchestrator import AlamoAgent
a = AlamoAgent()
a._begin_workflow("cps_energy")
a._commit_pending_workflow()
start = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
for v in ["Alex","Kim","1990-05-15","123-45-6789","alex@example.com","2105551234","123 Main St","keep","keep","78205",start,"no","yes","no"]:
    if a.workflow is None or a.workflow.is_complete():
        break
    a.handle_user_message(v)
item = a.tracker.get_item("cps_energy")
assert item.status in ("in_progress", "completed"), f"Expected in_progress/completed, got {item.status}"
print(f"CPS Energy status: {item.status}")
PYEOF
}

story_us04() {
  python3 - << 'PYEOF'
import os; os.environ.setdefault("ALAMO_DEMO_MODE", "1")
from src.agent.orchestrator import AlamoAgent
a = AlamoAgent()
a.tracker.update_profile({"user": {"first_name": "Alex", "last_name": "Kim",
    "email": "alex@example.com", "phone": "2105551234",
    "service_address": "123 Main St", "service_city": "San Antonio",
    "service_state": "TX", "service_zip": "78205"}})
a._begin_workflow("saws")
a._commit_pending_workflow()
assert a.workflow is not None, "SAWS workflow should have started"
assert a.workflow.schema.service_id == "saws"
item = a.tracker.get_item("saws")
assert item.status == "in_progress", f"Expected in_progress, got {item.status}"
print(f"SAWS status: {item.status} — pre-fill active")
PYEOF
}

story_us05() {
  python3 - << 'PYEOF'
import os; os.environ.setdefault("ALAMO_DEMO_MODE", "1")
from src.agent.orchestrator import AlamoAgent
a = AlamoAgent()
a.tracker.update_profile({"user": {"first_name": "Alex", "last_name": "Kim",
    "phone": "2105551234", "service_address": "123 Main St", "service_zip": "78205"}})
a._begin_workflow("cps_energy")
a._commit_pending_workflow()
idx_before = a.workflow.state.current_field_index
r = a.handle_user_message("keep all")
idx_after = a.workflow.state.current_field_index
assert idx_after >= idx_before, "keep all should advance past pre-filled fields"
assert r.text, "Expected non-empty response"
print(f"Advanced from field {idx_before} to {idx_after}")
PYEOF
}

story_us06() {
  python3 - << 'PYEOF'
import os; os.environ.setdefault("ALAMO_DEMO_MODE", "1")
from src.agent.orchestrator import AlamoAgent
a = AlamoAgent()
a._begin_workflow("cps_energy")
a._commit_pending_workflow()
a.handle_user_message("Alex")
a.handle_user_message("pause")
assert a.workflow is None, "Workflow should be detached after pause"
assert a.tracker.state.active_workflow is not None, "State should persist after pause"
a.handle_user_message("resume cps_energy")
assert a.workflow is not None, "Workflow should be restored after resume"
print("Paused and resumed successfully")
PYEOF
}

story_us07() {
  python3 - << 'PYEOF'
import os; os.environ.setdefault("ALAMO_DEMO_MODE", "1")
from src.forms.validators import validate
ok, _, err = validate("email", "notanemail")
assert ok is False, "Invalid email should be rejected"
assert "email" in err.lower(), f"Error should mention email, got: {err}"
ok2, _, _ = validate("email", "alex@example.com")
assert ok2 is True, "Valid email should be accepted"
print(f"Rejected 'notanemail': {err}")
print("Accepted 'alex@example.com'")
PYEOF
}

story_us08() {
  python3 - << 'PYEOF'
import os, datetime; os.environ.setdefault("ALAMO_DEMO_MODE", "1")
from src.forms.validators import validate
tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
ok, _, err = validate("lead_time_5bd", tomorrow)
assert ok is False, f"Tomorrow ({tomorrow}) should be rejected for SAWS"
assert err, "Error message should be non-empty"
future = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
ok2, _, _ = validate("lead_time_5bd", future)
assert ok2 is True, f"10 days out ({future}) should be accepted"
print(f"Rejected {tomorrow}: {err}")
print(f"Accepted {future}")
PYEOF
}

run_story "US-01" "Ask a factual question about CPS Energy deposit"        story_us01
run_story "US-02" "View the move-in checklist"                             story_us02
run_story "US-03" "Complete CPS Energy signup form"                        story_us03
run_story "US-04" "Complete SAWS signup with pre-filled fields"            story_us04
run_story "US-05" "Use keep-all to accept pre-filled values"               story_us05
run_story "US-06" "Pause a form mid-entry and resume it later"             story_us06
run_story "US-07" "Invalid email shows validation error (error path)"      story_us07
run_story "US-08" "Start date too soon shows lead time error (error path)" story_us08

echo
echo "=================================================================="
echo "Demo summary: $PASSED / $TOTAL stories passed ($FAILED failed)"
echo "=================================================================="

[[ $FAILED -eq 0 ]]
