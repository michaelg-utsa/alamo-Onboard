"""Adapter that loads chunks + embeddings from the SA Utilities pipeline.

The SA Utilities sibling package produces two artifacts:

    sa_utilities/data/chunks/all_chunks.json
        List of chunk metadata dicts. Each dict has chunk_id, source,
        doc_type, title, url, text, and chunk_index. Embeddings are
        stored as null in this file.

    sa_utilities/data/chroma/
        ChromaDB persistent directory holding the actual embedding
        vectors, keyed by chunk_id.

This loader reads the JSON for metadata, then queries ChromaDB to fetch
the matching embedding for each chunk_id and assembles a (N, EMBED_DIM)
NumPy array aligned by row order with the chunk list.

The result feeds straight into our FAISS-backed VectorStore. From that
point on the SA Utilities ChromaDB is no longer touched at runtime --
all retrieval goes through our hybrid BM25 + FAISS pipeline.

This module is the single seam between the SA Utilities pipeline and
our retrieval layer. If SA Utilities changes its output format, this is
the only file that needs updating on our side.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config import (
    EMBED_DIM,
    SA_UTILITIES_CHROMA_PATH,
    SA_UTILITIES_CHUNKS_PATH,
    SA_UTILITIES_COLLECTION,
)
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# Short source codes in SA Utilities map to display names used throughout
# our pipeline (system prompt, citations, source_filter argument).
SOURCE_LABELS: dict[str, str] = {
    "cps": "CPS Energy",
    "saws": "SAWS",
    "cosa": "City of San Antonio",
    # Pre-normalized values pass through unchanged so this is idempotent.
    "CPS Energy": "CPS Energy",
    "SAWS": "SAWS",
    "City of San Antonio": "City of San Antonio",
}


@dataclass
class IndexedChunk:
    """One chunk after normalization. Aligned by index with the vector array."""

    chunk_id: str
    source: str  # display name, e.g. "CPS Energy"
    title: str
    url: str
    text: str
    doc_type: str = ""  # SA Utilities category, e.g. "rate", "policy"
    chunk_index: int = 0  # position within the original document

    def as_dict(self) -> dict:
        # Keys match what vector_store, retriever, and build_grounding_block expect.
        return {
            "doc_id": self.chunk_id,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "text": self.text,
            "doc_type": self.doc_type,
            "chunk_index": self.chunk_index,
        }


def _normalize_source(raw: str) -> str:
    if raw in SOURCE_LABELS:
        return SOURCE_LABELS[raw]
    logger.warning("unknown source label %r, passing through unchanged", raw)
    return raw


def _coerce_chunk(raw: dict) -> IndexedChunk:
    """Map a raw chunk dict to internal shape, tolerant to missing keys."""
    return IndexedChunk(
        chunk_id=str(raw.get("chunk_id") or raw.get("id") or raw.get("doc_id") or ""),
        source=_normalize_source(str(raw.get("source", "unknown"))),
        title=str(raw.get("title") or ""),
        url=str(raw.get("url") or ""),
        text=str(raw.get("text") or ""),
        doc_type=str(raw.get("doc_type") or ""),
        chunk_index=int(raw.get("chunk_index") or 0),
    )


def _load_chunks_json(path: Path) -> list[IndexedChunk]:
    """Read the SA Utilities all_chunks.json file."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{path} is empty")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: invalid JSON: {e}") from e

    if isinstance(data, dict) and "chunks" in data:
        data = data["chunks"]
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of chunk objects, got {type(data).__name__}")

    chunks = [_coerce_chunk(item) for item in data if isinstance(item, dict)]
    chunks = [c for c in chunks if c.chunk_id and c.text]  # drop any truncated rows

    # Dedupe by chunk_id. The SA Utilities pipeline can occasionally emit the
    # same chunk twice when the same source PDF is fetched via more than one
    # link path; ChromaDB rejects duplicate ids so we collapse them here.
    # Keep the first occurrence of each id.
    seen: set[str] = set()
    deduped: list[IndexedChunk] = []
    for c in chunks:
        if c.chunk_id in seen:
            continue
        seen.add(c.chunk_id)
        deduped.append(c)
    dropped = len(chunks) - len(deduped)
    if dropped:
        logger.info("dropped %d duplicate chunk_ids while loading %s", dropped, path)
    return deduped


