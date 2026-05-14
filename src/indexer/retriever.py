"""Hybrid retriever: BM25 keyword + dense FAISS search, fused by score.

Pre-computed dense vectors are loaded from disk. BM25 is layered on top of
the same chunk text so keyword-heavy queries like "REAP" or "210-353-2222"
and semantic queries like "how much do I owe upfront" both work well.

Reciprocal rank fusion merges the two ranked lists. It is simple and requires
no score calibration between BM25 (unbounded) and cosine similarity (bounded).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from config import TOP_K
from src.indexer.embedder import Embedder
from src.indexer.loaders import IndexedChunk, load_sa_utilities_data
from src.indexer.vector_store import VectorStore
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievedPassage:
    """One retrieved passage with provenance."""

    text: str
    title: str
    source: str
    url: str
    score: float

    def citation(self) -> str:
        return f"{self.source} - {self.title} ({self.url})"


def _tokenize(text: str) -> list[str]:
    """Cheap whitespace + alphanumeric tokenizer for BM25."""
    return [w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if w]


class HybridRetriever:
    """BM25 + dense retrieval with reciprocal rank fusion."""

    def __init__(self) -> None:
        self.embedder = Embedder()
        self.store = VectorStore()
        self._bm25 = None
        self._tokenized: list[list[str]] = []
        self._meta: list[dict] = []

    # build
    def build_from_sa_utilities(self) -> None:
        """Load chunks + vectors from the SA Utilities pipeline and build both indexes.

        Dense vectors are loaded directly without re-embedding. BM25 is built
        from chunk text locally since it's fast and doesn't benefit from
        precomputation.
        """
        chunks, vectors = load_sa_utilities_data()
        metadata = [c.as_dict() for c in chunks]
        self.store.build(vectors, metadata)
        self._init_bm25(chunks)

    # load
    def load(self) -> bool:
        """Reload a previously-built index from disk."""
        if not self.store.load():
            return False
        # Reconstruct lightweight chunk objects for BM25 init.
        chunks = [
            IndexedChunk(
                chunk_id=m.get("doc_id", ""),
                source=m.get("source", ""),
                title=m.get("title", ""),
                url=m.get("url", ""),
                text=m.get("text", ""),
                doc_type=m.get("doc_type", ""),
                chunk_index=int(m.get("chunk_index") or 0),
            )
            for m in self.store._meta  # noqa: SLF001 (intentional)
        ]
        self._init_bm25(chunks)
        return True

    def _init_bm25(self, chunks: Sequence[IndexedChunk]) -> None:
        from rank_bm25 import BM25Okapi

        self._meta = [c.as_dict() for c in chunks]
        self._tokenized = [_tokenize(c.text) for c in chunks]
        self._bm25 = BM25Okapi(self._tokenized) if self._tokenized else None

    # search
    def search(
        self,
        query: str,
        k: int = TOP_K,
        source_filter: Iterable[str] | None = None,
    ) -> list[RetrievedPassage]:
        """Hybrid search.

        Parameters
        ----------
        query : str
            Natural-language search query.
        k : int
            Number of passages to return.
        source_filter : iterable of str, optional
            If provided, restrict results to chunks whose ``source`` matches
            one of the given values. Use the display names: ``"CPS Energy"``,
            ``"SAWS"``, ``"City of San Antonio"``. Pass ``None`` (default) to
            search across all sources and let ranking decide.
        """
        if self._bm25 is None or len(self.store) == 0:
            return []

        allowed: set[str] | None = {s for s in source_filter} if source_filter else None

        # We pull more than k from each side because the fusion may drop dups
        # and because filtering may discard some. 2*k is a reasonable buffer.
        q_vec = self.embedder.encode([query])
        dense_hits = self.store.search(q_vec, k=k * 2)

        bm25_scores = self._bm25.get_scores(_tokenize(query))
        bm25_top = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[
            : k * 2
        ]

        rrf: dict[int, float] = {}
        meta_lookup: dict[int, dict] = {}

        for rank, (_score, m) in enumerate(dense_hits):
            idx = self._find_meta_index(m)
            if idx >= 0:
                rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (60 + rank)
                meta_lookup[idx] = m

        for rank, idx in enumerate(bm25_top):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (60 + rank)
            meta_lookup[idx] = self._meta[idx]

        ordered = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)
        results: list[RetrievedPassage] = []
        for idx, score in ordered:
            m = meta_lookup[idx]
            if allowed is not None and m.get("source") not in allowed:
                continue
            results.append(
                RetrievedPassage(
                    text=m["text"],
                    title=m["title"],
                    source=m["source"],
                    url=m["url"],
                    score=score,
                )
            )
            if len(results) >= k:
                break
        return results

    def _find_meta_index(self, target: dict) -> int:
        """Locate a metadata dict in self._meta. Returns -1 if missing."""
        target_id = target.get("doc_id")
        target_idx = target.get("chunk_index")
        for i, m in enumerate(self._meta):
            if m.get("doc_id") == target_id and m.get("chunk_index") == target_idx:
                return i
        return -1
