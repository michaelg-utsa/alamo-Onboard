"""Standalone command-line script to (re)build the retrieval index.

Reads chunks + embeddings from the SA Utilities pipeline output
(``sa_utilities/data/chunks/all_chunks.json`` plus the ChromaDB
directory at ``sa_utilities/data/chroma/``) and writes a FAISS index
plus BM25 metadata into ``output/index/``.

Equivalent to ``python main.py --rebuild`` but without launching the UI
afterward.

Run from the project root:

    python scripts/build_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project importable when running from anywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.indexer.retriever import HybridRetriever  # noqa: E402
from src.utils.logging_utils import get_logger  # noqa: E402

logger = get_logger(__name__)


def main() -> None:
    retriever = HybridRetriever()
    retriever.build_from_sa_utilities()
    logger.info("index built successfully")


if __name__ == "__main__":
    main()
