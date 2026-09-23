"""Compare the frozen legacy retriever with the P66.3 RagService path."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from multiscribe_agent.infra.db import SqliteDatabase, init_db
from multiscribe_agent.infra.repositories.source_data import SourceDataRepository
from multiscribe_agent.knowledge.document_processor import DocumentProcessor
from multiscribe_agent.knowledge.embedding_service import EmbeddingService
from multiscribe_agent.knowledge.kb_service import KBService
from multiscribe_agent.knowledge.retriever import Retriever
from multiscribe_agent.knowledge.vector_store import VectorStore
from multiscribe_agent.rag.models import RetrievalScope
from multiscribe_agent.rag.service import RagService

ALLOWED_INTENTS = {"exact-term", "semantic", "mixed", "temporal"}
DEFAULT_DATASET = Path("data/eval/rag_queries.jsonl")
DEFAULT_DATABASE = Path("data/database.sqlite")
DEFAULT_REPORT_DIR = Path("data/eval/reports")


@dataclass(frozen=True, slots=True)
class QueryRecord:
    """One manually labelled retrieval query."""

    query_id: str
    query: str
    lang: str
    intent: str
    relevant: tuple[tuple[str, str], ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RankedResult:
    """One result normalized across the old KB and SourceData paths."""

    key: tuple[str, str]
    title: str
    url: str
    source: str
    retrieval_source: str
    score: float
    citation_complete: bool


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Per-query metrics and ranked evidence keys."""

    query: QueryRecord
    results: tuple[RankedResult, ...]
    recall_at_5: float
    recall_at_10: float
    reciprocal_rank: float
    citation_coverage: float
    latency_ms: float
    errors: tuple[str, ...]


