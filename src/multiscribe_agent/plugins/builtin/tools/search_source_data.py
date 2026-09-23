"""Tool for searching ingested SourceData through the P66 RAG service."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import ClassVar

from multiscribe_agent.domain.models import PluginMetadata, UnifiedData
from multiscribe_agent.memory.memory_service import MemoryService
from multiscribe_agent.memory.preference_store import DEFAULT_PREFERENCES, UserPreferences
from multiscribe_agent.plugins.base import BaseTool
from multiscribe_agent.rag.models import RetrievalScope, RetrievedEvidence
from multiscribe_agent.rag.ports import RagServiceProtocol
from multiscribe_agent.services.candidate_filter import CandidateFilter

DEFAULT_RESULT_LIMIT = 8
MAX_RESULT_LIMIT = 20
FETCH_MULTIPLIER = 3
SUMMARY_CHAR_LIMIT = 150


class SearchSourceDataTool(BaseTool):
    """Search SourceData via RagService and apply the shared candidate filter."""

    id: ClassVar[str] = "search_source_data"
    name: ClassVar[str] = "search_source_data"
    description: ClassVar[str] = (
        "Search the user's ingested news and source data for items matching a query. "
        "Results are filtered by blocked sources/topics and ranked by preferred tags "
        "and recency. Use this to answer questions about recent news or find specific articles."
    )
    is_builtin: ClassVar[bool] = True
    parameters: ClassVar[dict[str, object]] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search keywords (FTS query)."},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_RESULT_LIMIT,
                "default": DEFAULT_RESULT_LIMIT,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    metadata: ClassVar[PluginMetadata] = PluginMetadata(
        id=id,
        type="tool",
        name="Search Source Data",
        description=description,
        icon="search",
        config_fields=[],
        is_builtin=True,
    )

    def __init__(
        self,
        rag_service: RagServiceProtocol | None,
        memory_service: MemoryService | None,
        candidate_filter: CandidateFilter,
        default_user_id: str = "admin",
    ) -> None:
        """Inject the RAG service, preference source, and candidate filter."""
        self._rag_service = rag_service
        self._memory_service = memory_service
        self._candidate_filter = candidate_filter
        self._default_user_id = default_user_id.strip() or "admin"

    async def handler(self, args: Mapping[str, object]) -> object:
        """Return ranked search results or a non-fatal error string."""
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            return "Error: query must not be empty"
        limit = self._integer_argument(args.get("limit"), default=DEFAULT_RESULT_LIMIT, minimum=1)
        if limit is None or limit > MAX_RESULT_LIMIT:
            return f"Error: limit must be an integer between 1 and {MAX_RESULT_LIMIT}"

        if self._rag_service is None:
            return {"query": query, "results": [], "returned": 0, "blocked": 0}

        try:
            evidence = await self._rag_service.retrieve(
                query,
                RetrievalScope(user_id=self._default_user_id, doc_types=["source_data"]),
                top_k=limit * FETCH_MULTIPLIER,
            )
        except Exception:
            return {"query": query, "results": [], "returned": 0, "blocked": 0}

        items = [_unified_data(item) for item in evidence]
        preferences = await self._load_preferences()
        ranked, blocked_count = self._candidate_filter.filter_and_rank(items, preferences)

        results = [
            {
                "id": item.id,
                "title": item.title,
                "summary": item.description[:SUMMARY_CHAR_LIMIT],
                "url": item.url,
                "source": item.source,
            }
            for item in ranked[:limit]
        ]
        return {
            "query": query,
            "results": results,
            "returned": len(results),
            "blocked": blocked_count,
        }

    async def _load_preferences(self) -> UserPreferences:
        """Return persisted preferences or defaults when memory service is unavailable."""
        if self._memory_service is None:
            return DEFAULT_PREFERENCES
        try:
            return await self._memory_service.get_preferences()
        except Exception:
            return DEFAULT_PREFERENCES

    @staticmethod
    def _integer_argument(value: object, *, default: int, minimum: int) -> int | None:
        """Coerce a validated argument, matching ReadArtifactTool's helper."""
        if value is None:
            return default
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            return None
        return value


def _unified_data(evidence: RetrievedEvidence) -> UnifiedData:
    """Convert RAG evidence into the existing CandidateFilter input model."""
    document = evidence.document
    published_date = document.published_at or datetime.now(UTC).isoformat()
    item_id = document.document_id.removeprefix("source_data:")
    return UnifiedData(
        id=item_id,
        title=document.title,
        url=document.url,
        description=evidence.chunk.content,
        published_date=published_date,
        ingestion_date=document.indexed_at or published_date,
        source=document.source,
        category=document.category,
        metadata={
            "retrieval_source": evidence.retrieval_source,
            "retrieval_score": evidence.score,
        },
    )
