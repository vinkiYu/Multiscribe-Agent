"""Daily ingest-to-curation-to-publish workflow built on the generic DAG engine."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time, timedelta
from datetime import date as Date
from html.parser import HTMLParser
from typing import Literal, Protocol, runtime_checkable
from urllib.parse import urljoin

import httpx
import structlog

from multiscribe_agent.agents.pipelines.prompts import CURATE_PROMPT, DIGEST_OVERVIEW_PROMPT
from multiscribe_agent.agents.workflow.engine import WorkflowEngine
from multiscribe_agent.agents.workflow.events import WorkflowEvent
from multiscribe_agent.agents.workflow.protocols import AgentStepExecutor, LoopReflector
from multiscribe_agent.core.daily_digest_archive import get_daily_digest_archive
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.domain.models import (
    ScheduleTask,
    SourceData,
    UnifiedData,
    WorkflowDefinition,
    WorkflowStep,
)
from multiscribe_agent.domain.ports import SourceDataRepository
from multiscribe_agent.infra.db import Database
from multiscribe_agent.memory.digest_context import DigestMemoryContextBuilder, DigestMemoryService
from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.models import CuratedDigest
from multiscribe_agent.services.publishing import PublishingService
from multiscribe_agent.services.scheduler import TaskExecutorRegistry

_CURATE_SUMMARY_CHAR_LIMIT = 150
_ARTICLE_IMAGE_TIMEOUT_SECONDS = 8.0

INGEST_AGENT_ID = "daily_digest_ingest"
DEDUPE_AGENT_ID = "daily_digest_dedupe"
OVERVIEW_AGENT_ID = "daily_digest_overview"
FANOUT_AGENT_ID = "daily_digest_fanout"
WORKFLOW_ID = "daily_digest"
FEEDBACK_SEPARATOR = "\n\nFeedback from previous attempt:\n"
_SNAPSHOT_ADAPTER_IDS = frozenset({"github_trending"})
_CONTENT_FALLBACK_DAYS = 7
_DIGEST_SECTIONS = frozenset({"产品与功能更新", "前沿研究", "行业展望与社会影响", "开源TOP项目"})
log = structlog.get_logger(__name__)


class IngestionRunner(Protocol):
    """The portion of IngestionService needed by the daily pipeline."""

    async def run_all(
        self, adapter_configs: list[dict[str, object]], task_log_id: str | None = None
    ) -> dict[str, int]:
        """Run configured adapters and persist their normalized results."""


@runtime_checkable
class MemoryAwareAgentStepExecutor(Protocol):
    """Optional executor extension that can inject durable memory into HarnessContext."""

    async def execute_with_memory(
        self, agent_id: str, user_input: str, memory_summaries: list[str]
    ) -> str:
        """Execute one agent step with compact system-context memory."""


@dataclass(frozen=True, slots=True)
class DailyDigestConfig:
    """Runtime choices for one daily digest execution."""

    curate_agent_id: str
    adapter_ids: list[str] = field(default_factory=list)
    fetch_days: int = 2
    top_n: int = 12
    targets: list[str] = field(default_factory=lambda: ["feishu_bot", "wecom_bot"])
    enable_overview: bool = True
    resolve_article_images: bool = False
    loop_max_iterations: int = 3
    curate_candidate_limit: int = 100
    adapter_configs: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject invalid bounded workflow settings before scheduling execution."""
        if not self.curate_agent_id.strip():
            raise ValueError("curate_agent_id must not be empty")
        if (
            min(self.fetch_days, self.top_n, self.loop_max_iterations, self.curate_candidate_limit)
            <= 0
        ):
            raise ValueError("daily digest numeric limits must be positive")

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> DailyDigestConfig:
        """Build config from a persisted schedule-task JSON object."""
        curate_agent_id = values.get("curate_agent_id")
        if not isinstance(curate_agent_id, str):
            raise ValueError("daily digest config requires curate_agent_id")
        adapter_ids = _string_list(values.get("adapter_ids"), "adapter_ids")
        raw_targets = values.get("targets")
        targets = _string_list(raw_targets, "targets")
        raw_configs = values.get("adapter_configs", {})
        if not isinstance(raw_configs, Mapping):
            raise ValueError("adapter_configs must be an object")
        adapter_configs: dict[str, Mapping[str, object]] = {}
        for adapter_id, config in raw_configs.items():
            if not isinstance(adapter_id, str) or not isinstance(config, Mapping):
                raise ValueError("adapter_configs must map adapter IDs to objects")
            adapter_configs[adapter_id] = config
        return cls(
            curate_agent_id=curate_agent_id,
            adapter_ids=adapter_ids,
            fetch_days=_positive_int(values.get("fetch_days"), 2, "fetch_days"),
            top_n=_positive_int(values.get("top_n"), 12, "top_n"),
            targets=targets if raw_targets is not None else ["feishu_bot", "wecom_bot"],
            enable_overview=_bool_value(values.get("enable_overview"), True, "enable_overview"),
            resolve_article_images=_bool_value(
                values.get("resolve_article_images"), False, "resolve_article_images"
            ),
            loop_max_iterations=_positive_int(
                values.get("loop_max_iterations"), 3, "loop_max_iterations"
            ),
            curate_candidate_limit=_positive_int(
                values.get("curate_candidate_limit"), 100, "curate_candidate_limit"
            ),
            adapter_configs=adapter_configs,
        )


