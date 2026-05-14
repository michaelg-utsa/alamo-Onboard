"""Sentence-transformers embedder wrapper with lazy loading."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from config import EMBED_MODEL
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


class Embedder:
    """Thin wrapper around sentence-transformers with lazy model loading."""

    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name
        self._model = None  # lazy

    @property
    def model(self):
        if self._model is None:
            logger.info("loading embedding model %s", self.model_name)
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dim(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def encode(self, texts: Iterable[str], normalize: bool = True) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        return vecs.astype(np.float32)
