# Reproducibility Guide

## Hardware Profile

The system was developed and tested on the following configuration:

| Component | Specification |
|---|---|
| CPU | x86-64, 4+ cores recommended |
| RAM | 8 GB minimum (16 GB recommended for embedding model + FAISS in memory) |
| Disk | ~3 GB free (Docker image ~1.5 GB, embedding model ~100 MB, data pipeline output ~200 MB) |
| GPU | Not required (all inference runs on CPU) |
| OS | Windows 11 / Ubuntu 22.04 LTS (Docker-based deployment is platform-agnostic) |
| Network | Required for initial model download and SA Utilities web scraping |

## Expected Runtime

| Step | Expected time (first run) | Expected time (subsequent runs) |
|---|---|---|
| `docker compose build` | 3–5 minutes | <30 seconds (cached layers) |
| `make download-models` | 30–60 seconds | <5 seconds (cached) |
| `make download-data` (full scrape) | 5–15 minutes | 1–3 minutes (fingerprint cache skips unchanged pages) |
| `make test` | 2–4 minutes | same |
| App startup (first query) | <60 seconds | <10 seconds |
| `docker compose up` → healthy | <10 minutes | <3 minutes |

## One-Command Reproduction

### Prerequisites

Before running any `docker compose` or `make` command, make sure:

1. **You are in the project root** — the folder containing `docker-compose.yml`. Running from a parent or sibling folder will fail with `no configuration file provided`.
2. **`.env` exists** — copy it from the template before the first build:
   ```bash
   cp .env.example .env
   # Then open .env in an editor and fill in ALAMO_LLM_BASE_URL and ALAMO_LLM_API_KEY
   ```
   Without `.env`, `docker compose up` will fail at the `env_file` step.
3. **The LLM endpoint is reachable** — if you are using a UTSA internal endpoint (e.g. `10.246.100.230`), connect to UTSA VPN first. The TA grading on the UTSA network does not need this; remote graders or anyone testing off-campus does. If the endpoint is unreachable, the app will fall back to demo mode automatically and the test suite will still pass.

### Run

```bash
git clone <repository_url>
cd <repository_name>

# Fill in required environment variables (see Prerequisites above)
cp .env.example .env
# Edit .env: set ALAMO_LLM_BASE_URL and ALAMO_LLM_API_KEY

# Full reproduction: build image, download data and models, run tests
make reproduce
```

`make reproduce` executes these steps in order:
1. `docker compose build` — builds the Docker image
2. `make download-data` — runs the SA Utilities pipeline (scrape → chunk → embed)
3. `make download-models` — downloads and caches `all-MiniLM-L6-v2`
4. `pytest tests/` inside Docker with coverage reporting

## Starting the Application

```bash
docker compose up
# Open http://localhost:7860
```

The app is healthy when the Gradio interface is accessible at port 7860 and the welcome message is displayed.

## Expected Metric Values

| Metric | Expected value | Tolerance |
|---|---|---|
| User story test pass rate | ≥ 90% | ± 5% |
| Unit test pass rate | 100% | 0% |
| Code coverage (src/ + sa_utilities/) | ≥ 70% | — |
| Load test: requests/second at 20 concurrent users | ≥ 10 RPS | ± 20% |
| Load test: error rate over 60s window | < 5% | — |
| App startup to healthy (Docker) | < 10 minutes | — |

These metrics assume the LLM endpoint is available and responsive. In demo mode (no API key), user story tests that require LLM responses may produce degraded results.

## Pinned Versions

See `grading/manifest.yaml` for exact version pins including:
- Python version
- All package versions (mirrored from `requirements.txt`)
- Embedding model commit SHA (from HuggingFace Hub)
- Dataset scrape commit timestamp

## Troubleshooting

**Port 7860 already in use:**
```bash
docker compose down
# or change the host port in docker-compose.yml
```

**Embedding model download slow:**
The `sentence-transformers/all-MiniLM-L6-v2` model (~91 MB) downloads from HuggingFace Hub on first run. The loading message in the UI is shown during this download. It is cached at `~/.cache/huggingface/` inside the Docker volume.

**SA Utilities pipeline fails (ChromaDB not found):**
Run `make download-data` first. This runs the full scrape → chunk → embed pipeline and creates the ChromaDB at `sa_utilities/data/chroma/`. The FAISS index is built automatically on first app start.

**No LLM responses (only retrieval summaries):**
Check that `ALAMO_LLM_API_KEY` and `ALAMO_LLM_BASE_URL` are set in `.env`. Without them, the app runs in demo mode.

**`no configuration file provided` from docker compose:**
You are not in the project root. `cd` into the folder containing `docker-compose.yml` and re-run the command.

**Source edits don't seem to take effect:**
Docker reuses the previously-built image unless explicitly rebuilt. After editing any `.py` file, `Dockerfile`, or `requirements.txt`:
```bash
docker compose down
docker compose up -d --build
```
Without `--build`, the old image is reused and your changes are invisible to the running container.