def build_daily_digest_workflow(config: DailyDigestConfig) -> WorkflowDefinition:
    """Create the five-node DAG whose input maps declare all data dependencies."""
    return WorkflowDefinition(
        id=WORKFLOW_ID,
        name="Daily digest",
        description="Ingest, deduplicate, curate, summarize, then publish a daily digest.",
        steps=[
            WorkflowStep(
                id="ingest",
                name="Ingest sources",
                step_type="agent",
                agent_id=INGEST_AGENT_ID,
                next_step_id="dedupe",
            ),
            WorkflowStep(
                id="dedupe",
                name="Deduplicate sources",
                step_type="agent",
                agent_id=DEDUPE_AGENT_ID,
                input_map={"items": "ingest"},
                next_step_id="curate",
            ),
            WorkflowStep(
                id="curate",
                name="Curate with quality loop",
                step_type="agent",
                agent_id=config.curate_agent_id,
                input_map={"items": "dedupe"},
                next_step_id="overview",
                max_iterations=config.loop_max_iterations,
                exit_condition="llm",
            ),
            WorkflowStep(
                id="overview",
                name="Write overview",
                step_type="agent",
                agent_id=OVERVIEW_AGENT_ID,
                input_map={"items": "curate"},
                next_step_id="fanout",
                enabled=config.enable_overview,
            ),
            WorkflowStep(
                id="fanout",
                name="Render and publish",
                step_type="agent",
                agent_id=FANOUT_AGENT_ID,
                input_map={"curated": "curate", "overview": "overview"},
            ),
        ],
    )


