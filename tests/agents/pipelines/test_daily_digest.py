"""Tests for the P11 daily ingest, curate, loop, and publish workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import ClassVar

import pytest

from multiscribe_agent.agents.pipelines.daily_digest import (
    DailyDigestConfig,
    DailyDigestPipeline,
    _article_preview_image,
    _curate_item_dict,
    _prioritize_digest_sections,
    _supplement_curated_items,
    build_daily_digest_workflow,
    register_daily_digest_executor,
)
from multiscribe_agent.agents.pipelines.prompts import CURATE_PROMPT, DIGEST_OVERVIEW_PROMPT
from multiscribe_agent.core.errors import AgentStepTerminalError, WorkflowError
from multiscribe_agent.core.pushed_content import PushedContentRepository
from multiscribe_agent.domain.models import MemoryEntry, ScheduleTask, SourceData, UnifiedData
from multiscribe_agent.infra.db import Database, init_db
from multiscribe_agent.memory.preference_store import UserPreferences
from multiscribe_agent.renderers.feishu_card import DigestItem
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

    def __init__(
        self,
        entries: list[SourceData],
        entries_by_field: dict[str, list[SourceData]] | None = None,
    ) -> None:
        self._entries = entries
        self._entries_by_field = entries_by_field or {}
        self.ranges: list[tuple[str, str, str]] = []

    async def get_by_date_range(
        self, start: str, end: str, query_field: str = "ingestion_date"
    ) -> list[SourceData]:
        """Record query bounds and return the configured records."""
        self.ranges.append((start, end, query_field))
        return self._entries_by_field.get(query_field, self._entries)


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


class MemoryAwareFakeCurator(FakeCurator):
    """Curator double that exposes the summaries supplied to its harness context."""

    def __init__(self, outputs: list[str]) -> None:
        super().__init__(outputs)
        self.memory_summaries: list[str] = []

    async def execute_with_memory(
        self, agent_id: str, user_input: str, memory_summaries: list[str]
    ) -> str:
        self.memory_summaries = memory_summaries
        return await self.execute(agent_id, user_input)


class TerminalOverviewCurator(FakeCurator):
    """Fail the overview Agent with a structured context-budget terminal state."""

    async def execute(self, agent_id: str, user_input: str) -> str:
        if len(self.inputs) == 2:
            self.inputs.append(user_input)
            raise AgentStepTerminalError(
                "context_budget_exhausted",
                "overview context exhausted",
                {"actual": 2_000, "limit": 1_000},
            )
        return await super().execute(agent_id, user_input)


class FakeMemoryService:
    """Small retrieval boundary used to exercise digest memory injection and degradation."""

    def __init__(
        self, preferences: UserPreferences, entries: list[MemoryEntry], fail: bool = False
    ) -> None:
        self._preferences = preferences
        self._entries = entries
        self._fail = fail

    async def get_preferences(self) -> UserPreferences:
        if self._fail:
            raise RuntimeError("memory unavailable")
        return self._preferences

    async def search_entries(self, query: str, limit: int = 20) -> list[MemoryEntry]:
        del query, limit
        if self._fail:
            raise RuntimeError("memory unavailable")
        return self._entries


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


class FakePushedContentRepository:
    """In-memory cross-day identity store for pipeline behavior tests."""

    def __init__(self, records: list[tuple[str, str, str, str]] | None = None) -> None:
        self.records = records or []

    async def add(
        self,
        db: Database,
        *,
        content_hash: str,
        url: str,
        digest_date: str,
        title: str,
    ) -> None:
        """Record an item once per content hash and digest date."""
        del db
        key = (content_hash, digest_date)
        if not any((item[0], item[2]) == key for item in self.records):
            normalized_url = url.strip().rstrip("/").casefold()
            self.records.append((content_hash, normalized_url, digest_date, title))

    async def recent_hashes(self, db: Database, *, since_date: str) -> set[str]:
        """Return hashes in the inclusive date window."""
        del db
        return {
            content_hash
            for content_hash, _, digest_date, _ in self.records
            if digest_date >= since_date
        }

    async def recent_urls(self, db: Database, *, since_date: str) -> set[str]:
        """Return normalized URLs in the inclusive date window."""
        del db
        return {url for _, url, digest_date, _ in self.records if digest_date >= since_date}


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
        metadata={
            "tags": ["engineering"],
            "image_url": "https://example.test/one.jpg" if item_id == "one" else None,
            "video_url": "https://example.test/one.mp4" if item_id == "one" else None,
        },
    )


def _curation_json() -> str:
    """Return intentionally unordered LLM scores for top-N sorting tests."""
    return (
        '[{"id":"one","title":"One","summary":"摘要一","score":4,"score_reason":"ok"},'
        '{"id":"three","title":"Three","summary":"摘要三","score":9,"score_reason":"important"}]'
    )


def _pipeline(
    curator_outputs: list[str],
    *,
    curator: FakeCurator | None = None,
    memory_service: FakeMemoryService | None = None,
    adapter_configs: dict[str, dict[str, object]] | None = None,
    source_data_by_field: dict[str, list[SourceData]] | None = None,
    adapter_ids: list[str] | None = None,
    db: Database | None = None,
    pushed_content_repo: FakePushedContentRepository | PushedContentRepository | None = None,
    fetch_days: int = 2,
    targets: list[str] | None = None,
) -> tuple[DailyDigestPipeline, FakeCurator, FakeIngestionService]:
    """Assemble a fully mocked pipeline with a duplicate URL source record."""
    config = DailyDigestConfig(
        curate_agent_id="curator",
        adapter_ids=adapter_ids or ["rss"],
        fetch_days=fetch_days,
        top_n=2,
        targets=targets if targets is not None else ["good", "bad"],
        adapter_configs=adapter_configs or {"rss": {"url": "https://feed.example.test"}},
    )
    ingestion = FakeIngestionService()
    repository = FakeSourceDataRepository(
        [
            _source("one", "https://example.test/one", "One"),
            _source("two", "https://example.test/one/", "Duplicate"),
            _source("three", "https://example.test/three", "Three"),
        ],
        source_data_by_field,
    )
    curator = curator or FakeCurator(curator_outputs)
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
            ingestion,
            repository,
            curator,
            publishing,
            config,
            RetryOnceReflector(),
            db=db,
            memory_service=memory_service,
            pushed_content_repo=pushed_content_repo,
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


def test_curate_projection_excludes_full_content_and_bounds_one_hundred_candidates() -> None:
    """Curation receives minimal fields and stays below 30% for mixed candidates."""
    descriptions = ["长" * 1_500] * 20 + ["中" * 70] * 50 + ["短" * 35] * 30
    items = [
        UnifiedData(
            id=f"item-{index}",
            title=f"Title {index}",
            url=f"https://example.test/{index}",
            description=description,
            published_date="2026-07-17T08:00:00+00:00",
            source="RSS",
            category="technology",
            author="Author",
            metadata={"raw": "metadata" * 100},
            ingestion_date="2026-07-17T08:01:00+00:00",
            adapter_name="rss",
        )
        for index, description in enumerate(descriptions)
    ]
    projected = [_curate_item_dict(item) for item in items]
    new_prompt = CURATE_PROMPT.format(
        items=json.dumps(projected, ensure_ascii=False, separators=(",", ":")),
        feedback="无",
        target_count=12,
    )
    old_prompt = CURATE_PROMPT.format(
        items=json.dumps(
            [item.model_dump(mode="json") for item in items],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        feedback="无",
        target_count=12,
    )

    assert set(projected[0]) == {"id", "title", "summary"}
    assert all(len(str(item["summary"])) <= 150 for item in projected)
    assert len(new_prompt) < len(old_prompt) * 0.30


def test_daily_digest_prompts_require_chinese_page_content() -> None:
    """English sources are translated before the digest is archived and published."""
    assert "title 必须将原标题翻译或改写为" in CURATE_PROMPT
    assert "summary 必须使用中文" in CURATE_PROMPT
    assert "目标范围为 10 到 15 条" in CURATE_PROMPT
    assert "{target_count}" in CURATE_PROMPT
    assert "只返回中文概览正文" in DIGEST_OVERVIEW_PROMPT


def test_article_preview_image_prefers_safe_open_graph_metadata() -> None:
    """Article metadata supplies a preview only when it resolves to HTTP(S)."""
    html = '<meta property="og:image" content="/images/preview.jpg"><meta name="twitter:image" content="https://example.test/ignored.jpg">'

    assert _article_preview_image(html, "https://example.test/news/article") == (
        "https://example.test/images/preview.jpg"
    )
    assert (
        _article_preview_image(
            '<meta property="og:image" content="data:image/png;base64,x">', "https://example.test"
        )
        is None
    )


def test_section_priority_keeps_all_available_digest_sections() -> None:
    """Section coverage wins over score ordering when the configured limit allows it."""
    items = [
        DigestItem(
            "产品", "摘要", "https://example.test/product", "rss", 10.0, section="产品与功能更新"
        ),
        DigestItem("研究", "摘要", "https://example.test/research", "rss", 7.0, section="前沿研究"),
        DigestItem(
            "影响", "摘要", "https://example.test/impact", "rss", 6.0, section="行业展望与社会影响"
        ),
        DigestItem(
            "开源",
            "摘要",
            "https://example.test/oss",
            "github_trending",
            5.0,
            section="开源TOP项目",
        ),
        DigestItem(
            "补充", "摘要", "https://example.test/extra", "rss", 9.0, section="产品与功能更新"
        ),
    ]

    selected = _prioritize_digest_sections(items, 4)

    assert {item.section for item in selected} == {
        "产品与功能更新",
        "前沿研究",
        "行业展望与社会影响",
        "开源TOP项目",
    }


def test_supplement_curated_items_fills_short_selection_with_diverse_candidates() -> None:
    """Fallback selection fills the configured count without duplicate links or excess trends."""
    curated = [
        DigestItem(
            "Product",
            "summary",
            "https://example.test/product",
            "rss",
            9.0,
            section="产品与功能更新",
        )
    ]
    candidates = [
        UnifiedData(
            id="duplicate",
            title="Duplicate product",
            url="https://example.test/product",
            description="duplicate",
            published_date="2026-07-17T08:00:00+00:00",
            source="rss",
            category="technology",
        ),
        UnifiedData(
            id="research",
            title="Research paper",
            url="https://example.test/research",
            description="A new AI research paper.",
            published_date="2026-07-17T08:00:00+00:00",
            source="rss",
            category="technology",
        ),
        UnifiedData(
            id="impact",
            title="AI policy update",
            url="https://example.test/impact",
            description="New regulation for AI safety.",
            published_date="2026-07-17T08:00:00+00:00",
            source="rss",
            category="technology",
        ),
        *[
            UnifiedData(
                id=f"trend-{index}",
                title=f"Trending project {index}",
                url=f"https://example.test/trend-{index}",
                description="Open source AI project.",
                published_date="2026-07-17T08:00:00+00:00",
                source="github_trending",
                category="technology",
            )
            for index in range(3)
        ],
        *[
            UnifiedData(
                id=f"extra-{index}",
                title=f"Product update {index}",
                url=f"https://example.test/extra-{index}",
                description="AI product update.",
                published_date="2026-07-17T08:00:00+00:00",
                source="rss",
                category="technology",
            )
            for index in range(3)
        ],
    ]

    selected = _supplement_curated_items(curated, candidates, 7)

    assert len(selected) == 7
    assert len({item.url for item in selected}) == 7
    assert {item.section for item in selected} == {
        "产品与功能更新",
        "前沿研究",
        "行业展望与社会影响",
        "开源TOP项目",
    }
    assert sum(item.source == "github_trending" for item in selected) <= 2


def test_supplement_curated_items_replaces_excess_items_to_restore_missing_sections() -> None:
    """A full but one-note model response still renders each supported digest section."""
    curated = [
        DigestItem(
            f"Product {index}",
            "summary",
            f"https://example.test/product-{index}",
            "rss",
            float(10 - index),
            section="产品与功能更新",
        )
        for index in range(4)
    ]
    candidates = [
        UnifiedData(
            id="research",
            title="Research paper",
            url="https://example.test/research",
            description="A new AI research paper.",
            published_date="2026-07-17T08:00:00+00:00",
            source="rss",
            category="technology",
        ),
        UnifiedData(
            id="impact",
            title="AI policy",
            url="https://example.test/impact",
            description="New regulation for AI safety.",
            published_date="2026-07-17T08:00:00+00:00",
            source="rss",
            category="technology",
        ),
        UnifiedData(
            id="trend",
            title="Trending project",
            url="https://example.test/trend",
            description="Open source AI project.",
            published_date="2026-07-17T08:00:00+00:00",
            source="github_trending",
            category="technology",
        ),
    ]

    selected = _supplement_curated_items(curated, candidates, 4)

    assert {item.section for item in selected} == {
        "产品与功能更新",
        "前沿研究",
        "行业展望与社会影响",
        "开源TOP项目",
    }


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
        [
            {
                "adapter_id": "rss",
                "enabled": True,
                "config": {"url": "https://feed.example.test"},
            }
        ]
    ]
    assert "improve summaries" in curator.inputs[1]
    assert len(GoodPublisher.received) == 1
    digest = GoodPublisher.received[0]
    assert isinstance(digest, CuratedDigest)
    assert [item.title for item in digest.items] == ["Three", "One"]
    assert digest.items[1].image_url == "https://example.test/one.jpg"
    assert digest.items[1].video_url == "https://example.test/one.mp4"
    assert digest.items[1].tags == ("engineering", "technology")
    assert digest.total_scanned == 2


@pytest.mark.asyncio
async def test_multi_feed_run_excludes_stale_rss_rows_from_other_feeds() -> None:
    """An explicit multi-feed task must not re-curate a previous BBC-style RSS row."""
    pipeline, curator, _ = _pipeline(
        [
            '[{"id":"one","title":"AI update","summary":"summary","score":9}]',
            '[{"id":"one","title":"AI update","summary":"summary","score":9}]',
            "overview",
        ],
        adapter_configs={"rss": {"rss_urls": ["https://huggingface.co/blog/feed.xml"]}},
    )
    repository = pipeline._source_data_repo
    assert isinstance(repository, FakeSourceDataRepository)
    repository._entries[0].metadata["feed_url"] = "https://huggingface.co/blog/feed.xml"

    result = await pipeline.run(run_date="2026-07-17")

    assert result["result_count"] == 1
    assert "Duplicate" not in curator.inputs[0]
    assert "Three" not in curator.inputs[0]


@pytest.mark.asyncio
async def test_daily_digest_uses_publication_dates_but_keeps_current_trending_snapshot() -> None:
    """Old re-ingested articles cannot enter, while today's GitHub ranking can."""
    fresh_rss = _source("fresh-rss", "https://example.test/fresh", "Fresh RSS")
    stale_rss = _source("stale-rss", "https://example.test/stale", "Stale RSS")
    github_snapshot = _source("github", "https://github.com/example/project", "Trending project")
    github_snapshot = github_snapshot.model_copy(
        update={
            "published_date": "1970-01-01T00:00:00+00:00",
            "source": "github_trending",
            "adapter_name": "github_trending",
        }
    )
    unknown_ai_search = _source("search", "https://example.test/search", "Unverified search")
    unknown_ai_search = unknown_ai_search.model_copy(
        update={
            "published_date": "1970-01-01T00:00:00+00:00",
            "source": "ai_search:perplexity",
            "adapter_name": "ai_search",
        }
    )
    curation = (
        '[{"id":"fresh-rss","title":"Fresh RSS","summary":"fresh","score":9},'
        '{"id":"github","title":"Trending project","summary":"trend","score":8}]'
    )
    pipeline, curator, _ = _pipeline(
        [curation, curation, "overview"],
        adapter_ids=["rss", "github_trending", "ai_search"],
        source_data_by_field={
            "published_date": [fresh_rss],
            "fetched_at": [stale_rss, github_snapshot, unknown_ai_search],
        },
    )

    result = await pipeline.run(run_date="2026-07-17")

    assert result["result_count"] == 2
    assert "Fresh RSS" in curator.inputs[0]
    assert "Trending project" in curator.inputs[0]
    assert "Stale RSS" not in curator.inputs[0]
    assert "Unverified search" not in curator.inputs[0]


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
async def test_daily_digest_does_not_publish_agent_budget_error_as_overview() -> None:
    curator = TerminalOverviewCurator([_curation_json(), _curation_json()])
    pipeline, _, _ = _pipeline(
        [_curation_json(), _curation_json()],
        curator=curator,
    )

    with pytest.raises(WorkflowError) as captured:
        await pipeline.run(run_date="2026-07-17")

    assert captured.value.details["terminal_type"] == "context_budget_exhausted"
    assert GoodPublisher.received == []


