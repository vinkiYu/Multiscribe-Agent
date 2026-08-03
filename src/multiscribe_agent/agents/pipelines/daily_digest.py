"""Daily ingest-to-curation-to-publish workflow built on the generic DAG engine."""

from __future__ import annotations

import ast
import asyncio
import copy
import hashlib
import json
import math
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time, timedelta
from datetime import date as Date
from html.parser import HTMLParser
from typing import Literal, Protocol, runtime_checkable
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from multiscribe_agent.agents.pipelines.prompts import CURATE_PROMPT, DIGEST_OVERVIEW_PROMPT
from multiscribe_agent.agents.workflow.engine import WorkflowEngine
from multiscribe_agent.agents.workflow.events import WorkflowEvent
from multiscribe_agent.agents.workflow.iteration_store import IterationStore
from multiscribe_agent.agents.workflow.protocols import (
    AgentStepExecutor,
    LoopReflector,
    ObservingAgentStepExecutor,
)
from multiscribe_agent.core.daily_digest_archive import DailyDigestArchive, get_daily_digest_archive
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.core.pushed_content import PushedContentRepository
from multiscribe_agent.domain.models import (
    ScheduleTask,
    SourceData,
    TokenUsage,
    UnifiedData,
    WorkflowDefinition,
    WorkflowStep,
)
from multiscribe_agent.domain.ports import SourceDataRepository
from multiscribe_agent.infra.db import Database
from multiscribe_agent.infra.repositories.curation_evaluations import (
    CurationEvaluationRecord,
    CurationEvaluationRepository,
)
from multiscribe_agent.memory.digest_context import DigestMemoryContextBuilder, DigestMemoryService
from multiscribe_agent.renderers.feishu_card import DigestItem
from multiscribe_agent.renderers.models import CuratedDigest
from multiscribe_agent.services.preference_feedback import PreferenceFeedbackService
from multiscribe_agent.services.publishing import PublishingService
from multiscribe_agent.services.scheduler import TaskExecutorRegistry

# Shared with the curation benchmark so evaluation and production use one projection contract.
CURATE_SUMMARY_CHAR_LIMIT = 150
# Backwards-compatible alias for existing callers; use CURATE_SUMMARY_CHAR_LIMIT for new code.
_CURATE_SUMMARY_CHAR_LIMIT = CURATE_SUMMARY_CHAR_LIMIT
_ARTICLE_IMAGE_TIMEOUT_SECONDS = 8.0

INGEST_AGENT_ID = "daily_digest_ingest"
DEDUPE_AGENT_ID = "daily_digest_dedupe"
OVERVIEW_AGENT_ID = "daily_digest_overview"
FANOUT_AGENT_ID = "daily_digest_fanout"
WORKFLOW_ID = "daily_digest"
FEEDBACK_SEPARATOR = "\n\nFeedback from previous attempt:\n"
_SNAPSHOT_ADAPTER_IDS = frozenset({"github_trending"})
_CONTENT_FALLBACK_DAYS = 7
CURATE_SCORE_MIN = 1.0
CURATE_SCORE_MAX = 10.0
CURATE_SUMMARY_MAX_CHARS = 100
_DIGEST_SECTIONS = frozenset({"产品与功能更新", "前沿研究", "行业展望与社会影响", "开源TOP项目"})
log = structlog.get_logger(__name__)


def digest_content_hash(title: str, description: str) -> str:
    """Return the canonical fingerprint used by digest deduplication entry points."""
    return hashlib.sha256(f"{title}\n{description}".encode()).hexdigest()


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


@runtime_checkable
class MemoryAwareObservingAgentStepExecutor(Protocol):
    """Optional executor extension combining memory injection and usage capture."""

    async def execute_observed_with_memory(
        self, agent_id: str, user_input: str, memory_summaries: list[str]
    ) -> tuple[str, TokenUsage | None]:
        """Execute with memory and return provider usage alongside the output."""


