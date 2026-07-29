"""Application composition root for services, registries, and scheduled callbacks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from multiscribe_agent.agents.context_provider import MemoryKnowledgeContextProvider
from multiscribe_agent.agents.executor import AgentExecutor
from multiscribe_agent.agents.pipelines.daily_digest import (
    OVERVIEW_AGENT_ID,
    DailyDigestConfig,
    DailyDigestPipeline,
)
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.agents.reflector import Reflector
from multiscribe_agent.agents.workflow.engine import WorkflowEngine
from multiscribe_agent.agents.workflow.iteration_store import IterationStore
from multiscribe_agent.agents.workflow.protocols import LoopAssessment
from multiscribe_agent.config import ConfigService, SystemSettings, get_settings
from multiscribe_agent.core.adapter_health import AdapterHealthRepository
from multiscribe_agent.core.click_events import ClickEventRepository
from multiscribe_agent.core.daily_digest_archive import get_daily_digest_archive
from multiscribe_agent.core.errors import AgentStepTerminalError, ProviderError
from multiscribe_agent.core.event_bus import EventBus, get_event_bus
from multiscribe_agent.core.publish_history import PublishHistory, get_publish_history
from multiscribe_agent.core.pushed_content import PushedContentRepository
from multiscribe_agent.domain.models import (
    AgentDefinition,
    AgentRunResult,
    ScheduleTask,
    TokenUsage,
)
from multiscribe_agent.infra.db import Database, init_db
from multiscribe_agent.infra.redis_client import close_redis
from multiscribe_agent.infra.repositories.curation_evaluations import (
    CurationEvaluationRepository,
)
from multiscribe_agent.infra.repositories.daily_usage import DailyUsageRepository
from multiscribe_agent.infra.repositories.entity_json import EntityJsonRepository
from multiscribe_agent.infra.repositories.kv import KvRepository
from multiscribe_agent.infra.repositories.source_data import SourceDataRepository
from multiscribe_agent.infra.repositories.task_log import TaskLogRepository
from multiscribe_agent.knowledge.document_processor import DocumentProcessor
from multiscribe_agent.knowledge.embedding_service import EmbeddingService
from multiscribe_agent.knowledge.kb_service import KBCapabilities, KBService
from multiscribe_agent.knowledge.retriever import Retriever
from multiscribe_agent.knowledge.vector_store import VectorStore
from multiscribe_agent.llm.provider import AIProvider, create_provider
from multiscribe_agent.memory.extractor import PreferenceExtractor
from multiscribe_agent.memory.memory_service import MemoryService
from multiscribe_agent.memory.preference_store import PreferenceStore, UserPreferences
from multiscribe_agent.memory.repositories.memory_categories import MemoryCategoryRepository
from multiscribe_agent.memory.repositories.memory_entries import MemoryEntryRepository
from multiscribe_agent.observability.alerts import AlertEngine, load_rules
from multiscribe_agent.observability.meter import MetricsRegistry, set_metrics_registry
from multiscribe_agent.observability.optional import ObservabilityCapabilities, detect
from multiscribe_agent.observability.publisher_alert_callback import PublisherAlertCallback
from multiscribe_agent.observability.sql_audit import SqlAuditLogger
from multiscribe_agent.observability.tracer import setup_tracer
from multiscribe_agent.plugins.builtin.adapters.ai_search import AISearchAdapter
from multiscribe_agent.plugins.builtin.tools.execute_command import ExecuteCommandTool
from multiscribe_agent.plugins.builtin.tools.read_artifact import ReadArtifactTool
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import AdapterRegistry, PublisherRegistry, ToolRegistry
from multiscribe_agent.renderers.feishu_card import render_digest_card
from multiscribe_agent.renderers.wecom_markdown import render_digest_markdown
from multiscribe_agent.services.adapter_health_alerter import AdapterHealthAlerter
from multiscribe_agent.services.ingestion import IngestionService
from multiscribe_agent.services.interop import InteropService
from multiscribe_agent.services.interop_rate_limit import SlidingWindowLimiter
from multiscribe_agent.services.interop_registry import (
    ToolRegistry as InteropToolRegistry,
)
from multiscribe_agent.services.interop_registry import (
    build_default_registry,
)
from multiscribe_agent.services.preference_feedback import PreferenceFeedbackService
from multiscribe_agent.services.publishing import PublishingService
from multiscribe_agent.services.scheduler import SchedulerService, TaskExecutorRegistry
from multiscribe_agent.services.scheduler_lock import RedisSchedulerLock, SchedulerLock
from multiscribe_agent.skills.builtin_loader import load_builtin_skills
from multiscribe_agent.skills.frontmatter_parser import parse_frontmatter
from multiscribe_agent.skills.registry import get_skill_registry
from multiscribe_agent.skills.scanner import SkillScanner
from multiscribe_agent.skills.service import SkillService

DEFAULT_CURATION_AGENT_ID = "default-curation-agent"
DEFAULT_OVERVIEW_AGENT_PROMPT = (
    "You are a Chinese daily news digest writer. Given curated items, write a concise, "
    "natural-language overview in Chinese (no more than 180 characters) that summarizes the "
    "highlights. Do not output JSON, markdown, or English headings. Keep necessary product "
    "names and technical terms in their original form."
)
DEFAULT_DAILY_AI_NEWS_TASK_ID = "daily-ai-news"
_LEGACY_DAILY_AI_NEWS_TOP_N = frozenset({5, 10})
_DEFAULT_DAILY_AI_NEWS_TOP_N = 12
_LEGACY_DAILY_AI_NEWS_RSS_URLS = [
    "https://huggingface.co/blog/feed.xml",
    "https://openai.com/news/rss.xml",
    "https://www.deeplearning.ai/the-batch/rss/",
]
_LEGACY_DEFAULT_CURATION_AGENT_PROMPT = (
    "You are a news curation assistant. Select the five most useful items from the input "
    "and return a JSON array whose entries contain id, title, summary, and score from 0 to 10."
)
DEFAULT_CURATION_AGENT_PROMPT = (
    "You are a news curation assistant. Follow the task-specific selection count and section "
    "coverage requirements, then return a JSON array containing id, title, summary, score, "
    "score_reason, and section."
)


@dataclass(slots=True)
class _ProviderLoopReflector:
    """Adapt P4's provider-aware reflector to P10's narrow loop protocol."""

    reflector: Reflector
    provider: AIProvider
    usage_sink: Callable[[TokenUsage], None] | None = None

    def set_usage_sink(self, sink: Callable[[TokenUsage], None]) -> None:
        """Attach a per-run usage collector without changing the loop protocol."""
        self.usage_sink = sink

    async def assess(self, task: str, output: str) -> LoopAssessment:
        """Assess loop output with the provider selected for the curation agent."""
        reflection = await self.reflector.assess(task, output, self.provider)
        if reflection.usage is not None and self.usage_sink is not None:
            self.usage_sink(reflection.usage)
        return _MutableLoopAssessment(
            reflection.should_retry,
            reflection.feedback,
            reflection.score,
            reflection.usage,
        )


@dataclass(slots=True)
class _MutableLoopAssessment:
    """Writable protocol view of P4's frozen Reflection result."""

    should_retry: bool
    feedback: str
    score: float
    usage: TokenUsage | None = None


