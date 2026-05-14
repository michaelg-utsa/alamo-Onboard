"""
models.py
---------
Shared data structures used across adapters and the pipeline.
Every adapter must output a list of SourceDocument objects.
The pipeline consumes SourceDocument and produces Chunk objects.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class DocType(StrEnum):
    RATE = "rate"  # Rate schedules, pricing tables
    POLICY = "policy"  # Terms, conditions, legal rules
    SIGNUP = "signup"  # New service / account setup info
    FEE = "fee"  # Miscellaneous charges and fees
    FAQ = "faq"  # FAQs and general info
    ASSISTANCE = "assistance"  # Affordability programs, financial aid
    GENERAL = "general"  # Catch-all


class Source(StrEnum):
    CPS = "cps"  # CPS Energy
    SAWS = "saws"  # San Antonio Water System
    COSA = "cosa"  # City of San Antonio (solid waste, library, etc.)


@dataclass
class SourceDocument:
    """
    Normalized output from any adapter.
    All fields except content and metadata are required.
    """

    source: Source
    doc_type: DocType
    title: str
    url: str
    content: str  # Clean extracted text, ready to chunk

    # Optional enrichment
    effective_date: str | None = None  # e.g. "February 1, 2024"
    metadata: dict = field(default_factory=dict)  # Adapter-specific extras

    def __post_init__(self):
        if not self.content or not self.content.strip():
            raise ValueError(f"SourceDocument '{self.title}' has empty content")

    def char_count(self) -> int:
        return len(self.content)

    def __repr__(self):
        return (
            f"SourceDocument(source={self.source.value!r}, "
            f"doc_type={self.doc_type.value!r}, "
            f"title={self.title!r}, "
            f"chars={self.char_count():,})"
        )


@dataclass
class Chunk:
    """
    A single embeddable unit produced by the chunker.
    Retains full provenance back to its SourceDocument.
    """

    chunk_id: str  # Unique ID: "{source}_{doc_type}_{index}"
    source: Source
    doc_type: DocType
    title: str  # Parent document title
    url: str  # Parent document URL
    text: str  # The chunk text that will be embedded
    chunk_index: int  # Position within parent document (0-based)

    # Set after embedding
    embedding: list | None = None

    def __repr__(self):
        return (
            f"Chunk(id={self.chunk_id!r}, " f"chars={len(self.text)}, " f"index={self.chunk_index})"
        )
