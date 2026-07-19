"""Authenticated REST endpoints for the persistent knowledge base."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from multiscribe_agent.api.deps import get_context
from multiscribe_agent.api.security import get_current_user
from multiscribe_agent.bootstrap import ServiceContext
from multiscribe_agent.domain.models import KBCategory, KBDocument
from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.knowledge.retriever import RetrievalHit

router = APIRouter(
    prefix="/api/kb",
    tags=["knowledge"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/capabilities")
async def capabilities(context: ServiceContext = Depends(get_context)) -> dict[str, bool]:  # noqa: B008
    """Return enabled retrieval capability flags for frontend feature decisions."""
    service = _service(context)
    return service.capabilities.as_dict()


@router.get("/categories")
async def list_categories(
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """List all durable knowledge-base categories."""
    return [_category_response(category) for category in await _service(context).list_categories()]


@router.post("/categories")
async def create_category(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Create one category from a name and optional description."""
    name = _required_text(payload, "name")
    description = _optional_text(payload, "description")
    try:
        category = await _service(context).create_category(name, description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _category_response(category)


@router.get("/documents")
async def list_documents(
    category_id: str | None = None,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> list[dict[str, object]]:
    """List stored documents, optionally within a single category."""
    return [
        _document_response(document)
        for document in await _service(context).list_documents(category_id)
    ]


@router.post("/documents")
async def ingest_document(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Ingest one server-local PDF, DOCX, Markdown, or text file."""
    raw_path = _required_text(payload, "file_path")
    path = Path(raw_path)
    if not path.is_file():
        raise HTTPException(status_code=400, detail="file_path must point to an existing file")
    try:
        document = await _service(context).ingest_file(
            file_path=path,
            category_id=_required_text(payload, "category_id"),
            name=_required_text(payload, "name"),
            summary=_optional_text(payload, "summary"),
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _document_response(document)


@router.post("/documents/text")
async def ingest_text(
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Ingest direct text without requiring a temporary upload file."""
    try:
        document = await _service(context).ingest_text(
            text=_required_text(payload, "text"),
            category_id=_required_text(payload, "category_id"),
            name=_required_text(payload, "name"),
            summary=_optional_text(payload, "summary"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _document_response(document)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, str]:
    """Delete one document and all its derived search data."""
    await _service(context).delete_document(document_id)
    return {"status": "deleted"}


@router.get("/search")
async def search(
    q: str,
    top_k: int = Query(default=10, ge=1, le=50),
    category_id: str | None = None,
    deduplicate: bool = True,
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Return RRF-ranked retrieval hits alongside current degradation information."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="q must not be empty")
    service = _service(context)
    hits = await service.search(q, top_k=top_k, category_id=category_id, deduplicate=deduplicate)
    return {
        "hits": [_hit_response(hit) for hit in hits],
        "degraded": service.capabilities.degraded,
        "capabilities": service.capabilities.as_dict(),
    }


@router.post("/documents/{document_id}/move-to-memory")
async def move_to_memory(
    document_id: str,
    payload: dict[str, object],
    context: ServiceContext = Depends(get_context),  # noqa: B008
) -> dict[str, object]:
    """Copy document chunks to the existing future-memory table."""
    category = _required_text(payload, "target_memory_category")
    count = await _service(context).move_to_memory(document_id, category)
    return {"document_id": document_id, "moved_count": count}


def _service(context: ServiceContext) -> KBService:
    """Return initialized KB service or surface the standard API availability error."""
    if context.kb_service is None:
        raise HTTPException(status_code=503, detail="knowledge-base service unavailable")
    return context.kb_service


def _required_text(payload: dict[str, object], key: str) -> str:
    """Read one non-empty text payload value."""
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"{key} must be a non-empty string")
    return value.strip()


def _optional_text(payload: dict[str, object], key: str) -> str:
    """Normalize an optional text payload value."""
    value = payload.get(key, "")
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{key} must be a string")
    return value.strip()


def _category_response(category: KBCategory) -> dict[str, object]:
    """Serialize one frozen domain category for JSON responses."""
    return category.model_dump(mode="json")


def _document_response(document: KBDocument) -> dict[str, object]:
    """Serialize one frozen domain document for JSON responses."""
    return document.model_dump(mode="json")


def _hit_response(hit: RetrievalHit) -> dict[str, object]:
    """Serialize retrieval provenance without exposing implementation objects."""
    return {
        "chunk_id": hit.chunk_id,
        "document_id": hit.document_id,
        "content": hit.content,
        "score": hit.score,
        "source": hit.source,
    }