class _StoredAgentStepExecutor:
    """Resolve workflow agent IDs from the entity store before invoking P4's executor."""

    def __init__(self, agents: EntityJsonRepository, executor: AgentExecutor) -> None:
        self._agents = agents
        self._executor = executor

    async def execute(self, agent_id: str, user_input: str) -> str:
        """Execute one stored AgentDefinition through the existing harness."""
        raw = await self._agents.get("agents", agent_id)
        if raw is None:
            raise LookupError(f"agent not found: {agent_id}")
        return await self._execute_definition(AgentDefinition.model_validate(raw), user_input)

    async def execute_with_memory(
        self, agent_id: str, user_input: str, memory_summaries: list[str]
    ) -> str:
        """Execute a stored agent while injecting bounded durable-memory summaries."""
        raw = await self._agents.get("agents", agent_id)
        if raw is None:
            raise LookupError(f"agent not found: {agent_id}")
        return await self._execute_definition(
            AgentDefinition.model_validate(raw), user_input, memory_summaries
        )

    async def execute_observed(
        self, agent_id: str, user_input: str
    ) -> tuple[str, TokenUsage | None]:
        """Execute an agent and return its provider usage alongside the output."""
        raw = await self._agents.get("agents", agent_id)
        if raw is None:
            raise LookupError(f"agent not found: {agent_id}")
        result = await self._execute_result(AgentDefinition.model_validate(raw), user_input)
        self._raise_if_terminal(result)
        return result.content, result.usage

    async def execute_observed_with_memory(
        self,
        agent_id: str,
        user_input: str,
        memory_summaries: list[str],
    ) -> tuple[str, TokenUsage | None]:
        """Execute an agent with memory injection while preserving provider usage."""
        raw = await self._agents.get("agents", agent_id)
        if raw is None:
            raise LookupError(f"agent not found: {agent_id}")
        result = await self._execute_result(
            AgentDefinition.model_validate(raw), user_input, memory_summaries
        )
        self._raise_if_terminal(result)
        return result.content, result.usage

    async def _execute_definition(
        self,
        definition: AgentDefinition,
        user_input: str,
        memory_summaries: list[str] | None = None,
    ) -> str:
        result = await self._execute_result(definition, user_input, memory_summaries)
        if result.status != "success":
            raise AgentStepTerminalError(
                result.status,
                result.content,
                result.terminal_data,
            )
        return result.content

    async def _execute_result(
        self,
        definition: AgentDefinition,
        user_input: str,
        memory_summaries: list[str] | None = None,
    ) -> AgentRunResult:
        """Run one stored definition and preserve the structured result for observers."""
        return await self._executor.run_result(
            definition, user_input, memory_summaries=memory_summaries
        )

    @staticmethod
    def _raise_if_terminal(result: AgentRunResult) -> None:
        """Convert non-success agent results into the workflow terminal error contract."""
        if result.status != "success":
            raise AgentStepTerminalError(result.status, result.content, result.terminal_data)


