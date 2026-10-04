"""Qdrant persistence adapter for RAG chunk embeddings (P69).

Replaces the former pgvector adapter behind the same three-method surface.
The store is scope-blind: points carry only the chunk ID payload, and hard
scope isolation stays with the PostgreSQL registry join in the read path.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import httpx
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http import exceptions as _qdrant_http

COLLECTION_NAME = "rag_vectors"


class VectorStoreUnavailable(RuntimeError):
    """Raised when Qdrant cannot execute a vector operation."""


class QdrantVectorStore:
    """Persist and retrieve fixed-dimension vectors in one Qdrant collection."""

    def __init__(self, url: str, dim: int = 512, collection: str = COLLECTION_NAME) -> None:
        """Bind the Qdrant endpoint and expected embedding dimension."""
        if dim <= 0:
            raise ValueError("vector dimension must be positive")
        if not url.strip():
            raise ValueError("Qdrant URL must not be empty")
        self._client = AsyncQdrantClient(url=url, prefer_grpc=False, timeout=30)
        self._dim = dim
        self._collection = collection
        self._collection_ready = False

    async def upsert(self, chunk_id: str, embedding: Sequence[float]) -> None:
        """Store or update one embedding under its deterministic point ID."""
        if len(embedding) != self._dim:
            raise ValueError(f"embedding must contain {self._dim} dimensions")
        await self._ensure_collection()
        try:
            await self._client.upsert(
                collection_name=self._collection,
                points=[
                    models.PointStruct(
                        id=_point_id(chunk_id),
                        vector=list(embedding),
                        payload={"chunk_id": chunk_id},
                    )
                ],
            )
        except (
            _qdrant_http.ApiException,
            _qdrant_http.ResponseHandlingException,
            httpx.HTTPError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VectorStoreUnavailable("qdrant upsert is unavailable") from exc

    async def delete(self, chunk_id: str) -> None:
        """Remove one embedding without querying for its point ID."""
        await self._ensure_collection()
        try:
            await self._client.delete(
                collection_name=self._collection,
                points_selector=models.PointIdsList(points=[_point_id(chunk_id)]),
            )
        except (
            _qdrant_http.ApiException,
            _qdrant_http.ResponseHandlingException,
            httpx.HTTPError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VectorStoreUnavailable("qdrant delete is unavailable") from exc

    async def top_k(self, query: Sequence[float], k: int = 20) -> list[tuple[str, float]]:
        """Return nearest chunk IDs and cosine distances in ascending order."""
        if len(query) != self._dim:
            raise ValueError(f"query must contain {self._dim} dimensions")
        if k < 1:
            return []
        await self._ensure_collection()
        try:
            # Exact search is the documented operating point below 100k vectors;
            # ANN becomes an explicit ADR amendment above that threshold.
            response = await self._client.query_points(
                collection_name=self._collection,
                query=list(query),
                limit=k,
                search_params=models.SearchParams(exact=True),
                with_payload=True,
            )
        except (
            _qdrant_http.ApiException,
            _qdrant_http.ResponseHandlingException,
            httpx.HTTPError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VectorStoreUnavailable("qdrant search is unavailable") from exc
        return [
            (str(point.payload["chunk_id"]), 1.0 - float(point.score))
            for point in response.points
            if isinstance(point.payload, dict) and "chunk_id" in point.payload
        ]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    async def count(self) -> int:
        """Return the number of stored points (drift reconciliation helper)."""
        await self._ensure_collection()
        try:
            response = await self._client.count(collection_name=self._collection, exact=True)
        except (
            _qdrant_http.ApiException,
            _qdrant_http.ResponseHandlingException,
            httpx.HTTPError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VectorStoreUnavailable("qdrant count is unavailable") from exc
        return int(response.count)

    async def _ensure_collection(self) -> None:
        """Create the collection lazily with the configured cosine space."""
        if self._collection_ready:
            return
        try:
            if not await self._client.collection_exists(collection_name=self._collection):
                await self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=models.VectorParams(
                        size=self._dim,
                        distance=models.Distance.COSINE,
                    ),
                )
        except (
            _qdrant_http.ApiException,
            _qdrant_http.ResponseHandlingException,
            httpx.HTTPError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            raise VectorStoreUnavailable("qdrant collection init is unavailable") from exc
        self._collection_ready = True


def _point_id(chunk_id: str) -> str:
    """Derive the deterministic point ID so upsert is idempotent and delete is direct."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


__all__ = ["COLLECTION_NAME", "QdrantVectorStore", "VectorStoreUnavailable"]
