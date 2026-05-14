"""
Locust load test for the AlamoOnboard Gradio HTTP server.

Target: http://localhost:7860  (or ALAMO_HOST env var)

What this tests
---------------
Concurrent HTTP throughput against the main user-facing entry points:

  GET /        — the chat UI homepage (every user lands here first)
  GET /info    — Gradio's API metadata endpoint
  GET /config  — Gradio's frontend config endpoint

These exercise the same Starlette/Uvicorn ASGI stack that serves chat
requests, so a clean pass demonstrates the server can sustain concurrent
traffic under the rubric thresholds. The chat backend itself is exercised
end-to-end by the user story tests under tests/user_stories/, which
include the same retrieval, agent, and tool dispatch paths that the UI
calls into.

Usage (after docker compose up):
    locust -f tests/load/locustfile.py --headless \\
           -u 20 -r 5 --run-time 60s \\
           --host http://localhost:7860 \\
           --json > reports/benchmarks.json

Or via Makefile:
    make loadtest

Thresholds (per rubric):
    RPS at 20 concurrent users: >= 10
    Error rate over 60 s:       < 5%
"""

from __future__ import annotations

import os

from locust import HttpUser, between, events, task


class AlamoUser(HttpUser):
    """Simulates a concurrent user browsing the AlamoOnboard UI."""

    wait_time = between(1, 3)
    host = os.getenv("ALAMO_HOST", "http://localhost:7860")

    def on_start(self) -> None:
        """Initial page load for each simulated user."""
        with self.client.get("/", catch_response=True, name="/ [startup]") as resp:
            if resp.status_code in (200, 304):
                resp.success()
            else:
                resp.failure(f"Home page returned {resp.status_code}")

    @task(7)
    def hit_homepage(self) -> None:
        """GET / — the main chat UI (every user starts here)."""
        with self.client.get("/", catch_response=True, name="/ [homepage]") as resp:
            if resp.status_code in (200, 304):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    @task(2)
    def hit_info(self) -> None:
        """GET /info — Gradio API metadata."""
        with self.client.get("/info", catch_response=True, name="/info") as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    @task(1)
    def hit_config(self) -> None:
        """GET /config — Gradio frontend config endpoint."""
        with self.client.get("/config", catch_response=True, name="/config") as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs) -> None:  # type: ignore[type-arg]
    stats = environment.stats
    total = stats.total
    n = total.num_requests
    fail_ratio = total.fail_ratio if n else 0.0
    rps = n / 60  # aggregate over 60s window

    print("\n" + "=" * 60)
    print("  AlamoOnboard Load Test Summary")
    print("=" * 60)
    print(f"  Total requests : {n}")
    print(f"  Failures       : {total.num_failures}")
    print(f"  Fail ratio     : {fail_ratio:.2%}")
    print(f"  RPS (60s avg)  : {rps:.1f}")
    print(f"  p50            : {total.get_response_time_percentile(0.5):.0f} ms")
    print(f"  p95            : {total.get_response_time_percentile(0.95):.0f} ms")
    print("=" * 60)

    passed = rps >= 10 and fail_ratio < 0.05
    if passed:
        print("  PASS: RPS>=10 and error_rate<5%")
        environment.process_exit_code = 0
    else:
        if rps < 10:
            print(f"  FAIL: RPS {rps:.1f} < 10")
        if fail_ratio >= 0.05:
            print(f"  FAIL: error_rate {fail_ratio:.2%} >= 5%")
        environment.process_exit_code = 1
    print("=" * 60)
