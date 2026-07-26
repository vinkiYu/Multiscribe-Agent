"""Tests for the MVP dotenv-to-runtime configuration bridge."""

from __future__ import annotations

import pytest

from multiscribe_agent.bootstrap import (
    DEFAULT_CURATION_AGENT_ID,
    DEFAULT_DAILY_AI_NEWS_TASK_ID,
    ServiceContext,
)
from multiscribe_agent.config import ProviderConfig, SystemSettings


def _clear_mvp_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests exercise only the environment values they explicitly provide."""
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "FEISHU_WEBHOOK",
        "FEISHU_SECRET",
        "WECOM_WEBHOOK",
        "DEFAULT_CURATION_PROVIDER_ID",
        "DEFAULT_CURATION_MODEL",
        "DEFAULT_CURATION_TEMPERATURE",
        "DEFAULT_DIGEST_TARGETS",
        "DEFAULT_DIGEST_TOP_N",
        "DEFAULT_DIGEST_FETCH_DAYS",
        "DEFAULT_DIGEST_ADAPTER_IDS",
        "DAILY_AI_NEWS_CRON",
        "DAILY_AI_NEWS_RSS_URLS",
        "DAILY_AI_NEWS_FOLLOW_OPML_PATH",
        "DAILY_AI_NEWS_SEARCH_QUERY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_openai_key_binds_to_default_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """A flat dotenv key reaches the selected structured provider configuration."""
    _clear_mvp_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = SystemSettings(_env_file=None)
    provider = next(item for item in settings.ai_providers if item.id == "default-openai")

    assert provider.api_key == "sk-test"


def test_webhooks_enable_and_configure_mvp_publishers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured delivery endpoints become enabled publisher options without logging secrets."""
    _clear_mvp_environment(monkeypatch)
    monkeypatch.setenv("FEISHU_WEBHOOK", "https://feishu.example.test/hook")
    monkeypatch.setenv("FEISHU_SECRET", "test-secret")
    monkeypatch.setenv("WECOM_WEBHOOK", "https://wecom.example.test/hook")

    settings = SystemSettings(_env_file=None)
    publishers = {publisher.id: publisher for publisher in settings.publishers}

    assert publishers["feishu_bot"].enabled is True
    assert publishers["feishu_bot"].config == {
        "webhook": "https://feishu.example.test/hook",
        "secret": "test-secret",
    }
    assert publishers["wecom_bot"].enabled is True
    assert publishers["wecom_bot"].config == {"webhook": "https://wecom.example.test/hook"}


def test_empty_environment_key_keeps_explicit_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty dotenv value cannot erase a configured provider credential."""
    _clear_mvp_environment(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    providers = [
        ProviderConfig(
            id="default-openai",
            name="OpenAI",
            type="openai",
            api_key="configured-key",
            models=["gpt-4o-mini"],
        )
    ]

    settings = SystemSettings(_env_file=None, ai_providers=providers)

    assert settings.ai_providers[0].api_key == "configured-key"


def test_default_digest_settings_have_mvp_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default daily-digest choices are usable without custom configuration."""
    _clear_mvp_environment(monkeypatch)

    settings = SystemSettings(_env_file=None)

    assert settings.default_curation_provider_id == "default-openai"
    assert settings.default_curation_model == "gpt-4o-mini"
    assert settings.default_curation_temperature == 0.3
    assert settings.default_digest_targets == ["feishu_bot", "wecom_bot"]
    assert settings.default_digest_top_n == 12
    assert settings.default_digest_fetch_days == 2
    assert settings.default_digest_adapter_ids == ["rss-adapter"]
    assert settings.daily_ai_news_cron == "0 9 * * *"
    assert settings.daily_ai_news_rss_urls == [
        "https://huggingface.co/blog/feed.xml",
        "https://openai.com/news/rss.xml",
        "https://blog.google/technology/ai/rss/",
        "https://aws.amazon.com/blogs/machine-learning/feed/",
        "https://export.arxiv.org/rss/cs.AI",
        "https://export.arxiv.org/rss/cs.CL",
        "https://simonwillison.net/atom/everything/",
        "https://github.blog/feed/",
    ]


def test_daily_ai_news_rss_urls_accept_csv_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The multi-feed task accepts a practical dotenv-compatible list format."""
    _clear_mvp_environment(monkeypatch)
    monkeypatch.setenv("DAILY_AI_NEWS_RSS_URLS", "https://one.test/feed, https://two.test/feed")

    settings = SystemSettings(_env_file=None)

    assert settings.daily_ai_news_rss_urls == ["https://one.test/feed", "https://two.test/feed"]


@pytest.mark.asyncio
async def test_bootstrap_persists_default_curation_agent(tmp_path) -> None:
    """A new service database receives the default curator exactly once at startup."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "mvp.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        assert context.entities is not None
        stored = await context.entities.get("agents", DEFAULT_CURATION_AGENT_ID)
        assert stored is not None
        assert stored["provider_id"] == "default-openai"
        assert stored["model"] == "gpt-4o-mini"
        assert stored["temperature"] == 0.3
    finally:
        await context.close()