@pytest.mark.asyncio
async def test_daily_digest_applies_memory_constraints_and_injects_preferences() -> None:
    """Blocked topics stay out of the curator while matching durable memory reaches it."""
    curator = MemoryAwareFakeCurator([_curation_json(), _curation_json(), "overview"])
    memory = FakeMemoryService(
        UserPreferences(["technology"], [], "09:00", 0, blocked_topics=["one description"]),
        [
            MemoryEntry(
                id="memory-1",
                content="Prioritize practical Agent and RAG engineering updates.",
                importance=9,
                tags=["technology"],
                created_at=1_700_000_000,
                metadata={"trusted": True},
            )
        ],
    )
    pipeline, _, _ = _pipeline(
        [_curation_json(), _curation_json(), "overview"],
        curator=curator,
        memory_service=memory,
    )

    result = await pipeline.run(run_date="2026-07-17")

    assert result["result_count"] == 1
    assert '"id":"one"' not in curator.inputs[0]
    assert '"id": "three"' in curator.inputs[0]
    assert curator.memory_summaries == [
        "Preference memory (importance=9; tags=technology): "
        "Prioritize practical Agent and RAG engineering updates."
    ]


@pytest.mark.asyncio
async def test_daily_digest_degrades_when_memory_is_unavailable() -> None:
    """A memory outage keeps the original curation and publishing path available."""
    unavailable = FakeMemoryService(UserPreferences([], [], "09:00", 0), [], fail=True)
    pipeline, curator, _ = _pipeline(
        [_curation_json(), _curation_json(), "overview"], memory_service=unavailable
    )

    result = await pipeline.run(run_date="2026-07-17")

    assert result["result_count"] == 2
    assert len(curator.inputs) == 3


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


