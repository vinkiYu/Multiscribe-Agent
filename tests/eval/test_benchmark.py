import json
from pathlib import Path

import pytest

from multiscribe_agent.domain.models import AIResponse
from multiscribe_agent.eval.benchmark import RegressionDetected, run_benchmark
from multiscribe_agent.eval.dataset import load_dataset


class FakeProvider:
    def __init__(self, score: int = 8) -> None:
        self.score = score

    async def generate(self, *_args: object, **_kwargs: object) -> AIResponse:
        return AIResponse(
            content=json.dumps(
                {
                    "accuracy": self.score,
                    "conciseness": self.score,
                    "format": self.score,
                    "overall": self.score,
                    "relevance": self.score,
                    "matched": 1,
                    "total": 1,
                    "stability": self.score,
                    "bottleneck": "",
                    "reason": "",
                }
            )
        )


@pytest.mark.asyncio
async def test_benchmark_writes_summary_and_report(tmp_path: Path) -> None:
    dataset = load_dataset(Path("data/eval/datasets/summary_quality.yaml"))
    summary = await run_benchmark(
        FakeProvider(), dataset, [], tmp_path / "reports", tmp_path / "baseline.json"
    )
    assert summary.total == 3
    assert (tmp_path / "baseline.json").is_file()
    report = next((tmp_path / "reports").glob("*.md"))
    assert "| ID | 摘要 |" in report.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_benchmark_detects_regression(tmp_path: Path) -> None:
    dataset = load_dataset(Path("data/eval/datasets/summary_quality.yaml"))
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "dataset_name": dataset.name,
                "total": 3,
                "passed": 3,
                "failed": 0,
                "avg_summary": 9,
                "avg_relevance": 9,
                "avg_stability": 9,
                "overall": 9,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RegressionDetected):
        await run_benchmark(
            FakeProvider(score=6),
            dataset,
            [],
            tmp_path / "reports",
            baseline,
            regression_threshold=0.1,
        )


@pytest.mark.asyncio
async def test_benchmark_without_baseline_is_supported(tmp_path: Path) -> None:
    dataset = load_dataset(Path("data/eval/datasets/summary_quality.yaml"))
    summary = await run_benchmark(FakeProvider(), dataset, [], tmp_path / "reports")
    assert summary.overall == 8