# 负责装配配置、Agent、工作流、采集服务和发布服务,保证 API、CLI、调度任务复用同一套运行时依赖
class ServiceContext:
    """Lazily initialize and reload the concrete service graph for API and CLI use."""

    def __init__(self, settings: SystemSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db: Database | None = None
        self.entities: EntityJsonRepository | None = None
        self.task_logs: TaskLogRepository | None = None
        self.source_data: SourceDataRepository | None = None
        self.ingestion: IngestionService | None = None
        self.adapter_health_repo: AdapterHealthRepository | None = None
        self.publishing: PublishingService | None = None
        self.tools: ToolRegistry | None = None
        self.agent_executor: AgentExecutor | None = None
        self.workflow_engine: WorkflowEngine | None = None
        self.iteration_store: IterationStore | None = None
        self.scheduler: SchedulerService | None = None
        self.daily_usage: DailyUsageRepository | None = None
        self.curation_evaluations: CurationEvaluationRepository | None = None
        self.scheduler_lock: SchedulerLock | None = None
        self.config_service: ConfigService | None = None
        self.publish_history: PublishHistory | None = None
        self.pushed_content: PushedContentRepository | None = None
        self.click_events: ClickEventRepository | None = None
        self.preference_store: PreferenceStore | None = None
        self.preference_feedback: PreferenceFeedbackService | None = None
        self.kb_service: KBService | None = None
        self.kb_capabilities: KBCapabilities | None = None
        self.memory_service: MemoryService | None = None
        self.skill_service: SkillService | None = None
        self.interop_service: InteropService | None = None
        self.interop_limiter: SlidingWindowLimiter | None = None
        self.interop_registry: InteropToolRegistry | None = None
        self.observability_capabilities: ObservabilityCapabilities | None = None
        self.metrics: MetricsRegistry | None = None
        self.tracer: object | None = None
        self.event_bus: EventBus | None = None
        self.alerts: AlertEngine | None = None
        self.sql_audit: SqlAuditLogger | None = None
        self._initialized = False

    async def init(self) -> None:
        """Initialize database, plugins, services, executor adapters, and scheduler."""
        if self._initialized:
            return
        self.db = await init_db(
            self.settings.db_path,
            slow_query_threshold=self.settings.slow_query_threshold_seconds,
            enable_sql_audit=self.settings.enable_sql_audit,
            use_pool=True,
        )
        self.iteration_store = IterationStore(self.db)
        self.daily_usage = DailyUsageRepository(self.db)
        await self.daily_usage.ensure_schema()
        self.curation_evaluations = CurationEvaluationRepository(self.db)
        await self.curation_evaluations.ensure_schema()
        if self.settings.enable_sql_audit:
            self.sql_audit = SqlAuditLogger(self.db)
            self.db.set_audit_logger(self.sql_audit)
        rules_path = Path(__file__).parent / "observability" / "alert_rules.yaml"
        self.alerts = AlertEngine(load_rules(rules_path))
        self.observability_capabilities = detect()
        self.metrics = MetricsRegistry.create(self.observability_capabilities)
        self.metrics.alert_engine = self.alerts
        set_metrics_registry(self.metrics)
        self.tracer = setup_tracer()
        self.event_bus = get_event_bus()
        self.interop_service = InteropService(self.db)
        self.interop_limiter = SlidingWindowLimiter(window_seconds=60)
        self.publish_history = get_publish_history()
        self.pushed_content = PushedContentRepository()
        self.click_events = ClickEventRepository()
        entities = EntityJsonRepository(self.db)
        task_logs = TaskLogRepository(self.db)
        source_data = SourceDataRepository(self.db)
        kv = KvRepository(self.db)
        # Keep explicitly supplied runtime settings (notably a test or deployment
        # database path) as the base layer when reload rebuilds the service graph.
        self.config_service = ConfigService(kv, base_settings=self.settings)
        self.settings = await self.config_service.get_settings_with_overrides()
        await self._init_kb()
        await self._init_memory()
        await self._init_skills()
        scan_and_register()
        self.interop_registry = build_default_registry(self)
        adapters = AdapterRegistry.get_instance()
        publishers = PublisherRegistry.get_instance()
        tools = ToolRegistry.get_instance()
        tools.register_tool(ExecuteCommandTool(Path.cwd()))
        tools.register_tool(ReadArtifactTool())
        self.tools = tools
        default_provider = self._provider_for_default()
        runtime_adapters = (
            {"ai_search": AISearchAdapter(default_provider)} if default_provider is not None else {}
        )
        options = {
            publisher.id: publisher.config
            for publisher in self.settings.publishers
            if publisher.enabled
        }
        if self.settings.alert_targets:
            self.alerts.add_callback(
                PublisherAlertCallback(
                    self.settings.alert_targets.split(","),
                    options,
                    publisher_registry=publishers,
                )
            )
        self.adapter_health_repo = AdapterHealthRepository(
            self.settings.adapter_health_failure_threshold
        )
        health_alerter = AdapterHealthAlerter(
            [
                target.strip()
                for target in self.settings.adapter_health_alert_targets.split(",")
                if target.strip()
            ],
            options,
            publisher_registry=publishers,
        )
        self.ingestion = IngestionService(
            adapters,
            source_data,
            task_logs,
            runtime_adapters=runtime_adapters,
            db=self.db,
            health_repo=self.adapter_health_repo,
            alerter=health_alerter,
        )
        self.publishing = PublishingService(
            publishers,
            {
                "feishu_bot": lambda digest: render_digest_card(
                    digest.title, digest.items, footer=digest.summary
                ),
                "wecom_bot": lambda digest: render_digest_markdown(
                    digest.title, digest.items, footer=digest.summary
                ),
            },
            options,
        )
        executor = AgentExecutor(
            self._provider_for_agent,
            tools,
            PromptService(),
            context_provider=MemoryKnowledgeContextProvider(
                self.memory_service,
                self.kb_service,
            ),
        )
        self.agent_executor = executor
        self.workflow_engine = WorkflowEngine(
            _StoredAgentStepExecutor(entities, executor),
            entities,
            iteration_store=self.iteration_store,
        )
        registry = TaskExecutorRegistry()
        registry.register("daily_digest", self.run_daily_digest_task)
        scheduler_lock = RedisSchedulerLock(
            self.settings.redis_url,
            strict_mode=self.settings.scheduler_lock_strict_mode,
        )
        self.scheduler_lock = scheduler_lock
        self.scheduler = SchedulerService(
            task_logs,
            entities,
            executor_registry=registry,
            lock=scheduler_lock,
            lock_ttl_seconds=self.settings.scheduler_lock_ttl_seconds,
            lock_strict_mode=self.settings.scheduler_lock_strict_mode,
            daily_usage_repo=self.daily_usage,
        )
        self.entities = entities
        self.task_logs = task_logs
        self.source_data = source_data
        await self._bootstrap_default_curation_agent(entities)
        await self._bootstrap_default_overview_agent(entities)
        await self._bootstrap_daily_ai_news_schedule(entities)
        await self.scheduler.start()
        self._initialized = True

    async def reload(self) -> None:
        """Stop runtime services, close the database, then rebuild all composition state."""
        if self.scheduler is not None:
            await self.scheduler.stop()
        if self.db is not None:
            await self.db.close()
        await close_redis()
        self._initialized = False
        self.db = None
        await self.init()

    async def close(self) -> None:
        """Release scheduler and database resources at application shutdown."""
        if self.scheduler is not None:
            await self.scheduler.stop()
        if self.db is not None:
            await self.db.close()
        await close_redis()
        self._initialized = False

    async def _init_kb(self) -> None:
        """Initialize FTS5 knowledge services while preserving optional-feature degradation."""
        if self.db is None:
            raise RuntimeError("knowledge base initialization requires a database")
        vector_enabled = await self.db.migrate_kb()
        embeddings = EmbeddingService() if EmbeddingService.is_available() else None
        vector_store = VectorStore(self.db) if vector_enabled else None
        retriever = Retriever(self.db, vector_store, embeddings)
        self.kb_service = KBService(
            self.db, DocumentProcessor(), embeddings, vector_store, retriever
        )
        self.kb_capabilities = self.kb_service.capabilities

    async def _init_memory(self) -> None:
        """Initialize P17 repositories against the existing memory tables."""
        if self.db is None or self.publish_history is None or self.kb_service is None:
            raise RuntimeError(
                "memory initialization requires database, history, and knowledge services"
            )
        categories = MemoryCategoryRepository(self.db)
        preferences = PreferenceStore(
            categories,
            UserPreferences(
                preferred_tags=[],
                block_sources=[],
                blocked_topics=[],
                push_time=self.settings.memory_default_push_time,
                importance_threshold=self.settings.memory_importance_threshold,
            ),
        )
        self.preference_store = preferences
        self.memory_service = MemoryService(
            MemoryEntryRepository(self.db),
            preferences,
            PreferenceExtractor(self.db, self.publish_history, self._provider_for_default()),
            self.kb_service,
        )
        if self.click_events is None:
            raise RuntimeError("click-event repository initialization failed")
        self.preference_feedback = PreferenceFeedbackService(self.click_events, preferences)

    def _provider_for_default(self) -> AIProvider | None:
        """Create the default curator provider only when a usable credential exists."""
        provider = next(
            (
                item
                for item in self.settings.ai_providers
                if item.id == self.settings.default_curation_provider_id
            ),
            None,
        )
        if provider is None or not provider.api_key:
            return None
        try:
            return create_provider(
                provider,
                model=self.settings.default_curation_model,
                temperature=self.settings.default_curation_temperature,
                proxy=self.settings.http_proxy or None,
            )
        except (NotImplementedError, ProviderError):
            return None

    async def _init_skills(self) -> None:
        """Load bundled and runtime-created skill documents into the process registry."""
        builtin_root = Path(__file__).parent / "resources" / "skills"
        custom_root = Path("data") / "skills"
        self.skill_service = SkillService(
            get_skill_registry(),
            SkillScanner(parse_frontmatter),
            builtin_root,
            custom_root,
        )
        await load_builtin_skills(self.skill_service)

    #
    async def run_daily_digest_task(self, task: ScheduleTask) -> dict[str, object]:
        """Build and run P11 from the persisted schedule task configuration."""
        self._require_initialized()
        config = DailyDigestConfig.from_mapping(task.config)
        raw = await self.entities.get("agents", config.curate_agent_id)  # type: ignore[union-attr]
        if raw is None:
            raise LookupError(f"agent not found: {config.curate_agent_id}")
        definition = AgentDefinition.model_validate(raw)
        pipeline = DailyDigestPipeline(
            self.ingestion,  # type: ignore[arg-type]
            self.source_data,  # type: ignore[arg-type]
            _StoredAgentStepExecutor(self.entities, self.agent_executor),  # type: ignore[arg-type]
            self.publishing,  # type: ignore[arg-type]
            config,
            _ProviderLoopReflector(Reflector(), self._provider_for_agent(definition)),
            self.db,
            self.publish_history,
            self.memory_service,
            self.pushed_content,
            archive_repo=get_daily_digest_archive(),
            preference_feedback=self.preference_feedback,
            iteration_store=self.iteration_store,
            curation_evaluations=self.curation_evaluations,
        )
        return await pipeline.run()

    def _provider_for_agent(self, definition: AgentDefinition) -> AIProvider:
        """Resolve the provider settings requested by one stored agent definition."""
        provider = next(
            (item for item in self.settings.ai_providers if item.id == definition.provider_id), None
        )
        if provider is None:
            raise ProviderError(f"provider not found: {definition.provider_id}")
        return create_provider(
            provider,
            model=definition.model,
            temperature=definition.temperature,
            proxy=self.settings.http_proxy or None,
        )

    async def _bootstrap_default_curation_agent(self, entities: EntityJsonRepository) -> None:
        """Persist the MVP curator declaration once; update it if settings have drifted."""
        raw = await entities.get("agents", DEFAULT_CURATION_AGENT_ID)
        definition = AgentDefinition(
            id=DEFAULT_CURATION_AGENT_ID,
            name="Default Curation Agent",
            description="MVP default curation agent created by bootstrap.",
            system_prompt=DEFAULT_CURATION_AGENT_PROMPT,
            provider_id=self.settings.default_curation_provider_id,
            model=self.settings.default_curation_model,
            temperature=self.settings.default_curation_temperature,
        )
        if raw is None:
            await entities.save(
                "agents", DEFAULT_CURATION_AGENT_ID, definition.model_dump(mode="json")
            )
            return

        existing = AgentDefinition.model_validate(raw)
        if (
            existing.model != definition.model
            or existing.temperature != definition.temperature
            or existing.provider_id != definition.provider_id
            or existing.system_prompt == _LEGACY_DEFAULT_CURATION_AGENT_PROMPT
        ):
            await entities.save(
                "agents", DEFAULT_CURATION_AGENT_ID, definition.model_dump(mode="json")
            )

    async def _bootstrap_default_overview_agent(self, entities: EntityJsonRepository) -> None:
        """Persist the dedicated natural-language overview agent declaration."""
        raw = await entities.get("agents", OVERVIEW_AGENT_ID)
        definition = AgentDefinition(
            id=OVERVIEW_AGENT_ID,
            name="Daily Digest Overview Agent",
            description="Writes the natural-language overview for the daily digest.",
            system_prompt=DEFAULT_OVERVIEW_AGENT_PROMPT,
            provider_id=self.settings.default_curation_provider_id,
            model=self.settings.default_curation_model,
            temperature=self.settings.default_curation_temperature,
        )
        if raw is None:
            await entities.save("agents", OVERVIEW_AGENT_ID, definition.model_dump(mode="json"))
            return

        existing = AgentDefinition.model_validate(raw)
        if (
            existing.model != definition.model
            or existing.temperature != definition.temperature
            or existing.provider_id != definition.provider_id
            or existing.system_prompt != definition.system_prompt
        ):
            await entities.save("agents", OVERVIEW_AGENT_ID, definition.model_dump(mode="json"))

    async def _bootstrap_daily_ai_news_schedule(self, entities: EntityJsonRepository) -> None:
        """Create or update the default multi-source AI-news schedule."""
        raw = await entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)
        targets = self._daily_ai_news_targets()
        if raw is not None:
            existing = ScheduleTask.model_validate(raw)
            existing_targets = existing.config.get("targets", [])
            normalized_targets = (
                [target for target in existing_targets if isinstance(target, str)]
                if isinstance(existing_targets, list)
                else []
            )
            merged_targets = list(dict.fromkeys([*normalized_targets, *targets]))
            updated_config = dict(existing.config)
            if merged_targets != normalized_targets:
                updated_config["targets"] = merged_targets
            if existing.config.get("top_n") in _LEGACY_DAILY_AI_NEWS_TOP_N:
                updated_config["top_n"] = _DEFAULT_DAILY_AI_NEWS_TOP_N
            if "resolve_article_images" not in existing.config:
                updated_config["resolve_article_images"] = True
            if self._uses_legacy_daily_news_rss_urls(existing.config):
                adapter_configs = existing.config.get("adapter_configs")
                if isinstance(adapter_configs, dict):
                    updated_adapter_configs = dict(adapter_configs)
                    rss_config = adapter_configs.get("rss")
                    if isinstance(rss_config, dict):
                        updated_adapter_configs["rss"] = {
                            **rss_config,
                            "rss_urls": self.settings.daily_ai_news_rss_urls,
                        }
                        updated_config["adapter_configs"] = updated_adapter_configs
            if updated_config != existing.config:
                await entities.save(
                    "schedules",
                    existing.id,
                    existing.model_copy(update={"config": updated_config}).model_dump(mode="json"),
                )
            return
        follow_opml_path = self.settings.daily_ai_news_follow_opml_path.strip()
        task = ScheduleTask(
            id=DEFAULT_DAILY_AI_NEWS_TASK_ID,
            name="每日 AI 资讯日报",
            task_type="daily_digest",
            cron=self.settings.daily_ai_news_cron,
            enabled=True,
            config={
                "curate_agent_id": DEFAULT_CURATION_AGENT_ID,
                "adapter_ids": ["rss", "github_trending", "follow_opml", "ai_search"],
                "adapter_configs": {
                    "rss": {"rss_urls": self.settings.daily_ai_news_rss_urls},
                    "github_trending": {"max_items": 20},
                    "follow_opml": {
                        "enabled": bool(follow_opml_path),
                        "opml_path": follow_opml_path,
                        "fetch_articles": True,
                        "max_feeds": 12,
                        "max_items_per_feed": 8,
                        "source_tag": "AI",
                    },
                    "ai_search": {
                        "enabled": self._provider_for_default() is not None,
                        "provider": "perplexity",
                        "query": self.settings.daily_ai_news_search_query,
                        "max_items": 12,
                        "recency_days": 2,
                    },
                },
                "fetch_days": self.settings.default_digest_fetch_days,
                "top_n": self.settings.default_digest_top_n,
                "resolve_article_images": True,
                "targets": targets,
            },
        )
        await entities.save("schedules", task.id, task.model_dump(mode="json"))

    @staticmethod
    def _uses_legacy_daily_news_rss_urls(config: dict[str, object]) -> bool:
        """Detect exactly the historical built-in RSS list before replacing it."""
        adapter_configs = config.get("adapter_configs")
        if not isinstance(adapter_configs, dict):
            return False
        rss_config = adapter_configs.get("rss")
        if not isinstance(rss_config, dict):
            return False
        raw_urls = rss_config.get("rss_urls")
        return raw_urls == _LEGACY_DAILY_AI_NEWS_RSS_URLS

    def _daily_ai_news_targets(self) -> list[str]:
        """Enable Feishu delivery for the default task only when it is configured."""
        return [
            "feishu_bot"
            for publisher in self.settings.publishers
            if publisher.id == "feishu_bot" and publisher.enabled
        ]

    def _require_initialized(self) -> None:
        """Raise an explicit runtime error when context users skipped initialization."""
        if not self._initialized:
            raise RuntimeError("service context is not initialized")


_context: ServiceContext | None = None


def get_context() -> ServiceContext:
    """Return the process-wide lazy ServiceContext used by CLI application startup."""
    global _context
    if _context is None:
        _context = ServiceContext()
    return _context
