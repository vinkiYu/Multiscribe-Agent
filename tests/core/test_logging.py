"""Tests for persistent structured runtime logging."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler

from multiscribe_agent.core.logging import (
    FILE_HANDLER_NAME,
    LOG_FILE_BACKUP_COUNT,
    LOG_FILE_MAX_BYTES,
    configure_logging,
    get_logger,
)


def test_configure_logging_writes_redacted_json_to_rotating_file(tmp_path) -> None:
    """Application events persist as redacted JSON through one managed handler."""
    log_path = tmp_path / "runtime" / "multiscribe-agent.log"
    try:
        configure_logging("INFO", json_output=True, log_file=log_path)

        get_logger().info("runtime_log_test", api_key="super-secret-value")
        handler = _managed_handler()
        handler.flush()

        payload = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert payload["event"] == "runtime_log_test"
        assert payload["api_key"] != "super-secret-value"
        assert handler.maxBytes == LOG_FILE_MAX_BYTES
        assert handler.backupCount == LOG_FILE_BACKUP_COUNT
    finally:
        configure_logging("INFO", log_file=None)


def test_reconfigure_logging_replaces_file_handler(tmp_path) -> None:
    """Application reloads retain exactly one managed file handler."""
    try:
        configure_logging("INFO", log_file=tmp_path / "first.log")
        configure_logging("WARNING", log_file=tmp_path / "second.log")

        handlers = [
            handler
            for handler in logging.getLogger().handlers
            if handler.get_name() == FILE_HANDLER_NAME
        ]
        assert len(handlers) == 1
        assert handlers[0].level == logging.WARNING
    finally:
        configure_logging("INFO", log_file=None)


def _managed_handler() -> RotatingFileHandler:
    for handler in logging.getLogger().handlers:
        if handler.get_name() == FILE_HANDLER_NAME:
            assert isinstance(handler, RotatingFileHandler)
            return handler
    raise AssertionError("managed runtime file handler was not configured")
