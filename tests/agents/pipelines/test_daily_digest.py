"""Tests for the P11 daily ingest, curate, loop, and publish workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from multiscribe_agent.agents.pipelines.daily_digest import (
    DailyDigestConfig,
    DailyDigestPipeline,
    build_daily_digest_workflow,
    register_daily_digest_executor,
)
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.domain.models import ScheduleTask, SourceData
from multiscribe_agent.renderers.models import CuratedDigest
from multiscribe_agent.services.publishing import PublishingService
from multiscribe_agent.services.scheduler import TaskExecutorRegistry


class FakeIngestionService:
    """Record configured adapter runs without external fetching."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, object]]] = []

    async def run_all(
        self, adapter_configs: list[dict[str, object]], task_log_id: str | None = None
    ) -> dict[str, int]:
        """Record adapters and return a successful count mapping."""
        del task_log_id
        self.calls.append(adapter_configs)
        return {str(config["adapter_id"]): 1 for config in adapter_configs}


class FakeSourceDataRepository:
    """Return deterministic recent source records to the pipeline."""

    def __init__(self, entries: list[SourceData]) -> None:
        self._entries = entries
        self.ranges: list[tuple[str, str]] = []

    async def get_by_date_range(self, start: str, end: str) -> list[SourceData]:
        """Record query bounds and return the configured records."""
        self.ranges.append((start, end))
        return self._entries


class FakeCurator:
    """Return curation arrays and an overview while retaining prompts."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = iter(outputs)
        self.inputs: list[str] = []

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Capture the requested prompt and return its configured response."""
        assert agent_id == "curator"
        self.inputs.append(user_input)
        return next(self._outputs)


@dataclass(frozen=True)
class Assessment:
    """Small reflection result compatible with P10's loop protocol."""

    should_retry: bool
    feedback: str


class RetryOnceReflector:
    """Require one refined curation attempt before convergence."""

    def __init__(self) -> None:
        self.calls = 0

    async def assess(self, task: str, output: str) -> Assessment:
        """Return failure then pass while checking the raw curated output is assessed."""
        del task
        assert output.startswith("[")
        self.calls += 1
        return Assessment(should_retry=self.calls == 1, feedback="improve summaries")


class FakePublisherRegistry:
    """Map target IDs onto test publisher classes."""

    def __init__(self, entries: dict[str, type[object]]) -> None:
        self._entries = entries

    def get(self, target: str) -> type[object]:
        """Return a publisher class by configured ID."""
        return self._entries[target]


class GoodPublisher:
    """Keep rendered digest input for later assertions."""

    received: ClassVar[list[object]] = []

    async def publish(self, content: object, options: object = None) -> dict[str, object]:
        """Record a successful delivery."""
        del options
        self.received.append(content)
        return {"ok": True}


class BadPublisher:
    """Create an isolated target failure."""

    async def publish(self, content: object, options: object = None) -> dict[str, object]:
        """Fail without affecting the successful target."""
        del content, options
        raise RuntimeError("bad destination")


def _source(item_id: str, url: str, title: str) -> SourceData:
    """Build one recent persisted source record."""
    return SourceData(
        id=item_id,
        title=title,
        url=url,
        description=f"{title} description",
        published_date="2026-07-17T08:00:00+00:00",
        source="RSS",
        category="technology",
        fetched_at="2026-07-17T08:01:00+00:00",
        ingestion_date="2026-07-17T08:01:00+00:00",
        adapter_name="rss",
    )


def _curation_json() -> str:
    """Return intentionally unordered LLM scores for top-N sorting tests."""
    return (
        '[{"id":"one","title":"One","summary":"摘要一","score":4,"score_reason":"ok"},'
        '{"id":"three","title":"Three","summary":"摘要三","score":9,"score_reason":"important"}]'
    )