@pytest.mark.asyncio
async def test_bootstrap_persists_ai_news_schedule_once_without_external_targets(tmp_path) -> None:
    """Fresh installations receive one archive-only, multi-source daily AI-news task."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "daily-news.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        assert context.entities is not None
        stored = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)
        assert stored is not None
        assert stored["cron"] == "0 9 * * *"
        assert stored["config"]["targets"] == []
        assert stored["config"]["adapter_ids"] == [
            "rss",
            "github_trending",
            "follow_opml",
            "ai_search",
        ]
        adapter_configs = stored["config"]["adapter_configs"]
        assert adapter_configs["follow_opml"]["enabled"] is False
        assert adapter_configs["ai_search"]["enabled"] is False
        before = stored
        await context._bootstrap_daily_ai_news_schedule(context.entities)
        after = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)
        assert after == before
    finally:
        await context.close()


@pytest.mark.asyncio
async def test_bootstrap_replaces_only_the_legacy_default_rss_list(tmp_path) -> None:
    """Existing built-in schedules receive new defaults without overwriting custom lists."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "rss-upgrade.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        assert context.entities is not None
        stored = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)
        assert stored is not None
        adapter_configs = stored["config"]["adapter_configs"]
        adapter_configs["rss"]["rss_urls"] = [
            "https://huggingface.co/blog/feed.xml",
            "https://openai.com/news/rss.xml",
            "https://www.deeplearning.ai/the-batch/rss/",
        ]
        await context.entities.save("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID, stored)

        await context._bootstrap_daily_ai_news_schedule(context.entities)
        upgraded = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)

        assert upgraded is not None
        assert upgraded["config"]["adapter_configs"]["rss"]["rss_urls"] == (
            settings.daily_ai_news_rss_urls
        )
    finally:
        await context.close()


@pytest.mark.asyncio
async def test_bootstrap_upgrades_only_the_legacy_daily_news_top_n(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The historical built-in limit upgrades without changing user choices."""
    _clear_mvp_environment(monkeypatch)
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "top-n-upgrade.sqlite"))
    context = ServiceContext(settings)
    await context.init()
    try:
        assert context.entities is not None
        stored = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)
        assert stored is not None
        stored["config"]["top_n"] = 5
        await context.entities.save("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID, stored)

        await context._bootstrap_daily_ai_news_schedule(context.entities)
        upgraded = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)

        assert upgraded is not None
        assert upgraded["config"]["top_n"] == 12

        upgraded["config"]["top_n"] = 10
        await context.entities.save("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID, upgraded)
        await context._bootstrap_daily_ai_news_schedule(context.entities)
        upgraded_again = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)

        assert upgraded_again is not None
        assert upgraded_again["config"]["top_n"] == 12

        upgraded_again["config"]["top_n"] = 7
        await context.entities.save("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID, upgraded_again)
        await context._bootstrap_daily_ai_news_schedule(context.entities)
        preserved = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)

        assert preserved is not None
        assert preserved["config"]["top_n"] == 7
    finally:
        await context.close()


@pytest.mark.asyncio
async def test_bootstrap_adds_feishu_to_existing_default_ai_news_schedule(tmp_path) -> None:
    """A configured Feishu webhook upgrades the built-in task without dropping other targets."""
    settings = SystemSettings(_env_file=None, db_path=str(tmp_path / "feishu-news.sqlite"))
    feishu = next(publisher for publisher in settings.publishers if publisher.id == "feishu_bot")
    feishu.enabled = True
    feishu.config = {"webhook": "https://feishu.example.test/hook"}
    context = ServiceContext(settings)
    await context.init()
    try:
        assert context.entities is not None
        stored = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)
        assert stored is not None
        assert stored["config"]["targets"] == ["feishu_bot"]

        stored["config"]["targets"] = ["wecom_bot"]
        await context.entities.save("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID, stored)
        await context._bootstrap_daily_ai_news_schedule(context.entities)
        updated = await context.entities.get("schedules", DEFAULT_DAILY_AI_NEWS_TASK_ID)

        assert updated is not None
        assert updated["config"]["targets"] == ["wecom_bot", "feishu_bot"]
    finally:
        await context.close()
