"""Rebuild the P66 RAG index from SourceData and KB business tables."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from multiscribe_agent.config import get_settings
from multiscribe_agent.domain.models import KBChunk, KBDocument, SourceData
from multiscribe_agent.infra.db import init_database
from multiscribe_agent.infra.db_protocol import DatabaseProtocol
from multiscribe_agent.knowledge.embedding_service import EmbeddingService
from multiscribe_agent.knowledge.postgres_vector_store import PostgresVectorStore
from multiscribe_agent.knowledge.vector_store import VectorStore
from multiscribe_agent.rag.adapter import AdaptedDocument, RagDocumentAdapter
from multiscribe_agent.rag.index_version import make_index_version
from multiscribe_agent.rag.indexing import RagIndexingPipeline, RagIndexRegistry

CURSOR_PATH = Path("data/rag/rebuild_cursor.json")
_INDEX_VERSION_RE = re.compile(r"^\d{8}-.+$")


def build_parser() -> argparse.ArgumentParser:
    """Create the rebuild command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--incremental",
        action="store_true",
        help="Only index new or changed chunks (default).",
    )
    mode.add_argument("--full", action="store_true", help="Re-index every selected document.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume after the last document_id saved in the cursor file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned document count without embedding or writing vectors.",
    )
    parser.add_argument(
        "--cursor",
        type=Path,
        default=CURSOR_PATH,
        help="Cursor path used for resumable rebuilds.",
    )
    return parser


async def rebuild(args: argparse.Namespace) -> dict[str, int | str]:
    """Run one resumable rebuild and return a serializable summary."""
    settings = get_settings()
    database = await init_database(
        settings.db_driver,
        sqlite_path=settings.db_path,
        postgres_dsn=settings.db_dsn,
        pool_size=settings.db_pool_size,
        pool_timeout=settings.db_pool_timeout,
        slow_query_threshold=settings.slow_query_threshold_seconds,
        enable_sql_audit=settings.enable_sql_audit,
    )
    try:
        records = await _load_records(database, settings.rag_source_window_days)
        cursor = _read_cursor(args.cursor) if args.resume else ""
        selected = [record for record in records if not cursor or record.document_id > cursor]
        if args.dry_run:
            return {"planned_documents": len(selected), "cursor": cursor or ""}

        embeddings = EmbeddingService(
            model_name=settings.rag_embedding_model,
            dimension=settings.rag_embedding_dim,
        )
        if not EmbeddingService.is_available():
            raise RuntimeError(
                "sentence-transformers is unavailable; install the runtime before a real rebuild"
            )
        if settings.db_driver == "postgres":
            vector_store = PostgresVectorStore(database)
        else:
            vector_store = VectorStore(database, dim=settings.rag_embedding_dim)
        registry = RagIndexRegistry(database)
        version = make_index_version(model_name=settings.rag_embedding_model)
        existing_versions = await _existing_index_versions(database)
        version_changed = bool(existing_versions) and version not in existing_versions
        if args.full or version_changed:
            await _reset_derived_index(database, settings.db_driver, settings.rag_embedding_dim)
            selected = records
            cursor = ""
        indexer = RagIndexingPipeline(vector_store, registry, embeddings)
        incremental = not (args.full or version_changed)
        summary = {"indexed": 0, "skipped": 0, "deleted": 0, "failed": 0}
        active_source_ids = {
            record.document.document_id
            for record in records
            if record.document.doc_type == "source_data"
        }
        for record in selected:
            report = await indexer.index(
                [record],
                index_version=version,
                incremental=incremental,
            )
            summary["indexed"] += len(report.indexed_chunk_ids)
            summary["skipped"] += len(report.skipped_chunk_ids)
            summary["deleted"] += len(report.deleted_chunk_ids)
            summary["failed"] += len(report.failed_document_ids)
            _write_cursor(args.cursor, record.document.document_id)
        summary["deleted"] += len(await indexer.prune_source_documents(active_source_ids))
        summary["index_version"] = version
        return summary
    finally:
        await database.close()


