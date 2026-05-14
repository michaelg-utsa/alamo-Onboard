"""
tests/test_pipeline.py
----------------------
Unit tests for models, chunker, and adapter utilities.
Does NOT make live HTTP requests — uses fixtures for adapter tests.

Run with:
    python -m pytest sa_utilities/tests/test_pipeline.py -v
"""

import pytest
from sa_utilities.models import Chunk, DocType, Source, SourceDocument
from sa_utilities.pipeline.chunker import (
    _apply_overlap,
    _split_on_boundaries,
    _split_on_sentences,
    chunk_document,
    chunk_documents,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_doc(content: str, doc_type=DocType.RATE, title="Test Doc") -> SourceDocument:
    return SourceDocument(
        source=Source.CPS,
        doc_type=doc_type,
        title=title,
        url="https://example.com/test.pdf",
        content=content,
    )


RATE_CONTENT = """\
# Residential Electric Rate

SERVICE AVAILABILITY CHARGE
$ 9.50 per month

ENERGY CHARGE
$ 0.07503 Per kWh for all kWh

PEAK CAPACITY CHARGE
$ 0.02150 Per kWh for all kWh in excess of 600 kWh
Only applies during summer billing (June - September).

LATE PAYMENT CHARGE
Bills not paid on time will be charged an additional 2 percent.
"""

POLICY_CONTENT = """\
# Application for Service

An Applicant shall be required to provide one of the following forms of identification:
driver's license, state ID, social security number, or federal tax ID.

## Proof of Occupancy

CPS Energy may require an Applicant to produce verifiable proof of occupancy
before establishing service.

## Security Deposit

An Applicant may be required to submit a security deposit as a condition to receiving service.
The deposit amount is two times the estimated monthly bill for the premises.
"""


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestSourceDocument:
    def test_valid_creation(self):
        doc = make_doc("Some content here")
        assert doc.source == Source.CPS
        assert doc.char_count() == len("Some content here")

    def test_empty_content_raises(self):
        with pytest.raises(ValueError, match="empty content"):
            make_doc("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty content"):
            make_doc("   \n\n  ")

    def test_repr(self):
        doc = make_doc("hello world")
        r = repr(doc)
        assert "cps" in r
        assert "rate" in r


class TestChunk:
    def test_chunk_creation(self):
        chunk = Chunk(
            chunk_id="cps__test__0000",
            source=Source.CPS,
            doc_type=DocType.RATE,
            title="Test",
            url="https://example.com",
            text="Some text here",
            chunk_index=0,
        )
        assert chunk.embedding is None
        assert "0000" in repr(chunk)


# ---------------------------------------------------------------------------
# Chunker unit tests
# ---------------------------------------------------------------------------


class TestSplitOnBoundaries:
    def test_splits_on_headings(self):
        text = "Intro text.\n# Section One\nContent one.\n## Section Two\nContent two."
        parts = _split_on_boundaries(text)
        assert len(parts) >= 2
        assert any("Section One" in p for p in parts)
        assert any("Section Two" in p for p in parts)

    def test_splits_on_double_newlines(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        parts = _split_on_boundaries(text)
        assert len(parts) == 3

    def test_no_empty_sections(self):
        text = "Para one.\n\n\n\nPara two."
        parts = _split_on_boundaries(text)
        assert all(p.strip() for p in parts)


class TestSplitOnSentences:
    def test_respects_max_size(self):
        long_text = "This is a sentence. " * 50  # ~1000 chars
        chunks = _split_on_sentences(long_text, max_size=200)
        assert all(len(c) <= 300 for c in chunks)  # some slack for joining

    def test_single_short_text(self):
        text = "Short sentence."
        chunks = _split_on_sentences(text, max_size=200)
        assert chunks == ["Short sentence."]


class TestApplyOverlap:
    def test_prepends_tail(self):
        chunks = ["First chunk content here.", "Second chunk content.", "Third."]
        result = _apply_overlap(chunks, overlap=10)
        assert result[0] == "First chunk content here."
        assert "here." in result[1]  # tail of first chunk prepended

    def test_single_chunk_unchanged(self):
        chunks = ["Only one chunk."]
        result = _apply_overlap(chunks, overlap=50)
        assert result == chunks


class TestChunkDocument:
    def test_rate_doc_produces_chunks(self):
        doc = make_doc(RATE_CONTENT, doc_type=DocType.RATE)
        chunks = chunk_document(doc)
        assert len(chunks) >= 1
        # Every chunk should contain the document title
        for c in chunks:
            assert doc.title in c.text

    def test_policy_doc_produces_chunks(self):
        doc = make_doc(POLICY_CONTENT, doc_type=DocType.POLICY)
        chunks = chunk_document(doc)
        assert len(chunks) >= 1

    def test_chunk_ids_are_unique(self):
        doc = make_doc(RATE_CONTENT * 10, doc_type=DocType.RATE)  # force many chunks
        chunks = chunk_document(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_indices_are_sequential(self):
        doc = make_doc(RATE_CONTENT * 10, doc_type=DocType.RATE)
        chunks = chunk_document(doc)
        for i, c in enumerate(chunks):
            assert c.chunk_index == i

    def test_key_numbers_survive_chunking(self):
        doc = make_doc(RATE_CONTENT, doc_type=DocType.RATE)
        chunks = chunk_document(doc)
        all_text = " ".join(c.text for c in chunks)
        assert "0.07503" in all_text
        assert "9.50" in all_text
        assert "0.02150" in all_text

    def test_policy_terms_survive_chunking(self):
        doc = make_doc(POLICY_CONTENT, doc_type=DocType.POLICY)
        chunks = chunk_document(doc)
        all_text = " ".join(c.text for c in chunks)
        assert "driver's license" in all_text
        assert "security deposit" in all_text


class TestChunkDocuments:
    def test_multiple_docs(self):
        docs = [
            make_doc(RATE_CONTENT, doc_type=DocType.RATE, title="Rate Doc"),
            make_doc(POLICY_CONTENT, doc_type=DocType.POLICY, title="Policy Doc"),
        ]
        chunks = chunk_documents(docs)
        assert len(chunks) > 0

        sources = {c.source for c in chunks}
        assert Source.CPS in sources

    def test_empty_list(self):
        chunks = chunk_documents([])
        assert chunks == []
