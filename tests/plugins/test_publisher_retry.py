"""Regression tests for the shared publisher retry boundary."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from multiscribe_agent.core.errors import PublisherError
from multiscribe_agent.plugins.base import BasePublisher
from multiscribe_agent.plugins.builtin.publishers.dingtalk import DingTalkPublisher
from multiscribe_agent.plugins.builtin.publishers.feishu import FeishuPublisher
from multiscribe_agent.plugins.builtin.publishers.wechat import WeChatPublisher
from multiscribe_agent.plugins.builtin.publishers.wecom import WeComPublisher
from multiscribe_agent.plugins.builtin.publishers.xiaohongshu import XiaohongshuPublisher


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "publisher_factory",
    [
        FeishuPublisher,
        WeComPublisher,
        DingTalkPublisher,
        lambda: WeChatPublisher("app-id", "app-secret"),
        XiaohongshuPublisher,
    ],
)
async def test_publishers_share_bounded_retry_and_final_error(
    publisher_factory: Callable[[], BasePublisher],
) -> None:
    """All built-ins use four bounded attempts and expose PublisherError."""
    publisher = publisher_factory()
    attempts = 0

    async def send() -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        raise PublisherError("temporary response error")

    with pytest.raises(PublisherError, match="failed after retries"):
        await publisher._send_with_retry(
            send,
            publisher_name=type(publisher).__name__,
            retry_delays=(0.0, 0.0, 0.0),
        )

    assert attempts == 4


@pytest.mark.asyncio
async def test_shared_retry_returns_first_success_after_transient_failures() -> None:
    """A later success is returned without an extra request."""
    publisher = FeishuPublisher()
    attempts = 0

    async def send() -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PublisherError("temporary response error")
        return {"status": "success"}

    assert await publisher._send_with_retry(
        send,
        publisher_name="Feishu",
        retry_delays=(0.0, 0.0, 0.0),
    ) == {"status": "success"}
    assert attempts == 3