@pytest.mark.asyncio
async def test_daily_digest_excludes_recent_pushed_hash_and_url_and_keeps_new_candidate() -> None:
    """Cross-day dedupe removes both identity forms while retaining unrelated content."""
    database = await init_db(":memory:")
    try:
        repository = FakePushedContentRepository(
            [
                (
                    sha256(b"One\nOne description").hexdigest(),
                    "https://example.test/one",
                    "2026-07-16",
                    "One",
                ),
                (
                    "unrelated-hash",
                    "https://example.test/other",
                    "2026-07-16",
                    "Other",
                ),
            ]
        )
        pipeline, curator, _ = _pipeline(
            [_curation_json(), _curation_json(), "overview"],
            db=database,
            pushed_content_repo=repository,
        )

        result = await pipeline.run(run_date="2026-07-17")

        assert result["result_count"] == 1
        assert '"id":"one"' not in curator.inputs[0]
        assert '"id": "three"' in curator.inputs[0]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_daily_digest_fetch_days_controls_cross_day_exclusion_window() -> None:
    """A record outside fetch_days remains eligible for the current digest."""
    database = await init_db(":memory:")
    try:
        repository = FakePushedContentRepository(
            [
                (
                    sha256(b"One\nOne description").hexdigest(),
                    "https://example.test/one",
                    "2026-07-14",
                    "One",
                )
            ]
        )
        pipeline, curator, _ = _pipeline(
            [_curation_json(), _curation_json(), "overview"],
            db=database,
            pushed_content_repo=repository,
            fetch_days=2,
        )

        result = await pipeline.run(run_date="2026-07-17")

        assert result["result_count"] == 2
        assert '"id": "one"' in curator.inputs[0]
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_daily_digest_fallback_candidates_are_sorted_newest_first() -> None:
    """The no-memory fallback sends the newest candidates to the curator first."""
    pipeline, curator, _ = _pipeline(["[]", "[]", "overview"])
    source_repo = pipeline._source_data_repo
    assert isinstance(source_repo, FakeSourceDataRepository)
    source_repo._entries[0] = source_repo._entries[0].model_copy(
        update={"published_date": "2026-07-15T08:00:00+00:00"}
    )
    source_repo._entries[2] = source_repo._entries[2].model_copy(
        update={"published_date": "2026-07-17T08:00:00+00:00"}
    )

    await pipeline.run(run_date="2026-07-17")

    assert curator.inputs[0].index('"id": "three"') < curator.inputs[0].index('"id": "one"')


