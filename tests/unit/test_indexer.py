"""Unit tests for src/indexer/* — embedder, vector_store, retriever, loaders.

These tests use mocks/stubs to avoid requiring FAISS, sentence-transformers,
or a live ChromaDB to be fully loaded. They verify the public API contracts
and wiring between components.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

os.environ.setdefault("ALAMO_DEMO_MODE", "1")
os.environ.setdefault("ALAMO_LLM_API_KEY", "")


# ---------------------------------------------------------------------------
# RetrievedPassage dataclass
# ---------------------------------------------------------------------------


class TestRetrievedPassage:
    def _make(self, **kwargs):
        from src.indexer.retriever import RetrievedPassage

        defaults = dict(
            text="CPS requires a $200 deposit.",
            title="New Service Deposit",
            source="CPS Energy",
            url="https://cpsenergy.com/deposit",
            score=0.9,
        )
        defaults.update(kwargs)
        return RetrievedPassage(**defaults)

    def test_creation(self):
        p = self._make()
        assert p.text
        assert p.score == 0.9

    def test_citation_format(self):
        p = self._make()
        citation = p.citation()
        assert "CPS Energy" in citation
        assert "New Service Deposit" in citation


# ---------------------------------------------------------------------------
# Tokenizer (used by BM25)
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_splits_words(self):
        from src.indexer.retriever import _tokenize

        tokens = _tokenize("hello world")
        assert tokens == ["hello", "world"]

    def test_lowercase(self):
        from src.indexer.retriever import _tokenize

        tokens = _tokenize("CPS ENERGY")
        assert "cps" in tokens
        assert "energy" in tokens

    def test_strips_punctuation(self):
        from src.indexer.retriever import _tokenize

        tokens = _tokenize("hello, world!")
        assert "hello" in tokens
        assert "world" in tokens

    def test_empty_string(self):
        from src.indexer.retriever import _tokenize

        tokens = _tokenize("")
        assert tokens == []

    def test_non_ascii(self):
        from src.indexer.retriever import _tokenize

        tokens = _tokenize("café résumé")
        assert len(tokens) >= 1


# ---------------------------------------------------------------------------
# Embedder (lazy-loaded, so we mock SentenceTransformer)
# ---------------------------------------------------------------------------


class TestEmbedder:
    def test_encode_returns_numpy_array(self):
        from src.indexer.embedder import Embedder

        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
            mock_st.return_value = mock_model
            emb = Embedder()
            emb._model = mock_model  # inject directly to bypass lazy load
            result = emb.encode(["test sentence"])
            assert isinstance(result, np.ndarray)

    def test_encode_single_string(self):
        from src.indexer.embedder import Embedder

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.5, 0.5]])
        emb = Embedder()
        emb._model = mock_model
        result = emb.encode("single string")
        assert result is not None


# ---------------------------------------------------------------------------
# VectorStore — build, save, load, search
# ---------------------------------------------------------------------------


class TestVectorStore:
    def test_init_creates_directory(self, tmp_path):
        store_dir = tmp_path / "index"
        from src.indexer.vector_store import VectorStore

        VectorStore(index_dir=store_dir)
        assert store_dir.exists()

    def test_build_and_meta_populated(self, tmp_path):
        try:
            import faiss  # noqa: F401
        except ImportError:
            pytest.skip("faiss not installed")
        from src.indexer.vector_store import VectorStore

        store = VectorStore(index_dir=tmp_path / "vs")
        dim = 4
        vecs = np.random.randn(5, dim).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        meta = [
            {
                "doc_id": f"c{i}",
                "source": "cps",
                "title": f"Doc {i}",
                "url": "https://x.com",
                "text": f"text {i}",
                "chunk_index": i,
            }
            for i in range(5)
        ]
        store.build(vecs, meta)
        assert store._index is not None
        assert len(store._meta) == 5

    def test_search_returns_list(self, tmp_path):
        try:
            import faiss  # noqa: F401
        except ImportError:
            pytest.skip("faiss not installed")
        from src.indexer.vector_store import VectorStore

        store = VectorStore(index_dir=tmp_path / "vs2")
        dim = 4
        vecs = np.random.randn(10, dim).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        meta = [
            {
                "doc_id": f"c{i}",
                "source": "cps",
                "title": f"Doc {i}",
                "url": "https://x.com",
                "text": f"text {i}",
                "chunk_index": i,
            }
            for i in range(10)
        ]
        store.build(vecs, meta)
        query = np.random.randn(1, dim).astype(np.float32)
        query = query / np.linalg.norm(query, axis=1, keepdims=True)
        results = store.search(query, k=3)
        assert isinstance(results, list)

    def test_len_after_build(self, tmp_path):
        try:
            import faiss  # noqa: F401
        except ImportError:
            pytest.skip("faiss not installed")
        from src.indexer.vector_store import VectorStore

        store = VectorStore(index_dir=tmp_path / "vs3")
        dim = 4
        vecs = np.random.randn(3, dim).astype(np.float32)
        vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        meta = [
            {
                "doc_id": f"c{i}",
                "source": "x",
                "title": "t",
                "url": "u",
                "text": "t",
                "chunk_index": i,
            }
            for i in range(3)
        ]
        store.build(vecs, meta)
        assert len(store) == 3

    def test_empty_store_len_zero(self, tmp_path):
        from src.indexer.vector_store import VectorStore

        store = VectorStore(index_dir=tmp_path / "vs4")
        assert len(store) == 0


# ---------------------------------------------------------------------------
# IndexedChunk from loaders
# ---------------------------------------------------------------------------


class TestIndexedChunk:
    def test_creation_and_as_dict(self):
        from src.indexer.loaders import IndexedChunk

        c = IndexedChunk(
            chunk_id="cps_0",
            source="CPS Energy",
            title="Deposit Policy",
            url="https://cpsenergy.com",
            text="CPS Energy deposit info.",
        )
        d = c.as_dict()
        assert d["doc_id"] == "cps_0"
        assert d["source"] == "CPS Energy"
        assert d["text"] == "CPS Energy deposit info."

    def test_optional_fields_default(self):
        from src.indexer.loaders import IndexedChunk

        c = IndexedChunk(chunk_id="x", source="s", title="t", url="u", text="text")
        assert c.doc_type == ""
        assert c.chunk_index == 0


# ---------------------------------------------------------------------------
# HybridRetriever — empty index returns [] without crashing
# ---------------------------------------------------------------------------


class TestHybridRetrieverEmptyIndex:
    def test_search_empty_returns_empty(self):
        from src.indexer.retriever import HybridRetriever

        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever._bm25 = None
        retriever._meta = []
        retriever._tokenized = []
        retriever.embedder = MagicMock()
        mock_store = MagicMock()
        mock_store.__len__ = MagicMock(return_value=0)
        retriever.store = mock_store
        results = retriever.search("What is the CPS deposit?")
        assert results == []

    def test_find_meta_index_miss(self):
        from src.indexer.retriever import HybridRetriever

        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever._meta = [{"doc_id": "a", "chunk_index": 0}]
        idx = retriever._find_meta_index({"doc_id": "b", "chunk_index": 0})
        assert idx == -1

    def test_find_meta_index_hit(self):
        from src.indexer.retriever import HybridRetriever

        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever._meta = [{"doc_id": "a", "chunk_index": 0}]
        idx = retriever._find_meta_index({"doc_id": "a", "chunk_index": 0})
        assert idx == 0