# 每日信息聚合管道
class DailyDigestPipeline:
    """Assemble per-run pipeline dependencies into a P10 workflow execution."""

    def __init__(
        self,
        ingestion_service: IngestionRunner,
        source_data_repo: SourceDataRepository,
        curate_executor: AgentStepExecutor,
        publishing_service: PublishingService,
        config: DailyDigestConfig,
        reflector: LoopReflector,
        db: Database | None = None,
        publish_history: PublishHistory | None = None,
        memory_service: DigestMemoryService | None = None,
    ) -> None:
        """Configure injected service boundaries for a reusable scheduled pipeline."""
        self._ingestion_service = ingestion_service
        self._source_data_repo = source_data_repo
        self._curate_executor = curate_executor
        self._publishing_service = publishing_service
        self._config = config
        self._reflector = reflector
        self._db = db
        self._publish_history = publish_history
        self._memory_service = memory_service

    async def run(self, *, run_date: str | None = None) -> dict[str, object]:
        """Run the entire DAG and return scheduler-friendly result metadata."""
        engine = self._engine(run_date)
        result = await engine.run(WORKFLOW_ID, "", date=run_date)
        final = result["final"]
        if not isinstance(final, str):
            raise WorkflowError("daily digest workflow returned a non-text final result")
        payload = _json_object(final)
        result_count = payload.get("result_count")
        if not isinstance(result_count, int) or isinstance(result_count, bool):
            raise WorkflowError("daily digest final result is missing result_count")
        targets = payload.get("targets", {})
        return {
            "result_count": result_count,
            "message": (
                f"published {result_count} curated items"
                if targets
                else f"generated {result_count} curated items without publishing"
            ),
            "targets": targets,
            "curated": payload.get("curated", []),
            "overview": payload.get("overview", ""),
        }

    async def stream(self, *, run_date: str | None = None) -> AsyncIterator[WorkflowEvent]:
        """Expose P10 lifecycle events, including loop iterations, for observability."""
        async for event in self._engine(run_date).stream(WORKFLOW_ID, "", date=run_date):
            yield event

    async def daily_digest_executor(self, task: ScheduleTask) -> dict[str, object]:
        """Adapt a persisted daily-digest schedule task to the P9 callback contract."""
        if task.task_type != "daily_digest":
            raise ValueError(f"unsupported task type for daily digest executor: {task.task_type}")
        config = DailyDigestConfig.from_mapping(task.config)
        pipeline = DailyDigestPipeline(
            self._ingestion_service,
            self._source_data_repo,
            self._curate_executor,
            self._publishing_service,
            config,
            self._reflector,
            self._db,
            self._publish_history,
            self._memory_service,
        )
        return await pipeline.run()

    def _engine(self, run_date: str | None) -> WorkflowEngine:
        """Build isolated per-run workflow state so concurrent schedules do not share outputs."""
        date_value = run_date or datetime.now(UTC).date().isoformat()
        workflow = build_daily_digest_workflow(self._config)
        step_executor = _DailyDigestStepExecutor(
            self._ingestion_service,
            self._source_data_repo,
            self._curate_executor,
            self._publishing_service,
            self._config,
            date_value,
            self._db,
            self._publish_history,
            self._memory_service,
        )
        return WorkflowEngine(step_executor, _WorkflowStore(workflow), self._reflector)


def register_daily_digest_executor(
    registry: TaskExecutorRegistry, pipeline: DailyDigestPipeline
) -> None:
    """Register the pipeline under P9's persisted ``daily_digest`` task type."""
    registry.register("daily_digest", pipeline.daily_digest_executor)


class _WorkflowStore:
    """In-memory definition store satisfying the P10 workflow-store boundary."""

    def __init__(self, workflow: WorkflowDefinition) -> None:
        self._workflow = workflow.model_dump(mode="json")

    async def get(self, table: str, entity_id: str) -> dict[str, object] | None:
        """Return the single generated workflow only for the expected lookup."""
        if table == "workflows" and entity_id == WORKFLOW_ID:
            return self._workflow
        return None


