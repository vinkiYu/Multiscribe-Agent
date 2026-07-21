"""Daily ingest-to-curation-to-publish workflow built on the generic DAG engine."""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from datetime import date as Date
from typing import Literal, Protocol, runtime_checkable

import structlog

from multiscribe_agent.agents.pipelines.prompts import CURATE_PROMPT, DIGEST_OVERVIEW_PROMPT
from multiscribe_agent.agents.workflow.engine import WorkflowEngine
from multiscribe_agent.agents.workflow.events import WorkflowEvent
from multiscribe_agent.agents.workflow.protocols import AgentStepExecutor, LoopReflector
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.core.publish_history import PublishHistory
from multiscribe_agent.domain.models import (
    ScheduleTask,
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

INGEST_AGENT_ID = "daily_digest_ingest"
DEDUPE_AGENT_ID = "daily_digest_dedupe"
OVERVIEW_AGENT_ID = "daily_digest_overview"
FANOUT_AGENT_ID = "daily_digest_fanout"
WORKFLOW_ID = "daily_digest"
FEEDBACK_SEPARATOR = "\n\nFeedback from previous attempt:\n"
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
    top_n: int = 5
    targets: list[str] = field(default_factory=lambda: ["feishu_bot", "wecom_bot"])
    enable_overview: bool = True
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
            top_n=_positive_int(values.get("top_n"), 5, "top_n"),
            targets=targets if raw_targets is not None else ["feishu_bot", "wecom_bot"],
            enable_overview=_bool_value(values.get("enable_overview"), True, "enable_overview"),
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
            adapter_configs.append(
                {
                    "adapter_id": adapter_id,
                    "config": dict(self._config.adapter_configs.get(adapter_id, {})),
                }
            )
        await self._ingestion_service.run_all(adapter_configs)
        end_date = Date.fromisoformat(self._run_date)
        start_date = end_date - timedelta(days=self._config.fetch_days - 1)
        start = datetime.combine(start_date, time.min, tzinfo=UTC).isoformat()
        end = datetime.combine(end_date, time.max, tzinfo=UTC).isoformat()
        source_data = await self._source_data_repo.get_by_date_range(start, end)
        items = [UnifiedData.model_validate(item.model_dump()) for item in source_data]
        return _dump_json([item.model_dump(mode="json") for item in items])

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
            items=_dump_json([item.model_dump(mode="json") for item in items]),
            feedback=feedback or "无",
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
                    summary=_required_string(record, "summary"),
                    url=source.url,
                    source=source.source,
                    score=score,
                )
            )
        curated.sort(key=lambda item: item.score if item.score is not None else 0.0, reverse=True)
        return _dump_json([_digest_item_dict(item) for item in curated[: self._config.top_n]])

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


def _digest_item_dict(item: DigestItem) -> dict[str, object]:
    """Serialize the existing P7/P8 digest item without duplicating its model."""
    return {
        "title": item.title,
        "summary": item.summary,
        "url": item.url,
        "source": item.source,
        "score": item.score,
    }