async def _existing_index_versions(database: DatabaseProtocol) -> set[str]:
    """Read the manifest versions used by the current derived index."""
    try:
        rows = await database.fetchall("SELECT DISTINCT index_version FROM rag_index_registry")
    except Exception:
        return set()
    return {
        str(row["index_version"])
        for row in rows
        if isinstance(row.get("index_version"), str)
        and _INDEX_VERSION_RE.match(str(row["index_version"]))
    }


async def _reset_derived_index(database: DatabaseProtocol, driver: str, dimension: int) -> None:
    """Drop model-dependent derived rows and recreate the configured vector space."""
    if dimension <= 0:
        raise ValueError("embedding dimension must be positive")
    await _delete_table_if_present(database, "rag_index_registry", driver)
    await _delete_table_if_present(database, "rag_chunks", driver)
    if driver == "postgres":
        await _delete_table_if_present(database, "chunk_vectors", driver)
        return
    await database.execute("DROP TABLE IF EXISTS kb_chunks_vec")
    await database.execute(
        "CREATE VIRTUAL TABLE kb_chunks_vec USING vec0("
        f"chunk_id TEXT PRIMARY KEY, embedding float[{dimension}])"
    )


async def _delete_table_if_present(
    database: DatabaseProtocol, table: str, driver: str
) -> None:
    """Delete rows only when a derived table exists on the selected backend."""
    if driver == "postgres":
        exists = await database.fetchone(
            "SELECT to_regclass(?) AS table_name", (table,)
        )
        if exists is None or exists.get("table_name") is None:
            return
    else:
        exists = await database.fetchone(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        )
        if exists is None:
            return
    await database.execute(f"DELETE FROM {table}")  # noqa: S608


async def _load_records(database: DatabaseProtocol, window_days: int) -> list[AdaptedDocument]:
    """Load current SourceData and all KB documents into canonical adapters."""
    rows = await database.fetchall("SELECT * FROM source_data ORDER BY id")
    adapter = RagDocumentAdapter(
        user_id=get_settings().rag_default_user_id,
        source_window_days=window_days,
    )
    records: list[AdaptedDocument] = []
    for row in rows:
        source = _source_from_row(row)
        adapted = adapter.adapt_source_data(source)
        if adapted is not None:
            records.append(adapted)

    document_rows = await database.fetchall("SELECT data FROM kb_documents ORDER BY id")
    for raw_document in document_rows:
        document = KBDocument.model_validate(json.loads(str(raw_document["data"])))
        raw_chunks = await database.fetchall(
            "SELECT id, document_id, content, metadata FROM kb_chunks "
            "WHERE document_id = ? ORDER BY document_id, id",
            (document.id,),
        )
        chunks = [
            KBChunk(
                id=str(row["id"]),
                document_id=str(row["document_id"]),
                content=str(row["content"]),
                index=index,
                metadata=json.loads(str(row["metadata"])),
            )
            for index, row in enumerate(raw_chunks)
        ]
        records.append(adapter.adapt_kb_document(document, chunks))
    return sorted(records, key=lambda item: item.document.document_id)


def _source_from_row(row: object) -> SourceData:
    """Decode one backend-neutral source row without changing the repository path."""
    mapping = dict(cast(Any, row))
    metadata = mapping.get("metadata", "{}")
    mapping["metadata"] = json.loads(str(metadata)) if isinstance(metadata, str) else metadata
    return SourceData.model_validate(mapping)


def _read_cursor(path: Path) -> str:
    """Read a document cursor, tolerating a missing or malformed file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return ""
    value = raw.get("document_id") if isinstance(raw, dict) else None
    return str(value) if isinstance(value, str) else ""


def _write_cursor(path: Path, document_id: str) -> None:
    """Persist the last completed document atomically enough for local resume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"document_id": document_id, "updated_at": datetime.now(UTC).isoformat()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    """Run the command-line rebuild entry point."""
    args = build_parser().parse_args()
    result = asyncio.run(rebuild(args))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