class _DailyDigestStepExecutor:
    """Map declarative workflow agent IDs onto the pipeline's injected dependencies."""

    def __init__(
        self,
        ingestion_service: IngestionRunner,
        source_data_repo: SourceDataRepository,
        curate_executor: AgentStepExecutor,
        publishing_service: PublishingService,
        config: DailyDigestConfig,
        run_date: str,
        db: Database | None,
        publish_history: PublishHistory | None,
        memory_service: DigestMemoryService | None = None,
    ) -> None:
        self._ingestion_service = ingestion_service
        self._source_data_repo = source_data_repo
        self._curate_executor = curate_executor
        self._publishing_service = publishing_service
        self._config = config
        self._run_date = run_date
        self._db = db
        self._publish_history = publish_history
        self._memory_service = memory_service
        self._total_scanned = 0

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Dispatch one workflow node while preserving the P10 text executor contract."""
        if agent_id == INGEST_AGENT_ID:
            return await self._ingest()
        if agent_id == DEDUPE_AGENT_ID:
            return self._dedupe(user_input)
        if agent_id == self._config.curate_agent_id:
            return await self._curate(user_input)
        if agent_id == OVERVIEW_AGENT_ID:
            return await self._overview(user_input)
        if agent_id == FANOUT_AGENT_ID:
            return await self._fanout(user_input)
        raise LookupError(f"unknown daily digest workflow agent: {agent_id}")

    async def _ingest(self) -> str:
        """Run configured adapters then read the persisted recent normalized data."""
        adapter_configs: list[dict[str, object]] = []
        for adapter_id in self._config.adapter_ids:
            adapter_config = dict(self._config.adapter_configs.get(adapter_id, {}))
            adapter_configs.append(
                {
                    "adapter_id": adapter_id,
                    "enabled": adapter_config.pop("enabled", True),
                    "config": adapter_config,
                }
            )
        await self._ingestion_service.run_all(adapter_configs)
        end_date = Date.fromisoformat(self._run_date)
        start_date = end_date - timedelta(days=self._config.fetch_days - 1)
        fallback_start_date = end_date - timedelta(days=_CONTENT_FALLBACK_DAYS - 1)
        start = datetime.combine(start_date, time.min, tzinfo=UTC).isoformat()
        fallback_start = datetime.combine(fallback_start_date, time.min, tzinfo=UTC).isoformat()
        end = datetime.combine(end_date, time.max, tzinfo=UTC).isoformat()
        source_data = await self._recent_daily_candidates(start, fallback_start, end)
        source_data = self._filter_configured_rss_sources(source_data)
        items = [UnifiedData.model_validate(item.model_dump()) for item in source_data]
        return _dump_json([item.model_dump(mode="json") for item in items])

    async def _recent_daily_candidates(
        self, start: str, fallback_start: str, end: str
    ) -> list[SourceData]:
        """Return recent articles, seven-day content fallback, and trend snapshots.

        Published articles are eligible only when their source-declared publication
        time falls inside the digest window. GitHub Trending has no article
        publication time, so its current ranking is instead eligible by the time
        the snapshot was fetched. Other records with an unknown publication date
        stay out of the digest rather than becoming current merely by re-ingestion.
        """
        published_items = await self._source_data_repo.get_by_date_range(
            start, end, query_field="published_date"
        )
        fallback_items = await self._source_data_repo.get_by_date_range(
            fallback_start, end, query_field="published_date"
        )
        fetched_items = await self._source_data_repo.get_by_date_range(
            start, end, query_field="fetched_at"
        )
        configured_adapters = set(self._config.adapter_ids)
        candidates = {
            item.id: self._with_digest_freshness(item, "recent")
            for item in published_items
            if item.adapter_name in configured_adapters
        }
        for item in fallback_items:
            if (
                item.adapter_name in configured_adapters
                and item.adapter_name not in _SNAPSHOT_ADAPTER_IDS
            ):
                candidates.setdefault(item.id, self._with_digest_freshness(item, "fallback"))
        for item in fetched_items:
            if (
                item.adapter_name in configured_adapters
                and item.adapter_name in _SNAPSHOT_ADAPTER_IDS
            ):
                candidates[item.id] = self._with_digest_freshness(item, "snapshot")
        return list(candidates.values())

    @staticmethod
    def _with_digest_freshness(item: SourceData, freshness: str) -> SourceData:
        """Attach an ephemeral date-window marker for the curator prompt."""
        metadata = {**item.metadata, "digest_freshness": freshness}
        return item.model_copy(update={"metadata": metadata})

    def _filter_configured_rss_sources(self, source_data: list[SourceData]) -> list[SourceData]:
        """Exclude stale RSS rows when this run declares an explicit multi-feed list."""
        rss_config = self._config.adapter_configs.get("rss", {})
        raw_urls = rss_config.get("rss_urls")
        if not isinstance(raw_urls, list) or not raw_urls:
            return source_data
        configured_urls = {
            normalized
            for value in raw_urls
            if isinstance(value, str)
            and (normalized := self._normalize_feed_url(value)) is not None
        }
        if not configured_urls:
            return source_data
        filtered: list[SourceData] = []
        for item in source_data:
            if item.adapter_name != "rss":
                filtered.append(item)
                continue
            feed_url = item.metadata.get("feed_url")
            if isinstance(feed_url, str) and self._normalize_feed_url(feed_url) in configured_urls:
                filtered.append(item)
        return filtered

    @staticmethod
    def _normalize_feed_url(value: str) -> str | None:
        """Normalize configured feed URLs for stable source-boundary comparisons."""
        normalized = value.strip().casefold().rstrip("/")
        return normalized or None

    def _dedupe(self, value: str) -> str:
        """Remove repeated normalized URLs or content hashes before LLM curation."""
        items = _load_unified_items(value)
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()
        unique: list[UnifiedData] = []
        for item in items:
            normalized_url = item.url.strip().rstrip("/").casefold()
            content_hash = hashlib.sha256(f"{item.title}\n{item.description}".encode()).hexdigest()
            if normalized_url in seen_urls or content_hash in seen_hashes:
                continue
            seen_urls.add(normalized_url)
            seen_hashes.add(content_hash)
            unique.append(item)
        self._total_scanned = len(unique)
        return _dump_json([item.model_dump(mode="json") for item in unique])

    async def _curate(self, value: str) -> str:
        """Ask the injected curator for scored JSON and preserve the top configured entries."""
        item_payload, feedback = _split_feedback(value)
        items = _load_unified_items(item_payload)
        memory_summaries: list[str] = []
        if self._memory_service is not None:
            try:
                memory_context = await DigestMemoryContextBuilder(
                    self._memory_service, self._config.curate_candidate_limit
                ).build(items)
                items = memory_context.items
                memory_summaries = memory_context.memory_summaries
                if memory_context.blocked_count:
                    log.info(
                        "daily_digest_candidates_blocked",
                        count=memory_context.blocked_count,
                    )
            except Exception as exc:  # Memory must never block the scheduled digest.
                log.warning("daily_digest_memory_degraded", error_type=type(exc).__name__)
                items = items[: self._config.curate_candidate_limit]
        else:
            items = items[: self._config.curate_candidate_limit]
        prompt = CURATE_PROMPT.format(
            items=_dump_json([_curate_item_dict(item) for item in items]),
            feedback=feedback or "无",
            target_count=self._config.top_n,
        )
        if isinstance(self._curate_executor, MemoryAwareAgentStepExecutor):
            output = await self._curate_executor.execute_with_memory(
                self._config.curate_agent_id, prompt, memory_summaries
            )
        else:
            output = await self._curate_executor.execute(self._config.curate_agent_id, prompt)
        records = _json_array(output)
        by_id = {item.id: item for item in items}
        curated: list[DigestItem] = []
        for record in records:
            item_id = _required_string(record, "id")
            source = by_id.get(item_id)
            if source is None:
                continue
            score = _score_value(record.get("score"))
            curated.append(
                DigestItem(
                    title=_required_string(record, "title"),
                    summary=_plain_text(_required_string(record, "summary")),
                    url=source.url,
                    source=source.source,
                    score=score,
                    image_url=_metadata_string(source.metadata, "image_url", "thumbnail_url"),
                    video_url=_metadata_string(source.metadata, "video_url"),
                    published_at=source.published_date,
                    section=_digest_section(record.get("section"), source),
                    tags=_metadata_tags(source.metadata, source.category),
                )
            )
        curated = _supplement_curated_items(curated, items, self._config.top_n)
        selected = _prioritize_digest_sections(curated, self._config.top_n)
        if self._config.resolve_article_images:
            selected = await _resolve_article_images(selected)
        return _dump_json([_digest_item_dict(item) for item in selected])

    async def _overview(self, value: str) -> str:
        """Generate an optional natural-language overview from the selected entries."""
        items = _load_digest_items(value)
        prompt = DIGEST_OVERVIEW_PROMPT.format(
            items=_dump_json([_digest_item_dict(item) for item in items])
        )
        return await self._curate_executor.execute(self._config.curate_agent_id, prompt)

    async def _fanout(self, value: str) -> str:
        """Render one CuratedDigest and publish it through the fault-isolating fan-out service."""
        values = _fanout_inputs(value)
        items = _load_digest_items(values["curated"])
        overview = values["overview"] if self._config.enable_overview else ""
        digest = CuratedDigest(
            date=self._run_date,
            title=f"每日精选 · {self._run_date}",
            items=items,
            summary=overview,
            total_scanned=self._total_scanned,
        )
        if self._db is not None:
            await get_daily_digest_archive().upsert(self._db, digest)
        targets = await self._publishing_service.fanout(digest, self._config.targets)
        if self._db is not None and self._publish_history is not None:
            for publisher_id, result in targets.items():
                status: Literal["success", "error"] = (
                    "success" if result.get("status") == "success" else "error"
                )
                error = result.get("error")
                await self._publish_history.add(
                    self._db,
                    publisher_id=publisher_id,
                    status=status,
                    title=digest.title,
                    content=digest.summary,
                    result_data=result,
                    error_message=str(error) if status == "error" and error is not None else None,
                )
        return _dump_json(
            {
                "result_count": len(items),
                "targets": targets,
                "curated": [_digest_item_dict(item) for item in items],
                "overview": overview,
            }
        )


def _string_list(value: object, name: str) -> list[str]:
    """Validate an optional list of non-empty stable identifiers."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(entry, str) and entry for entry in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return list(value)


