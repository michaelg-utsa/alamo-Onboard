# Team Contributions

## Team Members

| Member | Role | Modules Owned | Contribution (%) |
|---|---|---|---|
| **Sidharth Nayak** | Lead Engineer | `src/agent/`, `src/forms/`, `src/indexer/`, `src/checklist/`, `sa_utilities/`, `tests/unit/`, `tests/integration/` | 50% |
| **Michael Goolsbey** | UI & QA | `src/ui/`, `docs/`, `tests/user_stories/`, `tests/edge/`, `tests/load/`, `Dockerfile`, `Makefile`, `grading/` | 50% |

**Total: 100%**

---

## Contribution Detail

### Sidharth Nayak

- Implemented `src/agent/orchestrator.py` — agent routing, form FSM lifecycle, LLM agentic loop
- Implemented `src/agent/llm_client.py` — OpenAI-compatible chat client, inline tool-call extraction, demo stub
- Implemented `src/forms/workflow.py` — FormWorkflow FSM, undo/keep-all/pause/resume commands
- Implemented `src/forms/validators.py` — field validator registry (email, phone, SSN, lead times)
- Implemented `src/indexer/retriever.py` — hybrid BM25+FAISS retrieval with RRF
- Implemented `sa_utilities/` pipeline — adapters (CPS, SAWS, CoSA), chunker, fingerprinter, embedder
- Wrote `tests/unit/` — one test per source module
- Wrote `tests/integration/` — end-to-end workflow tests

### Michael Goolsbey

- Implemented `src/ui/gradio_app.py` — Gradio Blocks layout, dynamic command buttons, lazy agent init
- Wrote `docs/SPEC.md`, `docs/STORIES.md`, `docs/usage.md`, `docs/LOGGING.md`, `docs/MODEL_CARD.md`
- Implemented `src/utils/logging_utils.py` — structured JSON logging, request_id via contextvars
- Created `Dockerfile`, `docker-compose.yml`, `.env.example`, `Makefile`
- Created `grading/manifest.yaml`, `grading/traceability.yaml`
- Wrote `tests/user_stories/` — one acceptance test per US-NN story
- Wrote `tests/edge/` and `tests/load/locustfile.py`

---

## Verification

```bash
git shortlog -sne --all --no-merges > reports/git_contributions.txt
cat reports/git_contributions.txt
```