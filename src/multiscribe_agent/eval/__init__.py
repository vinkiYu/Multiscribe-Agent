"""Public API for the LLM-as-Judge evaluation framework."""

from multiscribe_agent.eval.benchmark import BenchmarkSummary, RegressionDetected, run_benchmark
from multiscribe_agent.eval.dataset import Dataset, DatasetSample, load_dataset
from multiscribe_agent.eval.evaluator import (
    EvaluationResult,
    JudgeError,
    RelevanceScores,
    StabilityScores,
    SummaryScores,
    evaluate_sample,
)

__all__ = [
    "BenchmarkSummary",
    "Dataset",
    "DatasetSample",
    "EvaluationResult",
    "JudgeError",
    "RegressionDetected",
    "RelevanceScores",
    "StabilityScores",
    "SummaryScores",
    "evaluate_sample",
    "load_dataset",
    "run_benchmark",
]