def _positive_int(value: object, default: int, name: str) -> int:
    """Validate a positive non-boolean integer with a documented default."""
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _bool_value(value: object, default: bool, name: str) -> bool:
    """Validate a boolean configuration value with a documented default."""
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _dump_json(value: object) -> str:
    """Encode internal pipeline hand-offs in a deterministic JSON representation."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_array(value: str) -> list[Mapping[str, object]]:
    """Parse a strict JSON array, with embedded-array recovery for LLM fence noise."""
    decoded = _decode_json(value)
    if not isinstance(decoded, list) or not all(isinstance(item, Mapping) for item in decoded):
        raise WorkflowError("curation output must be a JSON array of objects")
    return list(decoded)


def _json_object(value: str) -> Mapping[str, object]:
    """Parse one JSON object emitted by the final pipeline fan-out step."""
    decoded = _decode_json(value)
    if not isinstance(decoded, Mapping):
        raise WorkflowError("pipeline output must be a JSON object")
    return decoded


def _decode_json(value: str) -> object:
    """Decode whole JSON first, then recover the first embedded JSON value if necessary."""
    try:
        decoded: object = json.loads(value)
        return decoded
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(value):
            if character not in "[{":
                continue
            try:
                decoded, _ = decoder.raw_decode(value[index:])
                return decoded
            except json.JSONDecodeError:
                continue
    raise WorkflowError("curation output did not contain valid JSON")


def _load_unified_items(value: str) -> list[UnifiedData]:
    """Validate a serialized normalized-content array from an earlier pipeline node."""
    try:
        return [UnifiedData.model_validate(item) for item in _json_array(value)]
    except ValueError as exc:
        raise WorkflowError("pipeline input did not contain valid unified data") from exc


def _load_digest_items(value: str) -> list[DigestItem]:
    """Validate serialized selected content emitted by the curation node."""
    items: list[DigestItem] = []
    for record in _json_array(value):
        items.append(
            DigestItem(
                title=_required_string(record, "title"),
                summary=_required_string(record, "summary"),
                url=_required_string(record, "url"),
                source=_required_string(record, "source"),
                score=_score_value(record.get("score")),
                image_url=_optional_string(record.get("image_url")),
                video_url=_optional_string(record.get("video_url")),
                published_at=_optional_string(record.get("published_at")),
                section=_optional_string(record.get("section")) or "产品与功能更新",
                tags=_string_tuple(record.get("tags")),
            )
        )
    return items


def _fanout_inputs(value: str) -> Mapping[str, str]:
    """Safely parse P10's stringified multi-input mapping for the fan-out node."""
    try:
        decoded = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise WorkflowError("fanout input mapping is invalid") from exc
    if not isinstance(decoded, dict):
        raise WorkflowError("fanout input must be a mapping")
    curated = decoded.get("curated")
    overview = decoded.get("overview")
    if not isinstance(curated, str) or not isinstance(overview, str):
        raise WorkflowError("fanout input is missing curated or overview text")
    return {"curated": curated, "overview": overview}


