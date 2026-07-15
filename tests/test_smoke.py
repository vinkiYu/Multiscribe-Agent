"""Smoke tests for package and CLI availability."""

import importlib

from click.testing import CliRunner

import multiscribe_agent
from multiscribe_agent.cli import main


def test_import() -> None:
    """The package can be imported."""
    importlib.import_module("multiscribe_agent")


def test_version() -> None:
    """The package exposes its current version."""
    assert multiscribe_agent.__version__ == "0.1.0"


def test_cli_version() -> None:
    """The CLI reports the package version and exits successfully."""
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "multiscribe-agent 0.1.0" in result.output
