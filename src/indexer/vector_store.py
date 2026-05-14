"""FAISS-backed vector store with JSON metadata sidecar.

Stored on disk as two files: ``index.faiss`` (the FAISS index) and
``meta.json`` (a list of chunk-metadata dicts, parallel to the FAISS rows).
The schema is intentionally simple so the index can be inspected by hand.

Vectors are expected to be L2-normalized before being added so that the
inner-product index behaves as cosine similarity. The ``loaders`` module
handles that normalization upstream in the loader.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from config import INDEX_DIR
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class VectorStore:
    """Inner-product FAISS index over normalized vectors (== cosine similarity)."""

    def __init__(self, index_dir: Path = INDEX_DIR):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.index_dir / "index.faiss"
        self.meta_path = self.index_dir / "meta.json"
        self._index = None
        self._meta: list[dict] = []

    # build
    def build(self, vectors: np.ndarray, metadata: Sequence[dict]) -> None:
        """Construct the FAISS index from pre-computed vectors + metadata.

        Parameters
        ----------
        vectors : np.ndarray
            Shape ``(N, dim)`` array of L2-normalized float32 vectors.
        metadata : Sequence[dict]
            ``N`` dicts, each describing the chunk at the same row index.
            Required keys: ``doc_id``, ``source``, ``title``, ``url``,
            ``text``. Optional: ``doc_type``, ``chunk_index``.
        """
        import faiss

        if vectors.shape[0] != len(metadata):
            raise ValueError(
                f"vector/metadata length mismatch: "
                f"{vectors.shape[0]} vectors vs {len(metadata)} metadata entries"
            )
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)

        dim = int(vectors.shape[1])
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
        self._index = index
        self._meta = list(metadata)
        self.save()
        logger.info("built FAISS index: %d vectors x %d dim", vectors.shape[0], dim)

    def save(self) -> None:
        import faiss

        if self._index is None:
            raise RuntimeError("nothing to save: index not built")
        faiss.write_index(self._index, str(self.index_path))
        self.meta_path.write_text(
            json.dumps(self._meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # load
    def load(self) -> bool:
        import faiss

        if not (self.index_path.exists() and self.meta_path.exists()):
            return False
        self._index = faiss.read_index(str(self.index_path))
        self._meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        return True

    # search
    def search(self, query_vec: np.ndarray, k: int = 5) -> list[tuple[float, dict]]:
        if self._index is None:
            raise RuntimeError("index not loaded")
        if query_vec.ndim == 1:
            query_vec = query_vec.reshape(1, -1)
        if query_vec.dtype != np.float32:
            query_vec = query_vec.astype(np.float32)
        scores, idxs = self._index.search(query_vec, k)
        out: list[tuple[float, dict]] = []
        for score, idx in zip(scores[0], idxs[0], strict=False):
            if idx < 0 or idx >= len(self._meta):
                continue
            out.append((float(score), self._meta[idx]))
        return out

    # info
    def __len__(self) -> int:
        return len(self._meta)