@pytest.mark.asyncio
async def test_daily_digest_records_all_items_after_one_successful_publisher() -> None:
    """A partial fan-out success records every selected item for future dedupe."""
    database = await init_db(":memory:")
    try:
        repository = PushedContentRepository()
        pipeline, _, _ = _pipeline(
            [_curation_json(), _curation_json(), "overview"],
            db=database,
            pushed_content_repo=repository,
        )

        result = await pipeline.run(run_date="2026-07-17")

        rows = await database.fetchall("SELECT url, digest_date FROM pushed_content")
        assert result["targets"]["good"]["status"] == "success"
        assert len(rows) == result["result_count"]
        assert {str(row["digest_date"]) for row in rows} == {"2026-07-17"}
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_daily_digest_does_not_record_items_when_all_publishers_fail() -> None:
    """A fully failed fan-out must not poison the next day's exclusion set."""
    database = await init_db(":memory:")
    try:
        repository = PushedContentRepository()
        pipeline, _, _ = _pipeline(
            [_curation_json(), _curation_json(), "overview"],
            db=database,
            pushed_content_repo=repository,
            targets=["bad"],
        )

        result = await pipeline.run(run_date="2026-07-17")

        rows = await database.fetchall("SELECT content_hash FROM pushed_content")
        assert result["targets"]["bad"]["status"] == "error"
        assert rows == []
    finally:
        await database.close()