def _fetch_embeddings_from_chroma(
    chunk_ids: list[str],
    chroma_path: Path,
    collection_name: str,
) -> np.ndarray:
    """Query ChromaDB for embeddings matching the given chunk_ids.

    Returns a (N, EMBED_DIM) float32 array in the same order as ``chunk_ids``.
    Raises if ChromaDB is missing, or if any chunk_id is not present in the
    collection (indicates the SA Utilities pipeline got out of sync).
    """
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as e:
        raise ImportError(
            "chromadb is required to read embeddings from the SA Utilities "
            "pipeline. Install it with: pip install chromadb"
        ) from e

    if not chroma_path.exists():
        raise FileNotFoundError(
            f"ChromaDB not found at {chroma_path}. "
            "Run the SA Utilities embedder first: "
            "python -m sa_utilities.pipeline.embedder"
        )

    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        collection = client.get_collection(collection_name)
    except Exception as e:
        raise RuntimeError(
            f"could not open ChromaDB collection {collection_name!r} at " f"{chroma_path}: {e}"
        ) from e

    # ChromaDB's get() with explicit ids preserves request order in the
    # response, but only for ids that exist. Any missing id is silently
    # dropped, so we have to validate after.
    response = collection.get(ids=chunk_ids, include=["embeddings"])
    returned_ids = response.get("ids") or []
    embeddings = response.get("embeddings")
    if embeddings is None or len(returned_ids) == 0:
        raise RuntimeError(f"ChromaDB returned no embeddings for {len(chunk_ids)} requested ids.")

    # Build a lookup so we can re-align in the original chunk order, even if
    # ChromaDB returned them in a different order.
    by_id = {cid: vec for cid, vec in zip(returned_ids, embeddings, strict=False)}
    missing = [cid for cid in chunk_ids if cid not in by_id]
    if missing:
        raise RuntimeError(
            f"{len(missing)} chunk_id(s) listed in the SA Utilities chunks "
            f"file are missing from ChromaDB. Re-run "
            f"'python -m sa_utilities.pipeline.embedder' to embed them. "
            f"First few missing: {missing[:5]}"
        )

    aligned = np.asarray([by_id[cid] for cid in chunk_ids], dtype=np.float32)
    return aligned


def _validate_dim(arr: np.ndarray) -> np.ndarray:
    if arr.ndim != 2:
        raise ValueError(f"expected a 2D embedding array, got shape {arr.shape}")
    if arr.shape[1] != EMBED_DIM:
        raise ValueError(
            f"embedding dimension mismatch: expected {EMBED_DIM}, got "
            f"{arr.shape[1]}. Update ALAMO_EMBED_MODEL and ALAMO_EMBED_DIM "
            f"to match the SA Utilities pipeline's embedding model."
        )
    return arr


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """Normalize each row to unit length so inner-product == cosine similarity.

    Idempotent: running it on already-normalized vectors is a no-op (within
    floating-point tolerance).
    """
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return vectors / norms


def load_sa_utilities_data(
    chunks_path: Path = SA_UTILITIES_CHUNKS_PATH,
    chroma_path: Path = SA_UTILITIES_CHROMA_PATH,
    collection_name: str = SA_UTILITIES_COLLECTION,
) -> tuple[list[IndexedChunk], np.ndarray]:
    """Load SA Utilities output and return (chunks, vectors) ready for indexing.

    Vectors are L2-normalized in place so the FAISS inner-product index
    behaves as cosine similarity.
    """
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"missing chunks file at {chunks_path}. Run the SA Utilities "
            f"pipeline first: python -m sa_utilities.pipeline.runner"
        )

    chunks = _load_chunks_json(chunks_path)
    if not chunks:
        raise ValueError(f"{chunks_path} contained no usable chunks")

    chunk_ids = [c.chunk_id for c in chunks]
    vectors = _fetch_embeddings_from_chroma(
        chunk_ids=chunk_ids,
        chroma_path=chroma_path,
        collection_name=collection_name,
    )
    vectors = _validate_dim(vectors)
    vectors = _l2_normalize(vectors)

    logger.info(
        "loaded SA Utilities data: %d chunks, vectors shape %s " "(chunks=%s, chroma=%s)",
        len(chunks),
        vectors.shape,
        chunks_path,
        chroma_path,
    )
    return chunks, vectors