def _pipeline(
    curator_outputs: list[str],
) -> tuple[DailyDigestPipeline, FakeCurator, FakeIngestionService]:
    """Assemble a fully mocked pipeline with a duplicate URL source record."""
    config = DailyDigestConfig(
        curate_agent_id="curator",
        adapter_ids=["rss"],
        top_n=2,
        targets=["good", "bad"],
        adapter_configs={"rss": {"url": "https://feed.example.test"}},
    )
    ingestion = FakeIngestionService()
    repository = FakeSourceDataRepository(
        [
            _source("one", "https://example.test/one", "One"),
            _source("two", "https://example.test/one/", "Duplicate"),
            _source("three", "https://example.test/three", "Three"),
        ]
    )
    curator = FakeCurator(curator_outputs)
    GoodPublisher.received = []
    publishing = PublishingService(
        FakePublisherRegistry({"good": GoodPublisher, "bad": BadPublisher}),  # type: ignore[arg-type]
        {
            "good": lambda digest: digest,
            "bad": lambda digest: digest,
        },
    )
    return (
        DailyDigestPipeline(
            ingestion, repository, curator, publishing, config, RetryOnceReflector()
        ),
        curator,
        ingestion,
    )


def test_workflow_declares_five_nodes_and_data_dependencies() -> None:
    """The user-facing workflow definition remains a five-node declarative DAG."""
    workflow = build_daily_digest_workflow(DailyDigestConfig(curate_agent_id="curator"))

    assert [step.id for step in workflow.steps] == [
        "ingest",
        "dedupe",
        "curate",
        "overview",
        "fanout",
    ]
    assert workflow.steps[-1].input_map == {"curated": "curate", "overview": "overview"}
    assert workflow.steps[2].max_iterations == 3
    assert workflow.steps[2].exit_condition == "llm"


def test_explicit_empty_targets_disable_default_publishers() -> None:
    """An explicit empty target list is a preview-only run, while omission keeps defaults."""
    preview = DailyDigestConfig.from_mapping({"curate_agent_id": "curator", "targets": []})
    default = DailyDigestConfig.from_mapping({"curate_agent_id": "curator"})

    assert preview.targets == []
    assert default.targets == ["feishu_bot", "wecom_bot"]


@pytest.mark.asyncio
async def test_daily_digest_runs_end_to_end_with_dedupe_top_n_loop_and_fanout() -> None:
    """Mocked pipeline retries curation, sorts selected entries, and isolates a target error."""
    pipeline, curator, ingestion = _pipeline(
        [_curation_json(), _curation_json(), "今日重点资讯概览"]
    )

    result = await pipeline.run(run_date="2026-07-17")

    assert result["result_count"] == 2
    assert [item["title"] for item in result["curated"]] == ["Three", "One"]
    assert result["overview"] == "今日重点资讯概览"
    assert result["targets"]["good"]["status"] == "success"
    assert result["targets"]["bad"]["status"] == "error"
    assert ingestion.calls == [
        [{"adapter_id": "rss", "config": {"url": "https://feed.example.test"}}]
    ]
    assert "improve summaries" in curator.inputs[1]
    assert len(GoodPublisher.received) == 1
    digest = GoodPublisher.received[0]
    assert isinstance(digest, CuratedDigest)
    assert [item.title for item in digest.items] == ["Three", "One"]
    assert digest.total_scanned == 2


@pytest.mark.asyncio
async def test_stream_exposes_loop_iteration_and_invalid_json_becomes_workflow_error() -> None:
    """Loop observability and JSON extraction failure are both visible to callers."""
    pipeline, _, _ = _pipeline([_curation_json(), _curation_json(), "overview"])
    events = [event async for event in pipeline.stream(run_date="2026-07-17")]
    assert [event.type for event in events].count("loop_iteration") == 2

    invalid_pipeline, _, _ = _pipeline(["not JSON"])
    with pytest.raises(WorkflowError, match="valid JSON"):
        await invalid_pipeline.run(run_date="2026-07-17")


@pytest.mark.asyncio
async def test_registered_scheduler_callback_runs_daily_digest_task() -> None:
    """P9 registry receives the daily-digest callback and can invoke it directly."""
    pipeline, _, _ = _pipeline([_curation_json(), _curation_json(), "overview"])
    registry = TaskExecutorRegistry()
    register_daily_digest_executor(registry, pipeline)
    task = ScheduleTask(
        id="daily",
        name="Daily digest",
        task_type="daily_digest",
        cron="0 9 * * *",
        config={
            "curate_agent_id": "curator",
            "adapter_ids": ["rss"],
            "top_n": 2,
            "targets": ["good", "bad"],
            "adapter_configs": {"rss": {"url": "https://feed.example.test"}},
        },
    )

    callback = registry.get("daily_digest")
    assert callback is not None
    result = await callback(task)
    assert result["result_count"] == 2
