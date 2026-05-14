"""Centralized configuration for AlamoOnboard.

All paths and runtime knobs are read from environment variables with
sensible defaults so the project runs out of the box on Windows or Linux.

Environment variables:
    ALAMO_OUTPUT_DIR     -- where indices, logs and user state are written
    ALAMO_DATA_DIR       -- where form_schemas.json lives
    ALAMO_INDEX_DIR      -- subdirectory of OUTPUT_DIR used for the FAISS index
    ALAMO_SAU_CHUNKS     -- path to the SA Utilities chunks JSON
    ALAMO_SAU_CHROMA     -- path to the SA Utilities ChromaDB directory
    ALAMO_SAU_COLLECTION -- ChromaDB collection name
    ALAMO_USER_STATE     -- json file used to persist a user's checklist + form data
    ALAMO_EMBED_MODEL    -- HuggingFace sentence-transformers model id
    ALAMO_EMBED_DIM      -- embedding dimension (must match the model)
    ALAMO_LLM_MODEL      -- model name passed to the OpenAI-compatible chat endpoint
    ALAMO_LLM_BASE_URL   -- base URL for the OpenAI-compatible chat endpoint
    ALAMO_LLM_API_KEY    -- API key for the chat endpoint (falls back to OPENAI_API_KEY)
    ALAMO_DEMO_MODE      -- "1" forces a no-LLM rule-based mode for offline demos
    ALAMO_TOP_K          -- number of passages returned per retrieval call
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parent

DATA_DIR: Path = Path(
    os.environ.get("ALAMO_DATA_DIR", PROJECT_ROOT / "data")
).resolve()

OUTPUT_DIR: Path = Path(
    os.environ.get("ALAMO_OUTPUT_DIR", PROJECT_ROOT / "output")
).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

INDEX_DIR: Path = Path(
    os.environ.get("ALAMO_INDEX_DIR", OUTPUT_DIR / "index")
).resolve()
INDEX_DIR.mkdir(parents=True, exist_ok=True)

USER_STATE_PATH: Path = Path(
    os.environ.get("ALAMO_USER_STATE", OUTPUT_DIR / "user_state.json")
).resolve()

LOG_DIR: Path = OUTPUT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Form schemas live with the project (we maintain them).
FORM_SCHEMAS_PATH: Path = DATA_DIR / "form_schemas.json"

# ---------------------------------------------------------------------------
# SA Utilities pipeline outputs
# ---------------------------------------------------------------------------
# The SA Utilities pipeline (sibling package `sa_utilities`) produces:
#   - all_chunks.json: list of chunk metadata dicts
#   - chroma/: ChromaDB persistent directory holding the embeddings
#
# Our retrieval pipeline reads both at index-build time and copies the
# embeddings into a FAISS index for fast hybrid (BM25 + dense) search.
SA_UTILITIES_ROOT: Path = Path(
    os.environ.get(
        "ALAMO_SAU_ROOT",
        PROJECT_ROOT / "sa_utilities",
    )
).resolve()
SA_UTILITIES_CHUNKS_PATH: Path = Path(
    os.environ.get(
        "ALAMO_SAU_CHUNKS",
        SA_UTILITIES_ROOT / "data" / "chunks" / "all_chunks.json",
    )
).resolve()
SA_UTILITIES_CHROMA_PATH: Path = Path(
    os.environ.get(
        "ALAMO_SAU_CHROMA",
        SA_UTILITIES_ROOT / "data" / "chroma",
    )
).resolve()
SA_UTILITIES_COLLECTION: str = os.environ.get(
    "ALAMO_SAU_COLLECTION", "sa_utilities"
)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
# Must match the model the SA Utilities pipeline used. The pipeline uses
# all-MiniLM-L6-v2 (384 dim) by default; if that ever changes, update both
# sides at the same time.
EMBED_MODEL: str = os.environ.get(
    "ALAMO_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
EMBED_DIM: int = int(os.environ.get("ALAMO_EMBED_DIM", "384"))

LLM_MODEL: str = os.environ.get("ALAMO_LLM_MODEL", "llama-3.3-70b-instruct-awq")
LLM_BASE_URL: str | None = os.environ.get("ALAMO_LLM_BASE_URL") or None
LLM_API_KEY: str | None = (
    os.environ.get("ALAMO_LLM_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
)

DEMO_MODE: bool = os.environ.get("ALAMO_DEMO_MODE", "0") == "1" or LLM_API_KEY is None

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
TOP_K: int = int(os.environ.get("ALAMO_TOP_K", "5"))


def banner() -> str:
    """Return a one-line summary of the active config (for logging)."""
    mode = "DEMO (no LLM)" if DEMO_MODE else f"LLM={LLM_MODEL}"
    return (
        f"[AlamoOnboard] mode={mode} embed={EMBED_MODEL} "
        f"output={OUTPUT_DIR} index={INDEX_DIR}"
    )
