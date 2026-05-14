"""
pipeline/runner.py
------------------
Orchestrates the full ingestion pipeline:

  1. Run all adapters (CPS, SAWS, CoSA)   [skipped with --no-fetch]
  2. Chunk all documents
  3. Save raw documents and chunks to disk as JSON

Usage:
    # Full run — fetch from web, chunk, save
    python -m sa_utilities.pipeline.runner

    # Specific sources only
    python -m sa_utilities.pipeline.runner --sources cps saws

    # Skip fetching — reload saved JSON and re-chunk only
    # (useful when tuning CHUNK_CONFIG without re-scraping)
    python -m sa_utilities.pipeline.runner --no-fetch

    # --no-fetch for specific sources
    python -m sa_utilities.pipeline.runner --sources cps --no-fetch
"""

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from sa_utilities.adapters.cosa import CoSAAdapter
from sa_utilities.adapters.cps import CPSAdapter
from sa_utilities.adapters.saws import SAWSAdapter
from sa_utilities.config import CHUNK_DIR, RAW_DIR
from sa_utilities.models import Chunk, DocType, Source, SourceDocument
from sa_utilities.pipeline.chunker import chunk_documents

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ADAPTERS = {
    "cps": CPSAdapter,
    "saws": SAWSAdapter,
    "cosa": CoSAAdapter,
}


def _save_json(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    logger.info(f"Saved {len(data)} records → {path}")


def _load_documents(source_name: str) -> list[SourceDocument]:
    """
    Reload previously saved raw documents from JSON.
    Used by --no-fetch mode to skip re-scraping.
    """
    path = RAW_DIR / f"{source_name}_documents.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No saved data found at {path}. " f"Run without --no-fetch first to populate it."
        )
    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    docs = []
    for r in records:
        r["source"] = Source(r["source"])
        r["doc_type"] = DocType(r["doc_type"])
        r.pop("embedding", None)
        docs.append(SourceDocument(**r))

    logger.info(f"Loaded {len(docs)} documents from {path}")
    return docs


def run(
    sources: list[str] | None = None,
    no_fetch: bool = False,
) -> tuple[list[SourceDocument], list[Chunk]]:
    """
    Run the full pipeline for the given sources (default: all).

    Args:
        sources:  List of source names to process. Defaults to all.
        no_fetch: If True, reload from saved JSON instead of hitting the web.

    Returns:
        (documents, chunks)
    """
    sources = sources or list(ADAPTERS.keys())
    all_docs = []
    all_chunks = []

    for source_name in sources:
        logger.info(f"\n{'='*50}")

        if no_fetch:
            logger.info(f"Loading cached data: {source_name.upper()}")
            logger.info(f"{'='*50}")
            try:
                docs = _load_documents(source_name)
            except FileNotFoundError as e:
                logger.error(str(e))
                continue
        else:
            logger.info(f"Running adapter: {source_name.upper()}")
            logger.info(f"{'='*50}")
            adapter = ADAPTERS[source_name]()
            docs = adapter.fetch_all()
            _save_json(RAW_DIR / f"{source_name}_documents.json", [asdict(d) for d in docs])

        all_docs.extend(docs)

    if not all_docs:
        logger.warning("No documents to process.")
        return [], []

    logger.info(f"\n{'='*50}")
    logger.info("Chunking all documents")
    logger.info(f"{'='*50}")

    all_chunks = chunk_documents(all_docs)

    # _save_json(CHUNK_DIR / "all_chunks.json", [
    #     {k: v for k, v in asdict(c).items() if k != "embedding"}
    #     for c in all_chunks
    # ])

    # Load any previously saved chunks for sources not in this run
    chunks_path = CHUNK_DIR / "all_chunks.json"
    existing_chunks = []
    if chunks_path.exists():
        with open(chunks_path, encoding="utf-8") as f:
            saved = json.load(f)
        # # Keep chunks from sources not being re-processed this run
        # existing_chunks = [
        #     c for c in saved
        #     if c["source"] not in [s for s in sources]
        # ]

        # Keep chunks whose source URL was not re-processed this run
        active_urls_this_run = {d.url for d in all_docs}
        existing_chunks = [c for c in saved if c["url"] not in active_urls_this_run]
        logger.info(f"Re-processed {len(active_urls_this_run)} URLs this run")
        logger.info(f"Retaining {len(existing_chunks)} chunks from previous runs")

        logger.info(f"Retaining {len(existing_chunks)} chunks from previous runs")

    # Merge with current run's chunks
    merged = existing_chunks + [
        {k: v for k, v in asdict(c).items() if k != "embedding"} for c in all_chunks
    ]
    _save_json(chunks_path, merged)

    logger.info("\n" + "=" * 50)
    logger.info("PIPELINE COMPLETE")
    logger.info("=" * 50)
    logger.info(f"  Mode       : {'cached' if no_fetch else 'live fetch'}")
    logger.info(f"  Sources    : {sources}")
    logger.info(f"  Documents  : {len(all_docs)}")
    logger.info(f"  Chunks     : {len(all_chunks)}")
    logger.info(f"  Raw JSON   : {RAW_DIR}")
    logger.info(f"  Chunks JSON: {CHUNK_DIR}")

    return all_docs, all_chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the SA utilities ingestion pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m sa_utilities.pipeline.runner
  python -m sa_utilities.pipeline.runner --sources cps saws
  python -m sa_utilities.pipeline.runner --no-fetch
  python -m sa_utilities.pipeline.runner --sources cps --no-fetch
        """,
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=list(ADAPTERS.keys()),
        help="Which adapters to run (default: all)",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip web fetching — reload from saved JSON and re-chunk only",
    )
    args = parser.parse_args()
    run(sources=args.sources, no_fetch=args.no_fetch)
