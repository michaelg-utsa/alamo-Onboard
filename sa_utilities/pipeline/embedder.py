"""
pipeline/embedder.py
--------------------
Embeds chunks with sentence-transformers and upserts them into ChromaDB.

Key design decisions:
  - Idempotent: re-running only updates chunks whose text has changed,
    identified by chunk_id. Safe to run after every pipeline run.
  - Batched: embeds in configurable batch sizes to avoid OOM on CPU.
  - Model-locked: embedding model is read from config so embedder and
    retriever are guaranteed to use the same model.
  - Metadata-rich: stores source, doc_type, title, url, and any
    eligibility_hints in ChromaDB metadata for filtered retrieval.

Usage:
    python -m sa_utilities.pipeline.embedder

    # Embed only specific sources
    python -m sa_utilities.pipeline.embedder --sources cps saws

    # Force re-embed everything even if unchanged
    python -m sa_utilities.pipeline.embedder --force
"""

import argparse
import json
import logging

from sa_utilities.config import (
    CHROMA_COLLECTION,
    CHROMA_PATH,
    CHUNK_DIR,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)


def _load_chunks(sources: list[str] | None = None) -> list[dict]:
    """Load chunks from the saved JSON file, optionally filtered by source."""
    path = CHUNK_DIR / "all_chunks.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No chunks found at {path}. "
            f"Run the pipeline first: python -m sa_utilities.pipeline.runner"
        )
    with open(path, encoding="utf-8") as f:
        chunks = json.load(f)

    if sources:
        chunks = [c for c in chunks if c["source"] in sources]
        logger.info(f"Filtered to {len(chunks)} chunks for sources: {sources}")

    return chunks


def _build_metadata(chunk: dict) -> dict:
    """
    Build the ChromaDB metadata dict for a chunk.
    ChromaDB only supports str, int, float, bool values — no nested dicts or lists.
    Flatten eligibility_hints list to a comma-separated string.
    """
    meta = {
        "source": chunk["source"],
        "doc_type": chunk["doc_type"],
        "title": chunk["title"],
        "url": chunk["url"],
        "chunk_index": chunk["chunk_index"],
    }

    # Flatten list metadata fields for ChromaDB compatibility
    raw_meta = chunk.get("metadata") or {}
    hints = raw_meta.get("eligibility_hints")
    if hints:
        meta["eligibility_hints"] = ",".join(hints)

    programs = raw_meta.get("programs")
    if programs:
        meta["programs"] = ",".join(programs)

    if raw_meta.get("last_changed"):
        meta["last_changed"] = raw_meta["last_changed"]

    if raw_meta.get("update_frequency"):
        meta["update_frequency"] = raw_meta["update_frequency"]

    return meta


def embed(
    sources: list[str] | None = None,
    force: bool = False,
) -> int:
    """
    Embed all chunks and upsert into ChromaDB.

    Args:
        sources: Limit to specific source names. None = all sources.
        force:   Re-embed all chunks even if already present in ChromaDB.

    Returns:
        Number of chunks upserted.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers not installed. " "Run: pip install sentence-transformers"
        ) from None

    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError:
        raise ImportError("chromadb not installed. " "Run: pip install chromadb") from None

    # --- Load chunks ---
    chunks = _load_chunks(sources)
    if not chunks:
        logger.warning("No chunks to embed.")
        return 0

    logger.info(f"Loaded {len(chunks)} chunks for embedding")

    # --- Load embedding model ---
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    # --- Connect to ChromaDB ---
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},  # cosine similarity for text
    )
    logger.info(f"ChromaDB collection '{CHROMA_COLLECTION}' at {CHROMA_PATH}")
    logger.info(f"Existing documents in collection: {collection.count()}")

    # --- Determine which chunks need embedding ---
    if force:
        to_embed = chunks
        logger.info("Force mode — re-embedding all chunks")
    else:
        # Check which chunk_ids are already in ChromaDB
        existing_ids = set()
        if collection.count() > 0:
            existing = collection.get(include=[])
            existing_ids = set(existing["ids"])

        to_embed = [c for c in chunks if c["chunk_id"] not in existing_ids]
        skipped = len(chunks) - len(to_embed)
        logger.info(
            f"Skipping {skipped} already-embedded chunks, "
            f"embedding {len(to_embed)} new/updated chunks"
        )

    if not to_embed:
        logger.info("Nothing to embed — collection is up to date.")
        return 0

    # --- Embed in batches and upsert ---
    total_upserted = 0
    texts = [c["text"] for c in to_embed]
    ids = [c["chunk_id"] for c in to_embed]
    metadatas = [_build_metadata(c) for c in to_embed]

    logger.info(f"Embedding {len(to_embed)} chunks in batches of {EMBEDDING_BATCH_SIZE}...")

    for batch_start in range(0, len(to_embed), EMBEDDING_BATCH_SIZE):
        batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, len(to_embed))
        batch_num = batch_start // EMBEDDING_BATCH_SIZE + 1
        total_batches = (len(to_embed) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE

        logger.info(f"  Batch {batch_num}/{total_batches} " f"(chunks {batch_start}–{batch_end})")

        batch_texts = texts[batch_start:batch_end]
        batch_ids = ids[batch_start:batch_end]
        batch_metadatas = metadatas[batch_start:batch_end]

        embeddings = model.encode(
            batch_texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).tolist()

        collection.upsert(
            ids=batch_ids,
            embeddings=embeddings,
            documents=batch_texts,
            metadatas=batch_metadatas,
        )
        total_upserted += len(batch_ids)

    logger.info(
        f"Embedding complete — {total_upserted} chunks upserted. "
        f"Collection now contains {collection.count()} documents."
    )
    return total_upserted


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Embed chunks and upsert into ChromaDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Embed all chunks
  python -m sa_utilities.pipeline.embedder

  # Embed only CPS chunks
  python -m sa_utilities.pipeline.embedder --sources cps

  # Force re-embed everything
  python -m sa_utilities.pipeline.embedder --force
        """,
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["cps", "saws", "cosa"],
        help="Limit to specific sources (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed all chunks even if already in ChromaDB",
    )
    args = parser.parse_args()
    embed(sources=args.sources, force=args.force)
