"""Reconcile the PG rag_index_registry against the Qdrant vector collection.

The vector data is derived data written to two stores without a transaction
(PG registry rows and Qdrant points), so drift is possible. This script is
the operational check: it compares the chunk-ID sets on both sides, reports
any divergence, and exits non-zero when the stores disagree.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import asyncpg
from qdrant_client import AsyncQdrantClient

from multiscribe_agent.config import get_settings
from multiscribe_agent.knowledge.vector_store import COLLECTION_NAME

_SCROLL_PAGE_SIZE = 512


def build_parser() -> argparse.ArgumentParser:
    """Create the reconcile command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pg-dsn",
        default=None,
        help="PostgreSQL DSN (default: DATABASE_URL from settings/.env)",
    )
    parser.add_argument(
        "--qdrant-url",
        default=None,
        help="Qdrant base URL (default: QDRANT_URL from settings/.env)",
    )
    parser.add_argument(
        "--collection",
        default=COLLECTION_NAME,
        help="Qdrant collection name (default: rag_vectors)",
    )
    return parser


async def _registry_chunk_ids(pg_dsn: str) -> set[str]:
    """Load every indexed chunk ID from the PG registry."""
    connection = await asyncpg.connect(pg_dsn)
    try:
        rows = await connection.fetch("SELECT chunk_id FROM rag_index_registry")
    finally:
        await connection.close()
    return {str(row["chunk_id"]) for row in rows}


async def _qdrant_chunk_ids(qdrant_url: str, collection: str) -> set[str]:
    """Scroll the whole collection and collect the chunk-ID payload values."""
    client = AsyncQdrantClient(url=qdrant_url)
    chunk_ids: set[str] = set()
    try:
        offset: object | None = None
        while True:
            points, offset = await client.scroll(
                collection_name=collection,
                limit=_SCROLL_PAGE_SIZE,
                offset=offset,
                with_payload=True,
            )
            for point in points:
                payload = point.payload
                if isinstance(payload, dict) and "chunk_id" in payload:
                    chunk_ids.add(str(payload["chunk_id"]))
            if offset is None:
                break
    finally:
        await client.close()
    return chunk_ids


async def reconcile(pg_dsn: str, qdrant_url: str, collection: str) -> dict[str, object]:
    """Compare both chunk-ID sets and return the drift report."""
    registry_ids = await _registry_chunk_ids(pg_dsn)
    qdrant_ids = await _qdrant_chunk_ids(qdrant_url, collection)
    missing_in_qdrant = sorted(registry_ids - qdrant_ids)
    extra_in_qdrant = sorted(qdrant_ids - registry_ids)
    return {
        "collection": collection,
        "registry_count": len(registry_ids),
        "qdrant_count": len(qdrant_ids),
        "missing_in_qdrant": missing_in_qdrant,
        "extra_in_qdrant": extra_in_qdrant,
        "match": not missing_in_qdrant and not extra_in_qdrant,
    }


def main() -> int:
    """Run the reconciliation and exit 0 only on an exact match."""
    args = build_parser().parse_args()
    settings = get_settings()
    pg_dsn = args.pg_dsn or settings.database_url
    qdrant_url = args.qdrant_url or settings.qdrant_url
    if not pg_dsn:
        print("reconcile: no PostgreSQL DSN (pass --pg-dsn or set DATABASE_URL)", file=sys.stderr)
        return 2
    if not qdrant_url:
        print("reconcile: no Qdrant URL (pass --qdrant-url or set QDRANT_URL)", file=sys.stderr)
        return 2

    report = asyncio.run(reconcile(pg_dsn, qdrant_url, args.collection))
    print(json.dumps(report, indent=2))
    if report["match"]:
        print("reconcile: MATCH")
        return 0
    print("reconcile: DRIFT DETECTED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
