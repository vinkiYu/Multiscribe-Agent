"""Tests for the curation LLM harness, report writer, and regression gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from multiscribe_agent.cli import main
from multiscribe_agent.domain.models import AIResponse
from multiscribe_agent.eval.benchmark import RegressionDetected
from multiscribe_agent.eval.curation_benchmark import run_curation, run_curation_benchmark
from multiscribe_agent.eval.curation_dataset import (
    CurationCandidate,
    CurationDataset,
    CurationSample,
)


class FakeProvider:
    """Return a configured JSON selection without making a network request."""

    def __init__(self, selected_ids: set[str]) -> None:
        self.selected_ids = selected_ids
        self.prompts: list[str] = []

    async def generate(self, messages: list[object], **_: object) -> AIResponse:
        self.prompts.append(str(messages[0].content))
        return AIResponse(
            content=json.dumps([{"id": item_id} for item_id in sorted(self.selected_ids)])
        )


def _sample(sample_id: str = "sample") -> CurationSample:
    """Build a small annotated sample for harness tests."""
    return CurationSample(
        id=sample_id,
        candidates=[
            CurationCandidate(
                id="good",
                title="Agent update",
                description="A useful Agent engineering release.",
                url="https://example.test/good",
                source="rss",
            ),
            CurationCandidate(
                id="noise",
                title="Weather update",
                description="A general weather report.",
                url="https://example.test/noise",
                source="rss",
            ),
        ],
        expected_selected_ids=["good"],
        expected_rejected_ids=["noise"],
    )


@pytest.mark.asyncio
async def test_run_curation_extracts_selected_ids() -> None:
    """The harness projects candidates and extracts IDs from the curator JSON."""
    provider = FakeProvider({"good"})

    selected = await run_curation(provider, _sample(), target_count=12)

    assert selected == {"good"}
    assert '"id": "good"' in provider.prompts[0]
    assert '"id": "noise"' in provider.prompts[0]


@pytest.mark.asyncio
async def test_benchmark_detects_regression(tmp_path: Path) -> None:
    """A drop in average F1 beyond the threshold raises RegressionDetected."""
    dataset = CurationDataset(
        name="fixture",
        description="fixture",
        samples=[_sample()],
    )
    baseline = tmp_path / "baseline.json"
    await run_curation_benchmark(
        FakeProvider({"good"}), dataset, tmp_path / "reports", baseline_path=baseline
    )

    with pytest.raises(RegressionDetected):
        await run_curation_benchmark(
            FakeProvider({"noise"}),
            dataset,
            tmp_path / "reports",
            baseline_path=baseline,
            threshold=0.1,
        )
    report = next((tmp_path / "reports").glob("*.md"))
    assert "Precision" in report.read_text(encoding="utf-8")


def test_eval_curation_help_is_available() -> None:
    """The new command is discoverable without initializing a provider."""
    result = CliRunner().invoke(main, ["eval-curation", "--help"])

    assert result.exit_code == 0
    assert "--target-count" in result.output
    assert "--regression-threshold" in result.output
