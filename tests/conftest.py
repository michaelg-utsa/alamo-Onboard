"""Shared pytest fixtures for the AlamoOnboard test suite."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Force demo mode in all tests (no LLM API key needed)
os.environ.setdefault("ALAMO_DEMO_MODE", "1")
os.environ.setdefault("ALAMO_LLM_API_KEY", "")


@pytest.fixture()
def tmp_state_file(tmp_path: Path):
    """Return a path to a fresh user_state.json in a temp directory."""
    return tmp_path / "user_state.json"


@pytest.fixture()
def tracker(tmp_state_file):
    """A fresh ChecklistTracker backed by a temp file."""
    from myproject.checklist.tracker import ChecklistTracker

    return ChecklistTracker(path=tmp_state_file)


@pytest.fixture()
def mock_retriever():
    """A HybridRetriever stub that returns one fake passage."""
    from myproject.indexer.retriever import RetrievedPassage

    r = MagicMock()
    r.search.return_value = [
        RetrievedPassage(
            text="CPS Energy requires a $200 deposit for new residential accounts.",
            title="New Service Deposit",
            source="CPS Energy",
            url="https://www.cpsenergy.com/deposit",
            score=0.95,
        )
    ]
    r.embedder = MagicMock()
    return r


@pytest.fixture()
def agent(tmp_state_file, mock_retriever):
    """A fully wired AlamoAgent in demo mode with a mock retriever."""
    from myproject.agent.orchestrator import AlamoAgent
    from myproject.checklist.tracker import ChecklistTracker

    tracker = ChecklistTracker(path=tmp_state_file)
    return AlamoAgent(retriever=mock_retriever, tracker=tracker)


@pytest.fixture()
def cps_schema():
    """Load the CPS Energy form schema from disk."""
    from myproject.forms.schemas import load_schemas

    schemas = load_schemas()
    # The JSON key is 'cps_energy_start'; fall back to searching by service_id
    return schemas.get("cps_energy_start") or next(
        s for s in schemas.values() if s.service_id == "cps_energy"
    )


@pytest.fixture()
def saws_schema():
    """Load the SAWS form schema from disk."""
    from myproject.forms.schemas import load_schemas

    schemas = load_schemas()
    # The JSON key is 'saws_start'; fall back to searching by service_id
    return schemas.get("saws_start") or next(s for s in schemas.values() if s.service_id == "saws")