@dataclass(slots=True)
class _DigestUsage:
    """Per-run token and provider-call accumulator for the daily digest."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, usage: TokenUsage | None) -> None:
        """Add one provider usage record when the execution surface exposes it."""
        if usage is None:
            return
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.total_tokens += usage.total_tokens
        self.llm_calls += 1
        self._add_model(
            usage.model_name,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        )

    def as_dict(self) -> dict[str, object]:
        """Return the stable scheduler/API payload shape."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "by_model": {model: dict(bucket) for model, bucket in self.by_model.items()},
        }

    def add_mapping(self, usage: Mapping[str, object]) -> None:
        """Add a serialized loop usage payload without trusting dynamic event data."""
        self.input_tokens += _usage_int(usage.get("input_tokens"))
        self.output_tokens += _usage_int(usage.get("output_tokens"))
        self.total_tokens += _usage_int(usage.get("total_tokens"))
        self.llm_calls += 1 if usage else 0
        if not usage:
            return
        model_name = usage.get("model_name")
        model = model_name if isinstance(model_name, str) else ""
        self._add_model(
            model,
            _usage_int(usage.get("input_tokens")),
            _usage_int(usage.get("output_tokens")),
            _usage_int(usage.get("total_tokens")),
        )

    def _add_model(
        self, model_name: str, input_tokens: int, output_tokens: int, total_tokens: int
    ) -> None:
        """Accumulate one call in a stable model bucket, including unknown models."""
        model = model_name.strip() or "unknown"
        bucket = self.by_model.setdefault(
            model,
            {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0},
        )
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["total_tokens"] += total_tokens
        bucket["llm_calls"] += 1


