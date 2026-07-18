"""Shared local embedding providers for indexing, retrieval, and evaluation."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Sequence

from forge.config import EMBEDDING_MODEL, EMBEDDING_PROVIDER


QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingProviderError(RuntimeError):
    """Raised when the configured local embedding provider cannot be loaded."""


class LocalEmbeddingService:
    """Lazy wrapper around one locally loaded SentenceTransformer model."""

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingProviderError(
                "Sentence Transformers is not installed. Run: pip install -r requirements.txt"
            ) from exc
        try:
            try:
                self.model = SentenceTransformer(model_name, local_files_only=True)
            except Exception:
                self.model = SentenceTransformer(model_name)
        except Exception as exc:
            raise EmbeddingProviderError(f"Could not load local embedding model '{model_name}'.") from exc
        dimension_method = getattr(self.model, "get_embedding_dimension", self.model.get_sentence_embedding_dimension)
        dimension = dimension_method()
        if not dimension:
            raise EmbeddingProviderError(f"Embedding model '{model_name}' did not report a dimension.")
        self.model_name = model_name
        self.dimension = int(dimension)

    def _encode(self, texts: Sequence[str], batch_size: int) -> list[list[float]]:
        """Encode texts locally and return JSON/Chroma-compatible vectors."""
        values = self.model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return values.tolist()

    def embed_documents(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        """Encode retrieval documents without the query instruction prefix."""
        return self._encode(texts, batch_size)

    def embed_query(self, query: str) -> list[float]:
        """Encode a search query using the BGE retrieval instruction."""
        return self._encode([QUERY_PREFIX + query], 1)[0]


@lru_cache(maxsize=8)
def get_embedding_service(provider: str = EMBEDDING_PROVIDER, model_name: str = EMBEDDING_MODEL) -> Any:
    """Return one cached embedding service for the configured provider/model pair."""
    normalized_provider = provider.strip().lower()
    if normalized_provider == "huggingface":
        return LocalEmbeddingService(model_name)
    raise EmbeddingProviderError(f"Unsupported embedding provider '{provider}'.")