def _split_feedback(value: str) -> tuple[str, str | None]:
    """Preserve P10 loop feedback while keeping its JSON task payload parseable."""
    payload, separator, feedback = value.partition(FEEDBACK_SEPARATOR)
    return payload, feedback if separator else None


def _required_string(record: Mapping[str, object], key: str) -> str:
    """Read one required non-empty string from validated LLM JSON."""
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"curation record requires non-empty {key}")
    return value.strip()


def _score_value(value: object) -> float:
    """Read a numeric non-boolean LLM score for sorting selected items."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise WorkflowError("curation record requires numeric score")
    return float(value)


def _optional_string(value: object) -> str | None:
    """Read an optional non-empty string from untrusted JSON or metadata."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _metadata_string(metadata: Mapping[str, object], *keys: str) -> str | None:
    """Read the first optional media URL from adapter metadata."""
    for key in keys:
        value = _optional_string(metadata.get(key))
        if value is not None:
            return value
    return None


def _metadata_tags(metadata: Mapping[str, object], category: str) -> tuple[str, ...]:
    """Keep a small, stable tag set for the article card."""
    values = metadata.get("tags")
    tags = (
        [tag.strip() for tag in values if isinstance(tag, str) and tag.strip()]
        if isinstance(values, list)
        else []
    )
    if category.strip() and category.strip() not in tags:
        tags.append(category.strip())
    return tuple(dict.fromkeys(tags[:4]))