@dataclass(slots=True)
class _LoopIterationAccumulator:
    """Collect curation Loop observations emitted by the existing workflow engine."""

    rounds: int = 0
    converged: bool = False
    exit_reason: str = "max_rounds"
    final_score: float | None = None
    score_delta: float | None = None
    scores: list[float] = field(default_factory=list)
    usage: _DigestUsage = field(default_factory=_DigestUsage)

    def record(self, event_data: Mapping[str, object]) -> None:
        """Capture one serialized `loop_iteration` event for the curation step."""
        round_value = event_data.get("iteration")
        if isinstance(round_value, int) and not isinstance(round_value, bool):
            self.rounds = max(self.rounds, round_value)
        score = _numeric_value(event_data.get("score"))
        if score is not None:
            self.final_score = score
            self.scores.append(score)
        self.score_delta = _numeric_value(event_data.get("delta"))
        reason = event_data.get("reason")
        if isinstance(reason, str) and reason:
            self.exit_reason = reason
        if event_data.get("converged") is True:
            self.converged = True
        iteration_usage = event_data.get("usage")
        if isinstance(iteration_usage, Mapping):
            self.usage.add_mapping(iteration_usage)

    def as_dict(self) -> dict[str, object]:
        """Return the stable curation evaluation payload used by persistence and APIs."""
        return {
            "rounds": self.rounds,
            "converged": self.converged,
            "exit_reason": self.exit_reason,
            "final_score": self.final_score,
            "score_delta": self.score_delta,
            "avg_iter_score": sum(self.scores) / len(self.scores) if self.scores else None,
            "usage": self.usage.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class DailyDigestConfig:
    """Runtime choices for one daily digest execution."""

    curate_agent_id: str
    adapter_ids: list[str] = field(default_factory=list)
    fetch_days: int = 2
    top_n: int = 12
    targets: list[str] = field(default_factory=lambda: ["feishu_bot", "wecom_bot"])
    preview_mode: Literal["off", "preview_first"] = "off"
    preview_targets: list[str] = field(default_factory=list)
    enable_overview: bool = True
    # Direct callers may opt in; the persisted default schedule is bootstrapped
    # with this enabled and ``from_mapping`` keeps that production default.
    resolve_article_images: bool = False
    loop_max_iterations: int = 3
    curate_candidate_limit: int = 100
    curate_score_threshold: float = 8.0
    adapter_configs: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject invalid bounded workflow settings before scheduling execution."""
        if not self.curate_agent_id.strip():
            raise ValueError("curate_agent_id must not be empty")
        if self.preview_mode not in {"off", "preview_first"}:
            raise ValueError("preview_mode must be 'off' or 'preview_first'")
        if (
            min(self.fetch_days, self.top_n, self.loop_max_iterations, self.curate_candidate_limit)
            <= 0
        ):
            raise ValueError("daily digest numeric limits must be positive")
        if (
            isinstance(self.curate_score_threshold, bool)
            or not isinstance(self.curate_score_threshold, int | float)
            or not math.isfinite(float(self.curate_score_threshold))
        ):
            raise ValueError("curate_score_threshold must be numeric")

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
        raw_preview_mode = values.get("preview_mode", "off")
        if raw_preview_mode not in {"off", "preview_first"}:
            raise ValueError("preview_mode must be 'off' or 'preview_first'")
        return cls(
            curate_agent_id=curate_agent_id,
            adapter_ids=adapter_ids,
            fetch_days=_positive_int(values.get("fetch_days"), 2, "fetch_days"),
            top_n=_positive_int(values.get("top_n"), 12, "top_n"),
            targets=targets if raw_targets is not None else ["feishu_bot", "wecom_bot"],
            preview_mode=raw_preview_mode,
            preview_targets=_string_list(values.get("preview_targets"), "preview_targets"),
            enable_overview=_bool_value(values.get("enable_overview"), True, "enable_overview"),
            resolve_article_images=_bool_value(
                values.get("resolve_article_images"), True, "resolve_article_images"
            ),
            loop_max_iterations=_positive_int(
                values.get("loop_max_iterations"), 3, "loop_max_iterations"
            ),
            curate_candidate_limit=_positive_int(
                values.get("curate_candidate_limit"), 100, "curate_candidate_limit"
            ),
            curate_score_threshold=_float_value(
                values.get("curate_score_threshold"), 8.0, "curate_score_threshold"
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
                config={"loop": {"score_threshold": config.curate_score_threshold}},
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


def _sort_fallback_candidates(items: list[UnifiedData], limit: int) -> list[UnifiedData]:
    """Make degraded curation deterministic by preferring the newest source records."""
    return sorted(items, key=lambda item: item.published_date, reverse=True)[:limit]


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
        pushed_content_repo: PushedContentRepository | None = None,
        archive_repo: DailyDigestArchive | None = None,
        preference_feedback: PreferenceFeedbackService | None = None,
        iteration_store: IterationStore | None = None,
        curation_evaluations: CurationEvaluationRepository | None = None,
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
        self._pushed_content_repo = pushed_content_repo
        self._archive_repo = archive_repo or get_daily_digest_archive()
        self._preference_feedback = preference_feedback
        self._iteration_store = iteration_store
        self._curation_evaluations = curation_evaluations

    async def run(
        self, *, run_date: str | None = None, workflow_run_id: str | None = None
    ) -> dict[str, object]:
        """Run the entire DAG and return scheduler-friendly result metadata."""
        if self._preference_feedback is not None and self._db is not None:
            await self._preference_feedback.apply_click_feedback(self._db)
        date_value = run_date or datetime.now(UTC).date().isoformat()
        engine, usage = self._engine(date_value)
        loop_summary = _LoopIterationAccumulator()
        resolved_run_id = workflow_run_id or ""
        final: object = ""
        async for event in engine.stream(WORKFLOW_ID, "", date=date_value, run_id=workflow_run_id):
            if not resolved_run_id:
                resolved_run_id = event.trace_id
            if event.type == "workflow_error":
                raise WorkflowError(str(event.data["message"]), event.data)
            if event.type == "loop_iteration" and event.data.get("step_id") == "curate":
                loop_summary.record(event.data)
            if event.type == "workflow_complete":
                final = event.data["final"]
        if not isinstance(final, str):
            raise WorkflowError("daily digest workflow returned a non-text final result")
        payload = _json_object(final)
        result_count = payload.get("result_count")
        if not isinstance(result_count, int) or isinstance(result_count, bool):
            raise WorkflowError("daily digest final result is missing result_count")
        targets = payload.get("targets", {})
        approval_status = payload.get("approval_status", "published")
        if approval_status == "skipped":
            message = f"skipped {result_count} curated items because targets were already published"
        elif approval_status == "pending":
            message = f"prepared {result_count} curated items for approval"
        elif targets:
            message = f"published {result_count} curated items"
        else:
            message = f"generated {result_count} curated items without publishing"
        serialized_loop_summary = loop_summary.as_dict()
        if self._curation_evaluations is not None and resolved_run_id:
            evaluation_usage = {
                key: value
                for key, value in loop_summary.usage.as_dict().items()
                if isinstance(value, int)
            }
            await self._curation_evaluations.upsert(
                CurationEvaluationRecord(
                    workflow_run_id=resolved_run_id,
                    date=date_value,
                    recorded_at=int(datetime.now(UTC).timestamp()),
                    rounds=loop_summary.rounds,
                    converged=loop_summary.converged,
                    exit_reason=loop_summary.exit_reason,
                    final_score=loop_summary.final_score,
                    score_delta=loop_summary.score_delta,
                    avg_iter_score=(
                        sum(loop_summary.scores) / len(loop_summary.scores)
                        if loop_summary.scores
                        else None
                    ),
                    result_count=result_count,
                    usage=evaluation_usage,
                )
            )
        return {
            "result_count": result_count,
            "message": message,
            "targets": targets,
            "skipped_targets": payload.get("skipped_targets", []),
            "curated": payload.get("curated", []),
            "overview": payload.get("overview", ""),
            "preview_mode": payload.get("preview_mode", "off"),
            "approval_status": approval_status,
            "fetched_counts": payload.get("fetched_counts", {}),
            "usage": usage.as_dict(),
            "loop_summary": serialized_loop_summary,
            "workflow_run_id": resolved_run_id,
        }

    async def stream(
        self, *, run_date: str | None = None, workflow_run_id: str | None = None
    ) -> AsyncIterator[WorkflowEvent]:
        """Expose P10 lifecycle events, including loop iterations, for observability."""
        engine, _ = self._engine(run_date)
        async for event in engine.stream(WORKFLOW_ID, "", date=run_date, run_id=workflow_run_id):
            yield event

    async def daily_digest_executor(
        self, task: ScheduleTask, *, run_id: str | None = None
    ) -> dict[str, object]:
        """Adapt a persisted daily-digest task while preserving its optional run ID."""
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
            self._pushed_content_repo,
            archive_repo=self._archive_repo,
            preference_feedback=self._preference_feedback,
            iteration_store=self._iteration_store,
            curation_evaluations=self._curation_evaluations,
        )
        run_date = run_id.split(":", 1)[1] if run_id is not None and ":" in run_id else None
        return await pipeline.run(run_date=run_date, workflow_run_id=run_id)

    def _engine(self, run_date: str | None) -> tuple[WorkflowEngine, _DigestUsage]:
        """Build isolated per-run workflow state so concurrent schedules do not share outputs."""
        date_value = run_date or datetime.now(UTC).date().isoformat()
        workflow = build_daily_digest_workflow(self._config)
        usage = _DigestUsage()
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
            self._pushed_content_repo,
            usage,
            self._archive_repo,
        )
        run_reflector = self._reflector
        set_usage_sink = getattr(run_reflector, "set_usage_sink", None)
        if callable(set_usage_sink):
            # Provider adapters are normally reused by the service context. Copy the
            # small adapter shell before attaching a run-local sink so overlapping
            # digest runs cannot redirect each other's reflector accounting.
            run_reflector = copy.copy(self._reflector)
            set_usage_sink = getattr(run_reflector, "set_usage_sink", None)
            if callable(set_usage_sink):
                set_usage_sink(usage.add)
        return (
            WorkflowEngine(
                step_executor,
                _WorkflowStore(workflow),
                run_reflector,
                iteration_store=self._iteration_store,
            ),
            usage,
        )


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
        pushed_content_repo: PushedContentRepository | None = None,
        usage: _DigestUsage | None = None,
        archive_repo: DailyDigestArchive | None = None,
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
        self._pushed_content_repo = pushed_content_repo
        self._usage = usage or _DigestUsage()
        self._archive_repo = archive_repo or get_daily_digest_archive()
        self._total_scanned = 0
        self._raw_candidate_count = 0
        self._deduped_count = 0
        self._curate_candidate_count = 0
        self._curated_count = 0
        self._images_found = 0
        self._images_failed = 0
        self._fetched_counts: dict[str, int] = {}
        self._content_hash_by_url: dict[str, str] = {}

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Dispatch one workflow node while preserving the P10 text executor contract."""
        if agent_id == INGEST_AGENT_ID:
            return await self._ingest()
        if agent_id == DEDUPE_AGENT_ID:
            return await self._dedupe(user_input)
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
        self._fetched_counts = await self._ingestion_service.run_all(adapter_configs)
        end_date = Date.fromisoformat(self._run_date)
        start_date = end_date - timedelta(days=self._config.fetch_days - 1)
        fallback_start_date = end_date - timedelta(days=_CONTENT_FALLBACK_DAYS - 1)
        start = datetime.combine(start_date, time.min, tzinfo=UTC).isoformat()
        fallback_start = datetime.combine(fallback_start_date, time.min, tzinfo=UTC).isoformat()
        end = datetime.combine(end_date, time.max, tzinfo=UTC).isoformat()
        source_data = await self._recent_daily_candidates(start, fallback_start, end)
        source_data = self._filter_configured_rss_sources(source_data)
        items = [UnifiedData.model_validate(item.model_dump()) for item in source_data]
        total_new = sum(self._fetched_counts.values())
        if total_new == 0 and not items and adapter_configs:
            raise WorkflowError(
                "all adapters returned 0 new items and no historical candidates exist "
                f"in the window; adapter_counts={self._fetched_counts}"
            )
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
        # The concrete repository performs this as one OR query.  Keep a fallback
        # for lightweight test doubles and older repository implementations.
        get_recent_candidates = getattr(self._source_data_repo, "get_recent_candidates", None)
        if callable(get_recent_candidates):
            recent_rows = await get_recent_candidates(start, end, fallback_start, end)
            all_published = [
                item
                for item in recent_rows
                if item.published_date is not None and fallback_start <= item.published_date <= end
            ]
            fetched_items = [item for item in recent_rows if start <= item.fetched_at <= end]
        else:
            all_published = await self._source_data_repo.get_by_date_range(
                fallback_start, end, query_field="published_date"
            )
            fetched_items = await self._source_data_repo.get_by_date_range(
                start, end, query_field="fetched_at"
            )
        configured_adapters = set(self._config.adapter_ids)
        candidates: dict[str, SourceData] = {}
        for item in all_published:
            if item.adapter_name not in configured_adapters:
                continue
            if item.adapter_name in _SNAPSHOT_ADAPTER_IDS:
                continue  # snapshots are selected from the fetched_at query below
            if item.published_date and item.published_date >= start:
                # Recent data wins even if the same id also appears in the
                # broad fallback window.
                candidates[item.id] = self._with_digest_freshness(item, "recent")
            else:
                # Preserve the old fallback semantics: only fill a missing id.
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

    async def _dedupe(self, value: str) -> str:
        """Remove batch duplicates and content sent within the configured cross-day window."""
        items = _load_unified_items(value)
        self._raw_candidate_count = len(items)
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()
        pushed_hashes, pushed_urls = await self._recent_pushed_identities()
        unique: list[UnifiedData] = []
        self._content_hash_by_url = {}
        for item in items:
            normalized_url = item.url.strip().rstrip("/").casefold()
            content_hash = digest_content_hash(item.title, item.description)
            if (
                normalized_url in seen_urls
                or content_hash in seen_hashes
                or normalized_url in pushed_urls
                or content_hash in pushed_hashes
            ):
                continue
            seen_urls.add(normalized_url)
            seen_hashes.add(content_hash)
            self._content_hash_by_url[normalized_url] = content_hash
            unique.append(item)
        self._deduped_count = len(unique)
        # ``total_scanned`` is a persisted legacy field and remains the
        # post-dedupe count; raw_candidates exposes the pre-dedupe volume.
        self._total_scanned = len(unique)
        return _dump_json([item.model_dump(mode="json") for item in unique])

    async def _recent_pushed_identities(self) -> tuple[set[str], set[str]]:
        """Load pushed identities using the same inclusive window as source fetching."""
        if self._db is None:
            return set(), set()
        end_date = Date.fromisoformat(self._run_date)
        since_date = (end_date - timedelta(days=self._config.fetch_days - 1)).isoformat()
        pushed_hashes: set[str] = set()
        pushed_urls: set[str] = set()
        if self._pushed_content_repo is not None:
            pushed_hashes = await self._pushed_content_repo.recent_hashes(
                self._db, since_date=since_date
            )
            pushed_urls = await self._pushed_content_repo.recent_urls(
                self._db, since_date=since_date
            )
        if self._publish_history is not None:
            pushed_hashes.update(
                await self._publish_history.recent_content_hashes(self._db, since_date)
            )
        return pushed_hashes, pushed_urls

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
                items = _sort_fallback_candidates(items, self._config.curate_candidate_limit)
        else:
            items = _sort_fallback_candidates(items, self._config.curate_candidate_limit)
        self._curate_candidate_count = len(items)
        prompt = CURATE_PROMPT.format(
            items=_dump_json([_curate_item_dict(item) for item in items]),
            feedback=feedback or "无",
            target_count=self._config.top_n,
        )
        if isinstance(self._curate_executor, MemoryAwareObservingAgentStepExecutor):
            output, usage = await self._curate_executor.execute_observed_with_memory(
                self._config.curate_agent_id, prompt, memory_summaries
            )
            self._usage.add(usage)
        elif isinstance(self._curate_executor, ObservingAgentStepExecutor):
            output, usage = await self._curate_executor.execute_observed(
                self._config.curate_agent_id, prompt
            )
            self._usage.add(usage)
        elif isinstance(self._curate_executor, MemoryAwareAgentStepExecutor):
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
            try:
                score = _score_value(record.get("score"))
                curated.append(
                    DigestItem(
                        title=_optional_string(record.get("title")) or source.title,
                        summary=_plain_text(_required_string(record, "summary"))[
                            :CURATE_SUMMARY_MAX_CHARS
                        ],
                        url=source.url,
                        source=source.source,
                        score=score,
                        score_reason=_optional_string(record.get("score_reason")),
                        image_url=_metadata_string(source.metadata, "image_url", "thumbnail_url"),
                        video_url=_metadata_string(source.metadata, "video_url"),
                        published_at=source.published_date,
                        section=_digest_section(record.get("section"), source),
                        tags=_metadata_tags(source.metadata, source.category),
                    )
                )
            except WorkflowError:
                log.warning("daily_digest_invalid_curation_record")
        curated = _supplement_curated_items(curated, items, self._config.top_n)
        selected = _prioritize_digest_sections(curated, self._config.top_n)
        self._curated_count = len(selected)
        if self._config.resolve_article_images:
            before_images = sum(item.image_url is not None for item in selected)
            selected = await _resolve_article_images(selected)
            self._images_found = sum(item.image_url is not None for item in selected)
            self._images_failed = max(0, len(selected) - self._images_found)
            log.info(
                "daily_digest_images_resolved",
                found=self._images_found,
                failed=self._images_failed,
                existing=before_images,
            )
        return _dump_json([_digest_item_dict(item) for item in selected])

    async def _overview(self, value: str) -> str:
        """Generate an optional natural-language overview from the selected entries."""
        items = _load_digest_items(value)
        prompt = DIGEST_OVERVIEW_PROMPT.format(
            items=_dump_json([_digest_item_dict(item) for item in items])
        )
        if isinstance(self._curate_executor, ObservingAgentStepExecutor):
            output, usage = await self._curate_executor.execute_observed(OVERVIEW_AGENT_ID, prompt)
            self._usage.add(usage)
            return output
        return await self._curate_executor.execute(OVERVIEW_AGENT_ID, prompt)

    async def _fanout(self, value: str) -> str:
        """Render one CuratedDigest and publish it through the fault-isolating fan-out service."""
        values = _fanout_inputs(value)
        items = _load_digest_items(values["curated"])
        if not items:
            raise WorkflowError(
                "curation produced 0 items; refusing to publish an empty daily digest"
            )
        overview = values["overview"] if self._config.enable_overview else ""
        digest = CuratedDigest(
            date=self._run_date,
            title=f"每日精选 · {self._run_date}",
            items=items,
            summary=overview,
            total_scanned=self._total_scanned,
        )
        preview_enabled = self._config.preview_mode == "preview_first" and bool(
            self._config.preview_targets
        )
        if self._db is not None:
            await self._archive_repo.upsert(
                self._db,
                digest,
                approval_status="pending" if preview_enabled else "published",
            )
        if preview_enabled:
            publish_targets, skipped_targets = await self._filter_already_succeeded_targets(
                self._config.preview_targets
            )
            if not publish_targets:
                return _dump_json(
                    {
                        "result_count": len(items),
                        "targets": {},
                        "skipped_targets": skipped_targets,
                        "curated": [_digest_item_dict(item) for item in items],
                        "overview": overview,
                        "preview_mode": "preview_first",
                        "approval_status": "skipped",
                        **self._run_stats(),
                    }
                )
            targets = await self._publishing_service.fanout(digest, publish_targets)
            await self._record_publish_history(digest, targets)
            return _dump_json(
                {
                    "result_count": len(items),
                    "targets": targets,
                    "skipped_targets": skipped_targets,
                    "curated": [_digest_item_dict(item) for item in items],
                    "overview": overview,
                    "preview_mode": "preview_first",
                    "approval_status": "pending",
                    **self._run_stats(),
                }
            )

        publish_targets, skipped_targets = await self._filter_already_succeeded_targets(
            self._config.targets
        )
        if not publish_targets:
            return _dump_json(
                {
                    "result_count": len(items),
                    "targets": {},
                    "skipped_targets": skipped_targets,
                    "curated": [_digest_item_dict(item) for item in items],
                    "overview": overview,
                    "preview_mode": "off",
                    "approval_status": "skipped",
                    **self._run_stats(),
                }
            )
        targets = await self._publishing_service.fanout(digest, publish_targets)
        await self._record_publish_history(digest, targets, include_content_hash=True)
        if (
            self._db is not None
            and self._pushed_content_repo is not None
            and any(result.get("status") == "success" for result in targets.values())
        ):
            for item in items:
                normalized_url = item.url.strip().rstrip("/").casefold()
                content_hash = self._content_hash_by_url.get(normalized_url)
                if content_hash is None:
                    content_hash = digest_content_hash(item.title, item.summary)
                await self._pushed_content_repo.add(
                    self._db,
                    content_hash=content_hash,
                    url=normalized_url,
                    digest_date=self._run_date,
                    title=item.title,
                )
        return _dump_json(
            {
                "result_count": len(items),
                "targets": targets,
                "skipped_targets": skipped_targets,
                "curated": [_digest_item_dict(item) for item in items],
                "overview": overview,
                "preview_mode": "off",
                "approval_status": "published",
                **self._run_stats(),
            }
        )

    def _run_stats(self) -> dict[str, object]:
        """Return stage counters without persisting source content or prompts."""
        return {
            "fetched_counts": self._fetched_counts,
            "fetched_new": sum(self._fetched_counts.values()),
            "historical_candidates": max(
                0, self._raw_candidate_count - sum(self._fetched_counts.values())
            ),
            "total_scanned": self._total_scanned,
            "raw_candidates": self._raw_candidate_count,
            "deduped": self._deduped_count,
            "curate_candidates": self._curate_candidate_count,
            "curated_count": self._curated_count,
            "images_found": self._images_found,
            "images_failed": self._images_failed,
        }

    async def _filter_already_succeeded_targets(
        self, targets: list[str]
    ) -> tuple[list[str], list[str]]:
        """Skip targets already successful for this digest date before sending again."""
        if self._db is None or self._publish_history is None:
            return list(targets), []
        to_publish: list[str] = []
        skipped: list[str] = []
        for target in targets:
            records = await self._publish_history.query(
                self._db,
                publisher_id=target,
                digest_date=self._run_date,
                limit=10,
            )
            if any(record.status == "success" for record in records):
                skipped.append(target)
            else:
                to_publish.append(target)
        return to_publish, skipped

    async def _record_publish_history(
        self,
        digest: CuratedDigest,
        targets: dict[str, dict[str, object]],
        *,
        include_content_hash: bool = False,
    ) -> None:
        """Record publisher outcomes, optionally retaining final digest fingerprints."""
        if self._db is None or self._publish_history is None:
            return
        content_hash: str | None = None
        if include_content_hash:
            hashes = [
                self._content_hash_by_url.get(
                    item.url.strip().rstrip("/").casefold(),
                    digest_content_hash(item.title, item.summary),
                )
                for item in digest.items
            ]
            unique_hashes = list(dict.fromkeys(hashes))
            if len(unique_hashes) == 1:
                content_hash = unique_hashes[0]
            elif unique_hashes:
                content_hash = json.dumps(unique_hashes, separators=(",", ":"))
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
                digest_date=self._run_date,
                content_hash=content_hash if status == "success" else None,
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


def _float_value(value: object, default: float, name: str) -> float:
    """Validate a finite numeric configuration value."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    return numeric


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
                score_reason=_optional_string(record.get("score_reason")),
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


def _score_value(value: object) -> float | None:
    """Read a numeric LLM score in the inclusive 1-10 range."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError as exc:
            raise WorkflowError("curation record requires numeric score") from exc
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise WorkflowError("curation record requires numeric score")
    score = float(value)
    if not (CURATE_SCORE_MIN <= score <= CURATE_SCORE_MAX):
        raise WorkflowError(
            f"curation score {score} out of range [{CURATE_SCORE_MIN}, {CURATE_SCORE_MAX}]"
        )
    return score


def _numeric_value(value: object) -> float | None:
    """Read a numeric non-boolean loop event value without raising on telemetry data."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return float(value)


def _usage_int(value: object) -> int:
    """Normalize serialized non-negative token counters from workflow event data."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0
    try:
        return max(0, int(value))
    except (OverflowError, ValueError):
        return 0


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
        summary=_plain_text(candidate.description[:180]) or candidate.title,
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
    parsed_url = urlparse(item.url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        log.info("daily_digest_image_skipped", reason="invalid_article_url")
        return item
    try:
        response = await client.get(item.url, headers={"User-Agent": "Multiscribe/1.0"})
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.info("daily_digest_image_failed", reason=type(exc).__name__)
        return item
    image_url = _article_preview_image(response.text, str(response.url))
    if image_url is None:
        log.info("daily_digest_image_failed", reason="no_image_metadata")
        return item
    return replace(item, image_url=image_url)


def _article_preview_image(html: str, base_url: str) -> str | None:
    """Read the first usable social-media image without parsing executable page content."""
    parser = _ArticleImageParser()
    parser.feed(html)
    parser.close()
    if parser.image_url is None:
        return None
    resolved = urljoin(base_url, parser.image_url)
    parsed = urlparse(resolved)
    return resolved if parsed.scheme in {"https", "http"} and parsed.hostname is not None else None


def _plain_text(value: str) -> str:
    """Remove feed or model HTML before rendering a text-only digest summary."""
    parser = _PlainTextParser()
    parser.feed(value)
    parser.close()
    return " ".join(parser.parts).strip() or value.strip()


class _ArticleImageParser(HTMLParser):
    """Extract social metadata, JSON-LD, or the first safe body image."""

    def __init__(self) -> None:
        super().__init__()
        self.image_url: str | None = None
        self._script_chunks: list[str] = []
        self._in_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.image_url is not None:
            return
        values = {key.casefold(): value for key, value in attrs if value is not None}
        if tag == "link":
            rel = (values.get("rel") or "").casefold()
            href = (values.get("href") or "").strip()
            if "image_src" in rel and href:
                self.image_url = href
            return
        if tag == "img":
            source = (values.get("src") or values.get("data-src") or "").strip()
            if source:
                self.image_url = source
            return
        if tag != "meta":
            if tag == "script" and values.get("type", "").casefold() == "application/ld+json":
                self._in_json_ld = True
            return
        key = (values.get("property") or values.get("name") or "").casefold()
        content = values.get("content", "").strip()
        if key in {"og:image", "twitter:image", "twitter:image:src"} and content:
            self.image_url = content
            return

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._script_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld and self.image_url is None:
            self._in_json_ld = False
            try:
                payload = json.loads("".join(self._script_chunks))
            except json.JSONDecodeError:
                return
            self.image_url = _json_ld_image(payload)
            self._script_chunks.clear()


def _json_ld_image(payload: object) -> str | None:
    """Read image/thumbnailUrl from common JSON-LD Article shapes."""
    values: list[object] = payload if isinstance(payload, list) else [payload]
    for value in values:
        if not isinstance(value, Mapping):
            continue
        for key in ("image", "thumbnailUrl"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            if isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
    return None


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
        "score_reason": item.score_reason,
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
        "summary": item.description[:CURATE_SUMMARY_CHAR_LIMIT],
        "url": item.url,
        "source": item.source,
    }
    if item.source == "github_trending":
        projected["g"] = True
    if item.metadata.get("digest_freshness") == "fallback":
        projected["freshness"] = "fallback"
    return projected
