"""
pipeline/retriever.py
---------------------
Queries the ChromaDB vector index to retrieve relevant chunks for a
given user query.

Supports:
  - Basic semantic search (top-k most similar chunks)
  - Filtered search by source, doc_type, or eligibility_hints
    (useful for the second-level assistance eligibility module later)

The retriever is intentionally thin — it returns chunks with their
text and metadata, and leaves the LLM call to the agent layer.

Usage:
    from sa_utilities.pipeline.retriever import Retriever

    r = Retriever()

    # Basic search
    results = r.search("what is the monthly electric rate?", k=5)

    # Filtered search
    results = r.search(
        "what assistance programs are available?",
        k=5,
        filters={"doc_type": "assistance"},
    )

    for result in results:
        print(result.text)
        print(result.score)
        print(result.url)
"""

import logging
from dataclasses import dataclass

from sa_utilities.config import (
    CHROMA_COLLECTION,
    CHROMA_PATH,
    EMBEDDING_MODEL,
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieved chunk with its similarity score and metadata."""

    chunk_id: str
    text: str
    score: float  # cosine similarity (0-1, higher = more similar)
    source: str
    doc_type: str
    title: str
    url: str
    metadata: dict


class Retriever:
    """
    Semantic search over the ChromaDB chunk index.

    Initialising loads the embedding model and connects to ChromaDB.
    Keep a single instance alive for the duration of your agent session
    rather than creating one per query.
    """

    def __init__(self):
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

        if not CHROMA_PATH.exists():
            raise FileNotFoundError(
                f"ChromaDB not found at {CHROMA_PATH}. "
                f"Run the embedder first: "
                f"python -m sa_utilities.pipeline.embedder"
            )

        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        self._model = SentenceTransformer(EMBEDDING_MODEL)

        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = client.get_collection(CHROMA_COLLECTION)
        logger.info(f"Retriever ready — {self._collection.count()} chunks indexed")

    def search(
        self,
        query: str,
        k: int = 5,
        filters: dict | None = None,
    ) -> list[RetrievalResult]:
        """
        Retrieve the top-k most semantically similar chunks.

        Args:
            query:   The user's question or search string.
            k:       Number of results to return.
            filters: Optional ChromaDB where-clause for metadata filtering.
                     Examples:
                       {"doc_type": "assistance"}
                       {"source": "cps"}
                       {"source": {"$in": ["cps", "saws"]}}
                       {"eligibility_hints": {"$contains": "income-based"}}

        Returns:
            List of RetrievalResult sorted by descending similarity score.
        """
        query_embedding = self._model.encode(
            query,
            convert_to_numpy=True,
        ).tolist()

        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": k,
            "include": ["documents", "metadatas", "distances"],
        }
        if filters:
            query_kwargs["where"] = filters

        response = self._collection.query(**query_kwargs)

        results = []
        for i in range(len(response["ids"][0])):
            chunk_id = response["ids"][0][i]
            text = response["documents"][0][i]
            meta = response["metadatas"][0][i]
            # ChromaDB returns cosine distance (0=identical, 2=opposite)
            # Convert to similarity score (1=identical, 0=opposite)
            distance = response["distances"][0][i]
            score = 1.0 - (distance / 2.0)

            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    text=text,
                    score=round(score, 4),
                    source=meta.get("source", ""),
                    doc_type=meta.get("doc_type", ""),
                    title=meta.get("title", ""),
                    url=meta.get("url", ""),
                    metadata=meta,
                )
            )

        return results

    def search_assistance(
        self,
        query: str,
        k: int = 5,
    ) -> list[RetrievalResult]:
        """
        Convenience method: search only assistance program chunks.
        Used by the second-level eligibility module.
        """
        return self.search(query, k=k, filters={"doc_type": "assistance"})

    def collection_stats(self) -> dict:
        """Return basic stats about the indexed collection."""
        from collections import Counter

        all_items = self._collection.get(include=["metadatas"])
        sources = Counter(m["source"] for m in all_items["metadatas"])
        doc_types = Counter(m["doc_type"] for m in all_items["metadatas"])
        return {
            "total": self._collection.count(),
            "sources": dict(sources),
            "doc_types": dict(doc_types),
        }