def _prioritize_digest_sections(items: list[DigestItem], top_n: int) -> list[DigestItem]:
    """Keep one high-scoring item from each returned section before filling remaining slots."""
    ordered = sorted(
        items,
        key=lambda item: item.score if item.score is not None else 0.0,
        reverse=True,
    )
    selected: list[DigestItem] = []
    selected_urls: set[str] = set()
    for section in sorted(_DIGEST_SECTIONS):
        candidate = next(
            (item for item in ordered if item.section == section and item.url not in selected_urls),
            None,
        )
        if candidate is not None:
            selected.append(candidate)
            selected_urls.add(candidate.url)
    for item in ordered:
        if item.url not in selected_urls:
            selected.append(item)
            selected_urls.add(item.url)
        if len(selected) >= top_n:
            break
    return selected[:top_n]


def _supplement_curated_items(
    curated: list[DigestItem], candidates: list[UnifiedData], top_n: int
) -> list[DigestItem]:
    """Fill a short LLM selection and restore missing sections from eligible candidates."""
    selected = list(curated)
    selected_urls = {item.url for item in selected}
    content_sources_present = any(candidate.source != "github_trending" for candidate in candidates)
    github_limit = 2 if content_sources_present else top_n
    github_count = sum(item.source == "github_trending" for item in selected)
    covered_sections = {item.section for item in selected}
    remaining = [candidate for candidate in candidates if candidate.url not in selected_urls]
    remaining.sort(key=lambda item: _digest_section(None, item) in covered_sections)
    for section in sorted(_DIGEST_SECTIONS - covered_sections):
        replacement = next(
            (
                candidate
                for candidate in remaining
                if _digest_section(None, candidate) == section
                and not (candidate.source == "github_trending" and github_count >= github_limit)
            ),
            None,
        )
        if replacement is None or len(selected) < top_n:
            continue
        removable = next(
            (
                item
                for item in reversed(selected)
                if sum(existing.section == item.section for existing in selected) > 1
                and item.source != "github_trending"
            ),
            None,
        )
        if removable is None:
            continue
        selected.remove(removable)
        selected_urls.remove(removable.url)
        covered_sections = {item.section for item in selected}
        remaining.remove(replacement)
        selected.append(_supplement_digest_item(replacement, section))
        selected_urls.add(replacement.url)
        covered_sections.add(section)
        if replacement.source == "github_trending":
            github_count += 1
    for candidate in remaining:
        if len(selected) >= top_n:
            break
        if candidate.source == "github_trending" and github_count >= github_limit:
            continue
        section = _digest_section(None, candidate)
        selected.append(_supplement_digest_item(candidate, section))
        selected_urls.add(candidate.url)
        covered_sections.add(section)
        if candidate.source == "github_trending":
            github_count += 1
    return selected


def _supplement_digest_item(candidate: UnifiedData, section: str) -> DigestItem:
    """Project an existing source candidate without asking the model to invent text."""
    return DigestItem(
        title=candidate.title,
        summary=candidate.description[:180].strip() or candidate.title,
        url=candidate.url,
        source=candidate.source,
        score=None,
        image_url=_metadata_string(candidate.metadata, "image_url", "thumbnail_url"),
        video_url=_metadata_string(candidate.metadata, "video_url"),
        published_at=candidate.published_date,
        section=section,
        tags=_metadata_tags(candidate.metadata, candidate.category),
    )