def _parse_args() -> argparse.Namespace:
    """Parse the baseline harness command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument(
        "--impl",
        choices=("old", "new", "both"),
        default="old",
        help="Run the frozen legacy path, P66.3 RagService, or both.",
    )
    parser.add_argument(
        "--user-id",
        default="admin",
        help="RetrievalScope user_id used by the new RagService path.",
    )
    parser.add_argument(
        "--enable-vector",
        action="store_true",
        help=(
            "Attempt the existing sentence-transformer/vector path; disabled by default "
            "to avoid network downloads."
        ),
    )
    return parser.parse_args()


def _load_queries(path: Path) -> list[QueryRecord]:
    """Load and validate the frozen JSONL query set."""
    records: list[QueryRecord] = []
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise ValueError(f"line {line_number}: query must be an object")
            query_id = _required_string(raw, "query_id", line_number)
            if query_id in seen_ids:
                raise ValueError(f"line {line_number}: duplicate query_id {query_id}")
            seen_ids.add(query_id)
            query = _required_string(raw, "query", line_number)
            lang = _required_string(raw, "lang", line_number)
            if lang not in {"zh", "en"}:
                raise ValueError(f"line {line_number}: lang must be zh or en")
            intent = _required_string(raw, "intent", line_number)
            if intent not in ALLOWED_INTENTS:
                raise ValueError(f"line {line_number}: unsupported intent {intent}")
            raw_relevant = raw.get("relevant")
            if not isinstance(raw_relevant, list) or not raw_relevant:
                raise ValueError(f"line {line_number}: relevant must be a non-empty list")
            relevant: list[tuple[str, str]] = []
            notes: list[str] = []
            for item in raw_relevant:
                if not isinstance(item, dict):
                    raise ValueError(f"line {line_number}: relevant item must be an object")
                doc_type = _required_string(item, "doc_type", line_number)
                if doc_type not in {"kb", "source_data"}:
                    raise ValueError(f"line {line_number}: invalid doc_type {doc_type}")
                match = _required_string(item, "match", line_number)
                note = _required_string(item, "note", line_number)
                relevant.append((doc_type, match))
                notes.append(note)
            records.append(
                QueryRecord(query_id, query, lang, intent, tuple(relevant), tuple(notes))
            )
    _validate_intent_distribution(records)
    return records


def _required_string(raw: dict[str, object], key: str, line_number: int) -> str:
    """Return a non-empty string field from a JSON object."""
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"line {line_number}: {key} must be a non-empty string")
    return value.strip()


def _validate_intent_distribution(records: list[QueryRecord]) -> None:
    """Enforce the P66.1 four-class minimum before touching the database."""
    counts = Counter(record.intent for record in records)
    missing = {intent: counts[intent] for intent in sorted(ALLOWED_INTENTS) if counts[intent] < 7}
    if missing:
        raise ValueError(f"each intent needs at least 7 records: {missing}")
    if len(records) < 30:
        raise ValueError(f"dataset needs at least 30 records, got {len(records)}")


async def _validate_references(
    db: SqliteDatabase, records: list[QueryRecord]
) -> tuple[int, int, set[str], set[str]]:
    """Check that every label points to a real current KB chunk or SourceData row."""
    source_rows = await db.fetchall("SELECT id FROM source_data")
    chunk_rows = await db.fetchall("SELECT id, content FROM kb_chunks")
    source_ids = {str(row["id"]) for row in source_rows}
    chunk_prefixes = {
        hashlib.sha256(str(row["content"]).encode()).hexdigest()[:16] for row in chunk_rows
    }
    missing: list[str] = []
    for record in records:
        for doc_type, match in record.relevant:
            exists = match in source_ids if doc_type == "source_data" else match in chunk_prefixes
            if not exists:
                missing.append(f"{record.query_id}:{doc_type}:{match}")
    if missing:
        raise ValueError("dataset references missing records: " + ", ".join(missing[:10]))
    return len(source_ids), len(chunk_rows), source_ids, chunk_prefixes


async def _search_one(
    record: QueryRecord,
    kb_service: KBService,
    source_repository: SourceDataRepository,
    candidate_k: int,
) -> QueryResult:
    """Run both legacy retrieval paths and normalize their ranked results."""
    started = time.perf_counter()
    ranked: list[RankedResult] = []
    errors: list[str] = []
    try:
        kb_hits = await kb_service.search(record.query, top_k=candidate_k)
    except Exception as exc:  # Baseline reports path failures per query.
        kb_hits = []
        errors.append(f"kb:{type(exc).__name__}")
    for hit in kb_hits:
        digest = hashlib.sha256(hit.content.encode()).hexdigest()[:16]
        ranked.append(
            RankedResult(
                key=("kb", digest),
                title="",
                url="",
                source="",
                retrieval_source="hybrid" if len(hit.source) > 1 else hit.source[0],
                score=hit.score,
                citation_complete=False,
            )
        )
    try:
        source_hits = await source_repository.search_fts(record.query, limit=candidate_k)
    except Exception as exc:  # Malformed FTS input is a reportable baseline result.
        source_hits = []
        errors.append(f"source_data:{type(exc).__name__}")
    for rank, item in enumerate(source_hits, start=1):
        ranked.append(
            RankedResult(
                key=("source_data", item.id),
                title=item.title,
                url=item.url,
                source=item.source,
                retrieval_source="bm25",
                score=1.0 / rank,
                citation_complete=bool(
                    item.title.strip() and item.url.strip() and item.source.strip()
                ),
            )
        )
    # The old paths have separate ranking domains.  Keep the legacy order
    # deterministic: KB results first, then SourceData FTS results.
    deduped: list[RankedResult] = []
    seen: set[tuple[str, str]] = set()
    for result in ranked:
        if result.key not in seen:
            deduped.append(result)
            seen.add(result.key)
    relevant = set(record.relevant)
    return QueryResult(
        query=record,
        results=tuple(deduped),
        recall_at_5=_recall(deduped[:5], relevant),
        recall_at_10=_recall(deduped[:10], relevant),
        reciprocal_rank=_mrr(deduped, relevant),
        citation_coverage=_citation_coverage(deduped),
        latency_ms=(time.perf_counter() - started) * 1000,
        errors=tuple(errors),
    )


async def _search_one_new(
    record: QueryRecord,
    rag_service: RagService,
    scope: RetrievalScope,
    candidate_k: int,
) -> QueryResult:
    """Run P66.3 hybrid retrieval and normalize RetrievedEvidence for the harness."""
    started = time.perf_counter()
    errors: list[str] = []
    try:
        evidence = await rag_service.retrieve(record.query, scope, top_k=candidate_k)
    except Exception as exc:  # Keep one malformed query from hiding the comparison.
        evidence = []
        errors.append(f"rag:{type(exc).__name__}")
    ranked = [
        RankedResult(
            key=_evidence_key(
                item.document.doc_type,
                item.document.document_id,
                item.chunk.content,
            ),
            title=item.document.title,
            url=item.document.url,
            source=item.document.source,
            retrieval_source=item.retrieval_source,
            score=item.score,
            citation_complete=bool(
                item.document.title.strip()
                and item.document.url.strip()
                and item.document.source.strip()
            ),
        )
        for item in evidence
    ]
    relevant = set(record.relevant)
    return QueryResult(
        query=record,
        results=tuple(ranked),
        recall_at_5=_recall(ranked[:5], relevant),
        recall_at_10=_recall(ranked[:10], relevant),
        reciprocal_rank=_mrr(ranked, relevant),
        citation_coverage=_citation_coverage(ranked),
        latency_ms=(time.perf_counter() - started) * 1000,
        errors=tuple(errors),
    )


def _evidence_key(doc_type: str, document_id: str, content: str) -> tuple[str, str]:
    """Map a RetrievedEvidence identity to the frozen dataset identity."""
    if doc_type == "source_data":
        return (doc_type, document_id.removeprefix("source_data:"))
    return (doc_type, hashlib.sha256(content.encode()).hexdigest()[:16])


def _recall(results: list[RankedResult], relevant: set[tuple[str, str]]) -> float:
    """Calculate query-level recall against stable labelled identities."""
    if not relevant:
        return 0.0
    return len({result.key for result in results} & relevant) / len(relevant)


def _mrr(results: list[RankedResult], relevant: set[tuple[str, str]]) -> float:
    """Calculate reciprocal rank of the first relevant result."""
    for rank, result in enumerate(results, start=1):
        if result.key in relevant:
            return 1.0 / rank
    return 0.0


def _citation_coverage(results: list[RankedResult]) -> float:
    """Return the fraction of returned records with complete source metadata."""
    if not results:
        return 0.0
    return sum(result.citation_complete for result in results) / len(results)


def _aggregate(results: list[QueryResult]) -> dict[str, float | int]:
    """Aggregate query-level metrics without weighting large result sets."""
    if not results:
        return {
            "queries": 0,
            "recall_at_5": 0.0,
            "recall_at_10": 0.0,
            "mrr": 0.0,
            "citation_coverage": 0.0,
            "queries_with_results": 0,
            "latency_p50_ms": 0.0,
            "latency_p95_ms": 0.0,
        }
    latencies = sorted(item.latency_ms for item in results)
    return {
        "queries": len(results),
        "recall_at_5": sum(item.recall_at_5 for item in results) / len(results),
        "recall_at_10": sum(item.recall_at_10 for item in results) / len(results),
        "mrr": sum(item.reciprocal_rank for item in results) / len(results),
        "citation_coverage": sum(item.citation_coverage for item in results) / len(results),
        "queries_with_results": sum(bool(item.results) for item in results),
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
    }


def _percentile(values: list[float], quantile: float) -> float:
    """Return a deterministic nearest-rank percentile for a non-empty list."""
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round((len(values) - 1) * quantile)))
    return values[index]


def _render_report(
    *,
    generated_at: str,
    dataset: Path,
    database: Path,
    source_count: int,
    chunk_count: int,
    vector_enabled: bool,
    results_by_impl: dict[str, list[QueryResult]],
) -> str:
    """Render a human-readable old/new comparison report."""
    vector_state = "enabled" if vector_enabled else "disabled"
    lines = [
        "# P66.3 RAG 检索对照报告",
        "",
        f"- 生成时间: `{generated_at}`",
        f"- 数据集: `{dataset}`",
        f"- 数据库: `{database}`",
        f"- 当前数据: SourceData `{source_count}` 条, KBChunk `{chunk_count}` 条",
        f"- 向量路径: `{vector_state}`",
    ]
    for implementation, results in results_by_impl.items():
        grouped: dict[str, list[QueryResult]] = defaultdict(list)
        for result in results:
            grouped[result.query.intent].append(result)
        lines.extend(
            [
                "",
                f"## {implementation}",
                "",
                "| 意图 | Queries | Recall@5 | Recall@10 | MRR | 引用覆盖率 | "
                "有结果查询 | p50(ms) | p95(ms) |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for intent in ("exact-term", "semantic", "mixed", "temporal"):
            metrics = _aggregate(grouped[intent])
            lines.append(
                f"| {intent} | {metrics['queries']} | {metrics['recall_at_5']:.4f} | "
                f"{metrics['recall_at_10']:.4f} | {metrics['mrr']:.4f} | "
                f"{metrics['citation_coverage']:.4f} | {metrics['queries_with_results']} | "
                f"{metrics['latency_p50_ms']:.2f} | {metrics['latency_p95_ms']:.2f} |"
            )
        metrics = _aggregate(results)
        lines.append(
            f"| **overall** | **{metrics['queries']}** | **{metrics['recall_at_5']:.4f}** | "
            f"**{metrics['recall_at_10']:.4f}** | **{metrics['mrr']:.4f}** | "
            f"**{metrics['citation_coverage']:.4f}** | **{metrics['queries_with_results']}** | "
            f"**{metrics['latency_p50_ms']:.2f}** | **{metrics['latency_p95_ms']:.2f}** |"
        )
        lines.extend(
            [
                "",
                "### 查询明细",
                "",
                "| Query ID | Intent | 返回数 | Recall@5 | Recall@10 | MRR | "
                "Citation | p50(ms) | 错误 |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for item in results:
            lines.append(
                f"| {item.query.query_id} | {item.query.intent} | {len(item.results)} | "
                f"{item.recall_at_5:.4f} | {item.recall_at_10:.4f} | "
                f"{item.reciprocal_rank:.4f} | {item.citation_coverage:.4f} | "
                f"{item.latency_ms:.2f} | {', '.join(item.errors) or '-'} |"
            )
    lines.extend(
        [
            "",
            "> 说明: `old` 只测现有 `KBService/Retriever` 与 "
            "`SourceDataRepository.search_fts`; `new` 测 P66.3 `RagService` 的 BM25 + 向量 + RRF。",
        ]
    )
    return "\n".join(lines) + "\n"


async def _run(args: argparse.Namespace) -> tuple[Path, Path, dict[str, object]]:
    """Run one or both retrieval implementations and write a comparison report."""
    records = _load_queries(args.dataset)
    if args.candidate_k < 1:
        raise ValueError("--candidate-k must be positive")
    # ``init_db`` loads sqlite-vec on the active connection; opening a raw
    # connection would make the dense route look unavailable in evaluation.
    db = await init_db(str(args.database), enable_sql_audit=False)
    try:
        source_count, chunk_count, _, _ = await _validate_references(db, records)
        vector_requested = args.enable_vector and EmbeddingService.is_available()
        embeddings = EmbeddingService() if vector_requested else None
        vector_store = VectorStore(db) if embeddings is not None else None
        results_by_impl: dict[str, list[QueryResult]] = {}
        if args.impl in {"old", "both"}:
            kb_service = KBService(
                db,
                DocumentProcessor(),
                embeddings,
                vector_store,
                Retriever(db, vector_store, embeddings),
            )
            source_repository = SourceDataRepository(db)
            results_by_impl["old"] = [
                await _search_one(record, kb_service, source_repository, args.candidate_k)
                for record in records
            ]
        if args.impl in {"new", "both"}:
            rag_service = RagService(db, vector_store, embeddings, candidate_k=args.candidate_k)
            scope = RetrievalScope(user_id=args.user_id)
            results_by_impl["new"] = [
                await _search_one_new(record, rag_service, scope, args.candidate_k)
                for record in records
            ]
    finally:
        await db.close()
    generated_at = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    stem = (
        f"rag-compare_{generated_at}" if args.impl == "both" else f"rag-{args.impl}_{generated_at}"
    )
    args.report_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report_dir / f"{stem}.md"
    json_path = args.report_dir / f"{stem}.json"
    report_path.write_text(
        _render_report(
            generated_at=datetime.now(UTC).isoformat(),
            dataset=args.dataset,
            database=args.database,
            source_count=source_count,
            chunk_count=chunk_count,
            vector_enabled=vector_requested,
            results_by_impl=results_by_impl,
        ),
        encoding="utf-8",
    )
    machine_by_impl = {
        implementation: {
            "overall": _aggregate(results),
            "by_intent": {
                intent: _aggregate([r for r in results if r.query.intent == intent])
                for intent in sorted(ALLOWED_INTENTS)
            },
            "queries": [
                {
                    "query_id": item.query.query_id,
                    "intent": item.query.intent,
                    "returned": len(item.results),
                    "recall_at_5": item.recall_at_5,
                    "recall_at_10": item.recall_at_10,
                    "mrr": item.reciprocal_rank,
                    "citation_coverage": item.citation_coverage,
                    "latency_ms": item.latency_ms,
                    "errors": list(item.errors),
                }
                for item in results
            ],
        }
        for implementation, results in results_by_impl.items()
    }
    machine = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset),
        "database": str(args.database),
        "source_data_count": source_count,
        "kb_chunk_count": chunk_count,
        "vector_enabled": vector_requested,
        "impl": args.impl,
        "implementations": machine_by_impl,
    }
    json_path.write_text(json.dumps(machine, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path, json_path, machine


def main() -> int:
    """Run the async baseline harness as a CLI command."""
    args = _parse_args()
    report_path, json_path, machine = asyncio.run(_run(args))
    print(f"report={report_path}")
    print(f"json={json_path}")
    print(json.dumps(machine["implementations"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
