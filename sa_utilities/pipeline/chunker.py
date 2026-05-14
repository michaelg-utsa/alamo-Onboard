"""
pipeline/chunker.py
-------------------
Converts SourceDocument objects into Chunk objects ready for embedding.

Strategy:
  - Split on natural section boundaries (double newlines, headings) first
  - Fall back to sentence-aware splitting if sections are too large
  - Apply overlap so context isn't lost at chunk boundaries
  - Rate/fee docs get smaller chunks (more precise retrieval)
  - Policy docs get larger chunks (preserve legal context)

Usage:
    from sa_utilities.pipeline.chunker import chunk_documents
    chunks = chunk_documents(documents)
"""

import logging
import re

from sa_utilities.config import CHUNK_CONFIG
from sa_utilities.models import Chunk, SourceDocument

logger = logging.getLogger(__name__)


def _split_on_boundaries(text: str) -> list[str]:
    """
    Split text on natural section boundaries:
    - Markdown-style headings (# or ##)
    - Double newlines (paragraph breaks)
    Returns a list of non-empty section strings.
    """
    # Split on headings first
    sections = re.split(r"\n(?=#{1,3}\s)", text)

    # Further split all sections on double newlines (paragraph breaks)
    refined = []
    for section in sections:
        subsections = re.split(r"\n{2,}", section)
        refined.extend(subsections)

    return [s.strip() for s in refined if s.strip()]


def _split_on_sentences(text: str, max_size: int) -> list[str]:
    """
    Split a text block into sentence-respecting chunks of at most max_size chars.
    Splits on '. ', '.\n', '! ', '? ' boundaries.
    """
    sentence_endings = re.compile(r"(?<=[.!?])\s+")
    sentences = sentence_endings.split(text)

    chunks = []
    current = []
    current_len = 0

    for sentence in sentences:
        if current_len + len(sentence) > max_size and current:
            chunks.append(" ".join(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += len(sentence)

    if current:
        chunks.append(" ".join(current))

    return chunks


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    """
    Prepend a tail from the previous chunk to each chunk.
    This ensures context isn't lost at split boundaries.
    """
    if len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        tail = chunks[i - 1][-overlap:].strip()
        result.append(tail + " " + chunks[i] if tail else chunks[i])

    return result


def _make_chunk_id(doc: SourceDocument, index: int) -> str:
    """Generate a stable, readable chunk ID."""
    safe_title = re.sub(r"[^a-z0-9]", "_", doc.title.lower())[:40]
    return f"{doc.source.value}__{safe_title}__{index:04d}"


def chunk_document(doc: SourceDocument) -> list[Chunk]:
    """
    Chunk a single SourceDocument into a list of Chunk objects.
    """
    config = CHUNK_CONFIG[doc.doc_type]
    max_size = config["max_size"]
    overlap = config["overlap"]

    # Step 1: Split on natural section boundaries
    sections = _split_on_boundaries(doc.content)

    # Step 2: Further split any sections that exceed max_size
    fine_chunks = []
    for section in sections:
        if len(section) <= max_size:
            fine_chunks.append(section)
        else:
            fine_chunks.extend(_split_on_sentences(section, max_size))

    # Step 3: Apply overlap
    overlapped = _apply_overlap(fine_chunks, overlap)

    # Step 3.5: Drop chunks that are title-only (no content beyond the heading)
    # These occur when a page heading lands in its own split with nothing below it
    overlapped = [c for c in overlapped if len(c.strip()) > 81]

    if not overlapped:
        logger.debug(f"No content chunks produced for '{doc.title}' after filtering")
        return []

    # Step 4: Prepend document title to every chunk for retrieval context
    titled = [f"[{doc.title}]\n{c}" for c in overlapped]

    # Step 5: Build Chunk objects
    chunks = []
    for i, text in enumerate(titled):
        chunk = Chunk(
            chunk_id=_make_chunk_id(doc, i),
            source=doc.source,
            doc_type=doc.doc_type,
            title=doc.title,
            url=doc.url,
            text=text,
            chunk_index=i,
        )
        chunks.append(chunk)

    logger.debug(
        f"Chunked '{doc.title}' → {len(chunks)} chunks "
        f"(avg {sum(len(c.text) for c in chunks)//len(chunks)} chars)"
    )
    return chunks


def chunk_documents(documents: list[SourceDocument]) -> list[Chunk]:
    """
    Chunk all documents and return a flat list of Chunk objects.
    """
    all_chunks = []
    for doc in documents:
        chunks = chunk_document(doc)
        all_chunks.extend(chunks)

    total_chars = sum(len(c.text) for c in all_chunks)
    logger.info(
        f"Chunker: {len(documents)} docs → {len(all_chunks)} chunks "
        f"({total_chars:,} total chars)"
    )
    return all_chunks