async def _resolve_article_images(items: list[DigestItem]) -> list[DigestItem]:
    """Resolve missing article previews from safe Open Graph and Twitter metadata."""
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=_ARTICLE_IMAGE_TIMEOUT_SECONDS
    ) as client:
        resolved = await asyncio.gather(
            *[_resolve_item_image(item, client) for item in items], return_exceptions=True
        )
    return [
        result if isinstance(result, DigestItem) else item
        for item, result in zip(items, resolved, strict=True)
    ]


async def _resolve_item_image(item: DigestItem, client: httpx.AsyncClient) -> DigestItem:
    if item.image_url is not None or item.source == "github_trending":
        return item
    try:
        response = await client.get(item.url, headers={"User-Agent": "Multiscribe/1.0"})
        response.raise_for_status()
    except httpx.HTTPError:
        return item
    image_url = _article_preview_image(response.text, str(response.url))
    return item if image_url is None else replace(item, image_url=image_url)


def _article_preview_image(html: str, base_url: str) -> str | None:
    """Read the first usable social-media image without parsing executable page content."""
    parser = _ArticleImageParser()
    parser.feed(html)
    parser.close()
    if parser.image_url is None:
        return None
    resolved = urljoin(base_url, parser.image_url)
    return resolved if resolved.startswith(("https://", "http://")) else None


def _plain_text(value: str) -> str:
    """Remove feed or model HTML before rendering a text-only digest summary."""
    parser = _PlainTextParser()
    parser.feed(value)
    parser.close()
    return " ".join(parser.parts).strip() or value.strip()


class _ArticleImageParser(HTMLParser):
    """Stop at the first Open Graph or Twitter image meta element."""

    def __init__(self) -> None:
        super().__init__()
        self.image_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta" or self.image_url is not None:
            return
        values = {key.casefold(): value for key, value in attrs if value is not None}
        key = (values.get("property") or values.get("name") or "").casefold()
        content = values.get("content", "").strip()
        if key in {"og:image", "twitter:image", "twitter:image:src"} and content:
            self.image_url = content


class _PlainTextParser(HTMLParser):
    """Collect visible text while ignoring markup in untrusted source summaries."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _digest_section(value: object, source: SourceData | UnifiedData) -> str:
    """Validate the LLM section or derive a stable fallback from the source."""
    if source.source == "github_trending":
        return "开源TOP项目"
    text = f"{source.title} {source.description} {source.category}".casefold()
    if any(
        term in text
        for term in ("arxiv", "paper", "research", "论文", "研究", "reasoning", "推理", "diffusion")
    ):
        return "前沿研究"
    if any(
        term in text
        for term in (
            "policy",
            "regulation",
            "society",
            "safety",
            "security",
            "cyberattack",
            "geopolitics",
            "政策",
            "监管",
            "社会",
            "安全",
            "攻击",
            "地缘政治",
            "失控",
        )
    ):
        return "行业展望与社会影响"
    section = _optional_string(value)
    if section in _DIGEST_SECTIONS:
        return section
    return "产品与功能更新"


def _string_tuple(value: object) -> tuple[str, ...]:
    """Decode optional persisted tags without allowing arbitrary JSON values."""
    if not isinstance(value, list):
        return ()
    return tuple(
        dict.fromkeys(tag.strip() for tag in value if isinstance(tag, str) and tag.strip())
    )


def _digest_item_dict(item: DigestItem) -> dict[str, object]:
    """Serialize the existing P7/P8 digest item without duplicating its model."""
    return {
        "title": item.title,
        "summary": item.summary,
        "url": item.url,
        "source": item.source,
        "score": item.score,
        "image_url": item.image_url,
        "video_url": item.video_url,
        "published_at": item.published_at,
        "section": item.section,
        "tags": list(item.tags),
    }


def _curate_item_dict(item: UnifiedData) -> dict[str, object]:
    """Project normalized content to the minimal fields needed for curation scoring.

    The model receives source provenance while the compact summary remains the
    primary ranking input.
    """
    projected: dict[str, object] = {
        "id": item.id,
        "title": item.title,
        "summary": item.description[:_CURATE_SUMMARY_CHAR_LIMIT],
    }
    if item.source == "github_trending":
        projected["g"] = True
    if item.metadata.get("digest_freshness") == "fallback":
        projected["freshness"] = "fallback"
    return projected
