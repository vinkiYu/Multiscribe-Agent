"""Opt-in real daily-digest verification against configured external services."""

from __future__ import annotations

import pytest

from multiscribe_agent.bootstrap import DEFAULT_CURATION_AGENT_ID, ServiceContext
from multiscribe_agent.cli import _resolve_adapter_ids, _resolve_targets
from multiscribe_agent.config import SystemSettings
from multiscribe_agent.domain.models import ScheduleTask

RSS_URL = "https://feeds.bbci.co.uk/news/rss.xml"


def test_cli_defaults_resolve_p0_5_alias_and_configured_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0.5's configured adapter alias becomes the RSS plugin ID used by P11."""
    monkeypatch.setenv("FEISHU_WEBHOOK", "https://feishu.example.test/hook")
    settings = SystemSettings(_env_file=None)

    assert _resolve_adapter_ids(settings.default_digest_adapter_ids) == ["rss"]
    assert _resolve_targets(None, settings.default_digest_targets, settings) == ["feishu_bot"]


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_real_daily_digest_delivers_to_configured_targets(tmp_path) -> None:
    """Fetch RSS, call the configured LLM, publish, and record a completed task log."""
    settings = SystemSettings(db_path=str(tmp_path / "e2e.sqlite"))
    provider = next(
        (
            item
            for item in settings.ai_providers
            if item.id == settings.default_curation_provider_id
        ),
        None,
    )
    if provider is None or not provider.api_key:
        pytest.skip("configure the default curation provider API key in .env")
    targets = [
        publisher.id
        for publisher in settings.publishers
        if publisher.id in {"feishu_bot", "wecom_bot"} and publisher.enabled
    ]
    if not targets:
        pytest.skip("configure a Feishu or Enterprise WeCom webhook in .env")

    task = ScheduleTask(
        id="e2e-daily-digest",
        name="E2E daily digest",
        task_type="daily_digest",
        cron="0 0 * * *",
        config={
            "curate_agent_id": DEFAULT_CURATION_AGENT_ID,
            "adapter_ids": ["rss"],
            "adapter_configs": {"rss": {"rss_url": RSS_URL}},
            "targets": targets,
            "top_n": 5,
        },
    )
    context = ServiceContext(settings)
    await context.init()
    result: dict[str, object] | None = None

    async def execute(_: ScheduleTask) -> dict[str, object]:
        nonlocal result
        result = await context.run_daily_digest_task(task)
        return result

    try:
        assert context.scheduler is not None
        assert context.db is not None
        await context.scheduler.execute_task(task, execute)
        if result is None:
            failed_task_log = await context.db.fetchone(
                "SELECT message FROM task_logs WHERE task_id = ? ORDER BY id DESC LIMIT 1",
                (task.id,),
            )
            assert failed_task_log is not None
            pytest.fail(f"daily digest task failed: {failed_task_log['message']}")
        outcomes = result["targets"]
        assert isinstance(outcomes, dict)
        assert any(
            isinstance(outcome, dict) and outcome.get("status") == "success"
            for outcome in outcomes.values()
        )
        task_log = await context.db.fetchone(
            "SELECT status FROM task_logs WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task.id,),
        )
        assert task_log is not None
        assert task_log["status"] == "success"
    finally:
        await context.close()
