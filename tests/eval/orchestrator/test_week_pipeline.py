"""Integration tests for the P64.3 six-step WeekPipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from multiscribe_agent.domain.models import AIMessage, AIResponse
from multiscribe_agent.eval.orchestrator.states import PipelineStep, StepStatus
from multiscribe_agent.eval.orchestrator.week_pipeline import WeekPipeline
from multiscribe_agent.llm.provider import AIProvider


class SelectingProvider:
    async def generate(self, messages: list[AIMessage], **_: object) -> AIResponse:
        del messages
        return AIResponse(content='[{"id":"cr-001-a1"}]')


def _fixture() -> dict[str, object]:
    return {
        "id": "cr-001",
        "candidates": [
            {
                "id": "cr-001-a1",
                "title": "Model release",
                "description": "A substantive model release.",
                "url": "https://example.test/a1",
                "source": "rss",
            }
        ],
        "expected_selected_ids": ["cr-001-a1"],
        "expected_rejected_ids": [],
        "selection_rationale": "test",
    }


def _write_inputs(tmp_path: Path) -> dict[str, Path]:
    fixtures = tmp_path / "fixtures"
    reports = tmp_path / "reports"
    datasets = tmp_path / "datasets"
    fixtures.mkdir()
    reports.mkdir()
    datasets.mkdir()
    (fixtures / "cr_001.json").write_text(json.dumps(_fixture()), encoding="utf-8")
    (datasets / "dataset.yaml").write_text(
        """name: fixture
description: fixture
samples:
  - id: cr-001
    input_path: ../fixtures/cr_001.json
""",
        encoding="utf-8",
    )
    (reports / "curation-recall_20260101-000000.md").write_text(
        """# report

| ID | Precision | Recall | F1 | 状态 | 选择 |
|---|---:|---:|---:|---|---|
| cr-001 | 0.500 | 1.000 | 0.667 | 失败 | sel=cr-001-a1,cr-001-a2;exp=cr-001-a1 |
""",
        encoding="utf-8",
    )
    return {
        "fixtures": fixtures,
        "reports": reports,
        "dataset": datasets / "dataset.yaml",
        "baselines": tmp_path / "baselines",
        "baseline": tmp_path / "baselines" / "curation_recall.json",
        "bad_cases": tmp_path / "bad_cases",
        "ledger": tmp_path / "ledgers" / "rejected.jsonl",
        "traces": tmp_path / "traces",
        "disputes": tmp_path / "disputes",
    }


def _pipeline(paths: dict[str, Path], provider: AIProvider | None) -> WeekPipeline:
    return WeekPipeline(
        provider=provider,
        model="fake",
        dataset_path=paths["dataset"],
        fixtures_dir=paths["fixtures"],
        reports_dir=paths["reports"],
        baselines_dir=paths["baselines"],
        baseline_path=paths["baseline"],
        bad_cases_dir=paths["bad_cases"],
        ledger_path=paths["ledger"],
        traces_dir=paths["traces"],
        disputes_dir=paths["disputes"],
    )


@pytest.mark.asyncio
async def test_dry_run_executes_six_steps_without_writing(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    pipeline = _pipeline(paths, provider=None)

    report = await pipeline.run(dry_run=True)

    assert report.dry_run
    assert report.steps[PipelineStep.COLLECT].status == StepStatus.SUCCEEDED
    assert report.steps[PipelineStep.CLEAN].status == StepStatus.SUCCEEDED
    assert report.steps[PipelineStep.BENCH].status == StepStatus.SUCCEEDED
    assert report.steps[PipelineStep.GATE].status == StepStatus.SKIPPED
    assert report.steps[PipelineStep.ANALYZE].status == StepStatus.SUCCEEDED
    assert report.steps[PipelineStep.FEEDBACK].status == StepStatus.SUCCEEDED
    assert not paths["bad_cases"].exists()
    assert not paths["baselines"].exists()
    assert not paths["ledger"].exists()
    assert not paths["traces"].exists()
    assert not paths["disputes"].exists()
    assert len(list(paths["reports"].glob("week-pipeline_*.md"))) == 0


@pytest.mark.asyncio
async def test_real_run_writes_pipeline_report_and_promotes_accepted_baseline(
    tmp_path: Path,
) -> None:
    paths = _write_inputs(tmp_path)
    pipeline = _pipeline(paths, provider=cast("AIProvider", SelectingProvider()))

    report = await pipeline.run(dry_run=False)

    assert report.steps[PipelineStep.BENCH].status == StepStatus.SUCCEEDED
    assert report.steps[PipelineStep.GATE].status == StepStatus.SUCCEEDED
    assert paths["baseline"].exists()
    assert paths["bad_cases"].exists()
    assert paths["traces"].exists()
    assert paths["disputes"].exists()
    assert len(list(paths["reports"].glob("week-pipeline_*.md"))) == 1


@pytest.mark.asyncio
async def test_gate_rejection_continues_analysis_and_records_failed_gate(tmp_path: Path) -> None:
    paths = _write_inputs(tmp_path)
    base_dir = paths["baselines"]
    base_dir.mkdir()
    paths["baseline"].write_text(
        json.dumps(
            {
                "avg_f1": 1.0,
                "avg_precision": 1.0,
                "avg_recall": 1.0,
                "step_success_rate": 1.0,
                "avg_tokens": 0,
                "p95_latency_ms": 0.0,
            }
        ),
        encoding="utf-8",
    )

    class RejectingProvider:
        async def generate(self, messages: list[AIMessage], **_: object) -> AIResponse:
            del messages
            return AIResponse(content="[]")

    report = await _pipeline(paths, cast("AIProvider", RejectingProvider())).run(dry_run=False)

    assert report.steps[PipelineStep.BENCH].status == StepStatus.SUCCEEDED
    assert report.steps[PipelineStep.GATE].status == StepStatus.FAILED
    assert report.steps[PipelineStep.ANALYZE].status == StepStatus.SUCCEEDED
    assert paths["ledger"].exists()
