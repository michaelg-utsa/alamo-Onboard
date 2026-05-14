"""End-to-end smoke test for AlamoOnboard.

Exercises the loader, retriever, agent (demo mode), form workflow,
validators, prefill, and checklist persistence -- without needing to
download a real embedding model or talk to a real LLM.

We skip ChromaDB by monkey-patching the loader to return synthetic
chunks + a synthetic vector array. The synthetic vectors come from a
hash-based "fake embedder" so the loader's vector-shape and
alignment checks still exercise real code paths.

Run from the project root:

    python smoke_test.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Sandbox env BEFORE importing project modules so paths resolve correctly.
# ---------------------------------------------------------------------------
SANDBOX = Path(tempfile.mkdtemp(prefix="alamo_smoke_"))

os.environ["ALAMO_OUTPUT_DIR"] = str(SANDBOX / "output")
os.environ["ALAMO_DEMO_MODE"] = "1"
os.environ.pop("ALAMO_LLM_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Synthetic dataset
# ---------------------------------------------------------------------------
SYNTH_CHUNKS = [
    {
        "chunk_id": "saws__deposit__0001",
        "source": "saws",
        "doc_type": "policy",
        "title": "SAWS New Service Deposit",
        "url": "https://www.saws.org/your-water/start-service/",
        "text": "SAWS asks new residential customers for a deposit of about 100 dollars to start water service. The deposit can be waived with a letter of credit.",
        "chunk_index": 0,
    },
    {
        "chunk_id": "cps__deposit__0001",
        "source": "cps",
        "doc_type": "policy",
        "title": "CPS Energy Deposits",
        "url": "https://www.cpsenergy.com/en/my-home/manage-my-account/deposits.html",
        "text": "Deposits at CPS Energy are determined by an automated credit screening. Active-duty military relocating under PCS orders may request a deposit waiver.",
        "chunk_index": 0,
    },
    {
        "chunk_id": "cosa__cart__0001",
        "source": "cosa",
        "doc_type": "rate",
        "title": "Garbage Cart Sizes and Fees",
        "url": "https://www.sa.gov/Directory/Departments/SWMD/Services/Garbage",
        "text": "Three cart sizes are offered: 48 gallons at about 14.76 dollars, 64 gallons at about 20.26, and 96 gallons at about 30.75 per month. Recycling and organics carts are free.",
        "chunk_index": 0,
    },
    {
        "chunk_id": "saws__contact__0001",
        "source": "saws",
        "doc_type": "contact",
        "title": "SAWS Customer Contact",
        "url": "https://www.saws.org/service/customer-service/",
        "text": "SAWS customer service is reachable at 210-704-SAWS (7297). Bilingual support is available.",
        "chunk_index": 0,
    },
]


def _fake_embed_one(text: str, dim: int = 384) -> np.ndarray:
    """Hash-based deterministic 'embedding' for testing only.

    Real embeddings respect semantic similarity. This one only produces
    consistent vectors per string, which is enough to validate that the
    pipeline plumbing (loader, FAISS, retriever) works without a real
    model.
    """
    rng = np.random.default_rng(int.from_bytes(hashlib.md5(text.encode()).digest()[:8], "little"))
    vec = rng.normal(size=dim).astype(np.float32)
    vec /= max(np.linalg.norm(vec), 1e-9)
    return vec


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
results: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append((label, ok, detail))
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f" -- {detail}"
    print(line)


# ===========================================================================
# Test plan
# ===========================================================================
def main() -> int:
    print(f"sandbox: {SANDBOX}\n")

    # -----------------------------------------------------------------------
    # 1. Config loads
    # -----------------------------------------------------------------------
    import config

    check("config loads", config.DEMO_MODE is True, f"output={config.OUTPUT_DIR}")

    # -----------------------------------------------------------------------
    # 2. Form schemas load
    # -----------------------------------------------------------------------
    from src.forms.schemas import load_schemas

    schemas = load_schemas()
    check(
        "form schemas load",
        set(schemas) == {"cps_energy_start", "saws_start", "cosa_solid_waste"},
    )
    cps = schemas["cps_energy_start"]
    check("cps form has fields", len(cps.fields) >= 10, f"{len(cps.fields)} fields")

    # -----------------------------------------------------------------------
    # 3. Validators
    # -----------------------------------------------------------------------
    from src.forms.validators import validate

    ok, val, _ = validate("email", "Jane@EXAMPLE.com")
    check("email validator normalizes case", ok and val == "jane@example.com")

    ok, val, _ = validate("phone_us", "210-555-1212")
    check("phone validator formats US number", ok and val == "(210) 555-1212")

    ok, val, _ = validate("ssn_or_dl", "123-45-6789")
    check("ssn validator masks number", ok and val.endswith("6789") and val.startswith("***"))

    ok, _, _ = validate("address", "Apt 5")
    check("address validator rejects unit-only", not ok)

    ok, _, _ = validate("lead_time_2bd", "2000-01-01")
    check("lead_time rejects past date", not ok)

    # -----------------------------------------------------------------------
    # 4. Form workflow with prefill
    # -----------------------------------------------------------------------
    from src.forms.workflow import FormWorkflow

    profile = {
        "user": {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "phone": "210-555-1212",
            "service_address": "100 Main St",
            "service_zip": "78201",
            "date_of_birth": "1990-04-15",
        }
    }
    wf = FormWorkflow(schema=cps)
    wf.start(profile)
    first_field_name = wf.current_field.name
    check("workflow starts on first field", first_field_name == "first_name")
    check(
        "prefill resolved first_name",
        wf.state.values.get("first_name") == "Jane",
        f"got {wf.state.values.get('first_name')!r}",
    )

    answers = {
        "ssn_or_dl": "123-45-6789",
        "service_state": "TX",
        "requested_start_date": "2099-12-15",
        "is_military_relocation": "no",
        "wants_paperless": "yes",
        "wants_budget_billing": "no",
    }
    safety = 0
    while not wf.is_complete() and safety < 60:
        safety += 1
        f = wf.current_field
        if f is None:
            break
        if wf.state.values.get(f.name) not in (None, ""):
            wf.submit_value("keep")
        else:
            wf.submit_value(answers.get(f.name, "test"))
    check("workflow completes", wf.is_complete(), f"safety={safety}")

    updated = wf.commit(profile)
    check(
        "commit pushes safe field email",
        updated.get("user", {}).get("email") == "jane@example.com",
    )
    check(
        "commit excludes ssn",
        "ssn_or_dl" not in updated.get("user", {}),
    )

    # -----------------------------------------------------------------------
    # 5. Checklist persistence
    # -----------------------------------------------------------------------
    from src.checklist.tracker import ChecklistTracker

    t1 = ChecklistTracker()
    t1.set_status("saws", "completed", "tested")
    t1.save()
    t2 = ChecklistTracker()
    saws_item = t2.get_item("saws")
    check(
        "checklist persists across reload",
        saws_item is not None and saws_item.status == "completed",
        f"saws status={saws_item.status if saws_item else 'missing'}",
    )

    # -----------------------------------------------------------------------
    # 6. Patch embedder so retriever doesn't try to download a real model
    # -----------------------------------------------------------------------
    from src.indexer import embedder as embedder_mod

    class FakeEmbedder:
        def encode(self, texts):
            return np.stack([_fake_embed_one(t) for t in texts], axis=0)

    embedder_mod.Embedder = FakeEmbedder  # type: ignore[assignment]

    from src.indexer import retriever as retr_mod

    retr_mod.Embedder = FakeEmbedder  # type: ignore[assignment]

    # -----------------------------------------------------------------------
    # 7. Patch loader so we don't need a real ChromaDB to test plumbing
    # -----------------------------------------------------------------------
    from src.indexer import loaders as loaders_mod

    def fake_load() -> tuple[list, np.ndarray]:
        chunks = [loaders_mod._coerce_chunk(c) for c in SYNTH_CHUNKS]
        vectors = np.stack([_fake_embed_one(c.text) for c in chunks], axis=0)
        vectors = loaders_mod._l2_normalize(vectors)
        return chunks, vectors

    loaders_mod.load_sa_utilities_data = fake_load
    loaders_mod.load_partner_data = fake_load  # back-compat alias
    retr_mod.load_sa_utilities_data = fake_load

    # -----------------------------------------------------------------------
    # 8. Source label normalization
    # -----------------------------------------------------------------------
    chunks, vecs = fake_load()
    check(
        "loader returns aligned data",
        len(chunks) == vecs.shape[0] == 4,
        f"chunks={len(chunks)} vec_rows={vecs.shape[0]}",
    )
    check("vectors are 384-dim", vecs.shape[1] == 384)
    check(
        "source labels normalized",
        chunks[0].source in {"SAWS", "CPS Energy", "City of San Antonio"},
    )

    # -----------------------------------------------------------------------
    # 9. Retriever build
    # -----------------------------------------------------------------------
    from src.indexer.retriever import HybridRetriever

    retriever = HybridRetriever()
    retriever.build_from_sa_utilities()
    check("retriever built from SA Utilities data", len(retriever.store) == 4)

    # -----------------------------------------------------------------------
    # 10. Retrieval queries (BM25 wins on keyword overlap)
    # -----------------------------------------------------------------------
    hits = retriever.search("SAWS deposit", k=2)
    check(
        "search 'SAWS deposit' returns SAWS source first",
        bool(hits) and hits[0].source == "SAWS",
        f"top={hits[0].source if hits else 'none'}",
    )

    hits = retriever.search("trash cart fees", k=2)
    check(
        "search 'trash cart fees' returns COSA source",
        bool(hits) and any(h.source == "City of San Antonio" for h in hits),
    )

    # -----------------------------------------------------------------------
    # 11. source_filter restricts results
    # -----------------------------------------------------------------------
    hits = retriever.search("deposit", k=5, source_filter=["SAWS"])
    check(
        "source_filter=['SAWS'] returns only SAWS hits",
        bool(hits) and all(h.source == "SAWS" for h in hits),
        f"sources={[h.source for h in hits]}",
    )

    # -----------------------------------------------------------------------
    # 12. Demo-mode agent answers a question
    # -----------------------------------------------------------------------
    from src.agent.orchestrator import AlamoAgent

    agent = AlamoAgent(retriever=retriever)
    reply = agent.handle_user_message("What's the deposit for SAWS water service?")
    check(
        "agent demo-mode returns an answer",
        bool(reply.text) and "demo mode" in reply.text.lower(),
        f"len={len(reply.text)}",
    )

    # -----------------------------------------------------------------------
    # 13. Agent can stage and commit a workflow programmatically
    # -----------------------------------------------------------------------
    agent._begin_workflow("cps_energy")  # noqa: SLF001 (test harness, stages)
    check("agent stages CPS workflow", agent._pending_workflow == "cps_energy")
    reply = agent._commit_pending_workflow()  # noqa: SLF001 (test harness, commits)
    check("agent commits pending workflow", agent.workflow is not None)

    # -----------------------------------------------------------------------
    # Done
    # -----------------------------------------------------------------------
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n=== {passed}/{total} checks passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    rc = main()
    try:
        shutil.rmtree(SANDBOX, ignore_errors=True)
    except Exception:
        pass
    sys.exit(rc)
