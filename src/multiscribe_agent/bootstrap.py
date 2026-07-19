"""Application composition root for services, registries, and scheduled callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from multiscribe_agent.agents.executor import AgentExecutor
from multiscribe_agent.agents.pipelines.daily_digest import DailyDigestConfig, DailyDigestPipeline
from multiscribe_agent.agents.prompt_service import PromptService
from multiscribe_agent.agents.reflector import Reflector
from multiscribe_agent.agents.workflow.engine import WorkflowEngine
from multiscribe_agent.agents.workflow.protocols import LoopAssessment
from multiscribe_agent.config import ConfigService, SystemSettings, get_settings
from multiscribe_agent.core.errors import ProviderError
from multiscribe_agent.core.publish_history import PublishHistory, get_publish_history
from multiscribe_agent.domain.models import AgentDefinition, ScheduleTask
from multiscribe_agent.infra.db import Database, init_db
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
from multiscribe_agent.observability.meter import MetricsRegistry, set_metrics_registry
from multiscribe_agent.observability.optional import ObservabilityCapabilities, detect
from multiscribe_agent.observability.tracer import setup_tracer
from multiscribe_agent.plugins.discovery import scan_and_register
from multiscribe_agent.plugins.registry import AdapterRegistry, PublisherRegistry, ToolRegistry
from multiscribe_agent.renderers.feishu_card import render_digest_card
from multiscribe_agent.renderers.wecom_markdown import render_digest_markdown
from multiscribe_agent.services.ingestion import IngestionService
from multiscribe_agent.services.interop import InteropService
from multiscribe_agent.services.interop_rate_limit import SlidingWindowLimiter
from multiscribe_agent.services.interop_registry import (
    ToolRegistry as InteropToolRegistry,
)
from multiscribe_agent.services.interop_registry import (
    build_default_registry,
)
from multiscribe_agent.services.publishing import PublishingService
from multiscribe_agent.services.scheduler import SchedulerService, TaskExecutorRegistry
from multiscribe_agent.skills.builtin_loader import load_builtin_skills
from multiscribe_agent.skills.frontmatter_parser import parse_frontmatter
from multiscribe_agent.skills.registry import get_skill_registry
from multiscribe_agent.skills.scanner import SkillScanner
from multiscribe_agent.skills.service import SkillService

DEFAULT_CURATION_AGENT_ID = "default-curation-agent"
DEFAULT_CURATION_AGENT_PROMPT = (
    "You are a news curation assistant. Select the five most useful items from the input "
    "and return a JSON array whose entries contain id, title, summary, and score from 0 to 10."
)


@dataclass(slots=True)
class _ProviderLoopReflector:
    """Adapt P4's provider-aware reflector to P10's narrow loop protocol."""

    reflector: Reflector
    provider: AIProvider

    async def assess(self, task: str, output: str) -> LoopAssessment:
        """Assess loop output with the provider selected for the curation agent."""
        reflection = await self.reflector.assess(task, output, self.provider)
        return _MutableLoopAssessment(
            reflection.should_retry, reflection.feedback, reflection.score
        )


@dataclass(slots=True)
class _MutableLoopAssessment:
    """Writable protocol view of P4's frozen Reflection result."""

    should_retry: bool
    feedback: str
    score: float


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
        return (await self._executor.run(AgentDefinition.model_validate(raw), user_input)).content


class ServiceContext:
    """Lazily initialize and reload the concrete service graph for API and CLI use."""

    def __init__(self, settings: SystemSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db: Database | None = None
        self.entities: EntityJsonRepository | None = None
        self.task_logs: TaskLogRepository | None = None
        self.source_data: SourceDataRepository | None = None
        self.ingestion: IngestionService | None = None
        self.publishing: PublishingService | None = None
        self.agent_executor: AgentExecutor | None = None
        self.workflow_engine: WorkflowEngine | None = None
        self.scheduler: SchedulerService | None = None
        self.config_service: ConfigService | None = None
        self.publish_history: PublishHistory | None = None
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
        self._initialized = False

    async def init(self) -> None:
        """Initialize database, plugins, services, executor adapters, and scheduler."""
        if self._initialized:
            return
        self.db = await init_db(self.settings.db_path)
        self.observability_capabilities = detect()
        self.metrics = MetricsRegistry.create(self.observability_capabilities)
        set_metrics_registry(self.metrics)
        self.tracer = setup_tracer()
        self.interop_service = InteropService(self.db)
        self.interop_limiter = SlidingWindowLimiter(window_seconds=60)
        self.publish_history = get_publish_history()
        entities = EntityJsonRepository(self.db)
        task_logs = TaskLogRepository(self.db)
        source_data = SourceDataRepository(self.db)
        kv = KvRepository(self.db)
        self.config_service = ConfigService(kv)
        await self._init_kb()
        await self._init_memory()
        await self._init_skills()
        scan_and_register()
        self.interop_registry = build_default_registry(self)
        adapters = AdapterRegistry.get_instance()
        publishers = PublisherRegistry.get_instance()
        tools = ToolRegistry.get_instance()
        self.ingestion = IngestionService(adapters, source_data, task_logs)
        options = {
            publisher.id: publisher.config
            for publisher in self.settings.publishers
            if publisher.enabled
        }
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
        executor = AgentExecutor(self._provider_for_agent, tools, PromptService())
        self.agent_executor = executor
        self.workflow_engine = WorkflowEngine(
            _StoredAgentStepExecutor(entities, executor), entities
        )
        registry = TaskExecutorRegistry()
        registry.register("daily_digest", self.run_daily_digest_task)
        self.scheduler = SchedulerService(task_logs, entities, executor_registry=registry)
        self.entities = entities
        self.task_logs = task_logs
        self.source_data = source_data
        await self._bootstrap_default_curation_agent(entities)
        await self.scheduler.start()
        self._initialized = True

    async def reload(self) -> None:
        """Stop runtime services, close the database, then rebuild all composition state."""
        if self.scheduler is not None:
            await self.scheduler.stop()
        if self.db is not None:
            await self.db.close()
        self._initialized = False
        self.db = None
        await self.init()

    async def close(self) -> None:
        """Release scheduler and database resources at application shutdown."""
        if self.scheduler is not None:
            await self.scheduler.stop()
        if self.db is not None:
            await self.db.close()
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
                push_time=self.settings.memory_default_push_time,
                importance_threshold=self.settings.memory_importance_threshold,
            ),
        )
        self.memory_service = MemoryService(
            MemoryEntryRepository(self.db),
            preferences,
            PreferenceExtractor(self.db, self.publish_history, self._provider_for_default()),
            self.kb_service,
        )

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
        ):
            await entities.save(
                "agents", DEFAULT_CURATION_AGENT_ID, definition.model_dump(mode="json")
            )

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
