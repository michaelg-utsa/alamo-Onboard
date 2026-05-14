"""Unit tests for sa_utilities data models and config constants."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("ALAMO_DEMO_MODE", "1")
os.environ.setdefault("ALAMO_LLM_API_KEY", "")


class TestDocType:
    def test_enum_values_exist(self):
        from sa_utilities.models import DocType

        assert DocType.RATE.value == "rate"
        assert DocType.POLICY.value == "policy"
        assert DocType.SIGNUP.value == "signup"
        assert DocType.FEE.value == "fee"
        assert DocType.FAQ.value == "faq"
        assert DocType.ASSISTANCE.value == "assistance"
        assert DocType.GENERAL.value == "general"

    def test_enum_is_str(self):
        from sa_utilities.models import DocType

        assert isinstance(DocType.RATE, str)
        assert DocType.RATE == "rate"


class TestSource:
    def test_enum_values_exist(self):
        from sa_utilities.models import Source

        assert Source.CPS.value == "cps"
        assert Source.SAWS.value == "saws"
        assert Source.COSA.value == "cosa"

    def test_enum_is_str(self):
        from sa_utilities.models import Source

        assert isinstance(Source.CPS, str)


class TestSourceDocument:
    def _make(self, **kwargs):
        from sa_utilities.models import DocType, Source, SourceDocument

        defaults = dict(
            source=Source.CPS,
            doc_type=DocType.POLICY,
            title="Test Policy",
            url="https://example.com",
            content="Some content about CPS Energy policies.",
        )
        defaults.update(kwargs)
        return SourceDocument(**defaults)

    def test_creation_ok(self):
        doc = self._make()
        assert doc.title == "Test Policy"

    def test_char_count(self):
        doc = self._make(content="hello world")
        assert doc.char_count() == 11

    def test_empty_content_raises(self):
        with pytest.raises(ValueError, match="empty content"):
            self._make(content="")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty content"):
            self._make(content="   ")

    def test_repr_contains_source(self):
        doc = self._make()
        assert "cps" in repr(doc)

    def test_optional_effective_date(self):
        doc = self._make(effective_date="2024-01-01")
        assert doc.effective_date == "2024-01-01"

    def test_metadata_default_empty(self):
        doc = self._make()
        assert doc.metadata == {}

    def test_metadata_stored(self):
        doc = self._make(metadata={"key": "value"})
        assert doc.metadata["key"] == "value"


class TestChunk:
    def _make(self, **kwargs):
        from sa_utilities.models import Chunk, DocType, Source

        defaults = dict(
            chunk_id="cps_policy_0",
            source=Source.CPS,
            doc_type=DocType.POLICY,
            title="Test Policy",
            url="https://example.com",
            text="Chunk text here.",
            chunk_index=0,
        )
        defaults.update(kwargs)
        return Chunk(**defaults)

    def test_creation_ok(self):
        c = self._make()
        assert c.chunk_id == "cps_policy_0"

    def test_repr_has_id(self):
        c = self._make()
        assert "cps_policy_0" in repr(c)

    def test_embedding_default_none(self):
        c = self._make()
        assert c.embedding is None

    def test_embedding_can_be_set(self):
        c = self._make(embedding=[0.1, 0.2, 0.3])
        assert c.embedding == [0.1, 0.2, 0.3]


class TestSAUtilitiesConfig:
    def test_paths_exist_as_path_objects(self):
        from pathlib import Path

        from sa_utilities.config import CHUNK_DIR, PROJECT_ROOT, RAW_DIR

        assert isinstance(PROJECT_ROOT, Path)
        assert isinstance(RAW_DIR, Path)
        assert isinstance(CHUNK_DIR, Path)

    def test_crawl_delay_has_all_sources(self):
        from sa_utilities.config import CRAWL_DELAY

        assert "cps" in CRAWL_DELAY
        assert "saws" in CRAWL_DELAY
        assert "cosa" in CRAWL_DELAY

    def test_request_headers_has_user_agent(self):
        from sa_utilities.config import REQUEST_HEADERS

        assert "User-Agent" in REQUEST_HEADERS

    def test_chunk_config_defined(self):
        from sa_utilities.config import CHUNK_CONFIG

        assert isinstance(CHUNK_CONFIG, dict)
        # Should have at least one chunk size configured
        assert len(CHUNK_CONFIG) > 0

    def test_embedding_batch_size_positive(self):
        from sa_utilities.config import EMBEDDING_BATCH_SIZE

        assert isinstance(EMBEDDING_BATCH_SIZE, int)
        assert EMBEDDING_BATCH_SIZE > 0
