# 执行包：P24 — Loop Engineering 深化

> **阶段**：阶段四（与 P22 / P23 同期开发）
> **目标**：扩展 Loop 节点为多轮自评迭代 + 退出条件 + 与 P21 评估框架联动。
> **依赖**：P10（DAG workflow 已存在 loop_node）、P21（评估驱动触发精炼工作流）。
> **并行说明**：与 P22、P23 独立可开发；Skill 沉淀可独立。

---

## 一、目标与验收口径

**核心目标**：
- `execute_loop_step` 支持**多轮**自评迭代；默认 3 轮，可配置。
- **退出条件**：`score > 8` 或 `rounds >= max` 或 `score_diff < 0.5`。
- **评估驱动**：当 P21 评估分数 < 阈值时，自动触发精炼工作流。
- **Skill 沉淀**：`loop-engineering-patterns.md` 文档化最佳迭代策略。

**验收口径**：
- 多轮 Loop 测试：mock reflector 返回 6 → 7 → 8.5，第三轮退出。
- 评估驱动联动：feed 评估报告 + 触发 digest-retry workflow。
- Skill 文件可通过 `skill_registry.scan()` 发现并加载。

---

## 二、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | `LoopSpec` dataclass：`max_rounds / score_threshold / convergence_delta` 可配 | `workflow/loop_node.py` |
| 2 | 多轮退出：score > 阈值 → 退出；`|score_diff| < delta` → 退出；rounds >= max → 退出 | 单测 |
| 3 | 历史记录含每轮 score / feedback / delta；可在历史回放中识别「卡住」轮次 | 单测 |
| 4 | 评估驱动：提供 `feedback_loop.trigger_refinement(score, dataset)` 入口 | 单测 |
| 5 | `data/skills/loop-engineering-patterns.md` 文件存在；能被 scanner 发现 | 手动 + 单测 |
| 6 | 全量 pytest + ruff + mypy 通过 | `pytest -q` |

> **验收序列验证**：默认 `score_threshold=8.0`、`convergence_delta=0.5`、3 轮；mock reflector 返回 `6 → 7 → 8.5`：
> - 轮 1：score=6，未达阈值，无前值，不退；
> - 轮 2：|7−6|=1.0 ≥ 0.5，未饱和，未达阈值，不退；
> - 轮 3：8.5 > 8.0 阈值命中 `threshold` 退出。✓
>
> **修订记录**：
> - **rev1**（2026-07-19）：`score_diff = abs(score - prev_score)` 而非 `prev - score`，避免上升序列误触发收敛；同时 `_normalise_score` 改为透传原值，由 reflector 保证 0-10 范围。

---

## 三、可改范围（白名单）

| 文件路径 | 操作 |
|---|---|
| `src/multiscribe_agent/agents/workflow/loop_node.py` | **修改**（多轮 + 退出条件） |
| `src/multiscribe_agent/agents/workflow/protocols.py` | **修改**（`LoopReflector.assess` 新增 `score` 字段返回） |
| `src/multiscribe_agent/agents/reflector.py` | **修改**（`Reflection` 已有 score 字段，确认输出 0-10 而非 0-1） |
| `src/multiscribe_agent/eval/feedback_loop.py` | **新增**（评估→精炼联动） |
| `src/multiscribe_agent/agents/workflow/__init__.py` | **修改**（导出 LoopSpec） |
| `data/skills/loop-engineering-patterns.md` | **新增**（SKILL.md frontmatter + Markdown body） |
| `tests/agents/test_reflector.py` | **修改**（score 范围调整 0-10） |
| `tests/agents/test_loop_node_multi_round.py` | **新增** |
| `tests/agents/test_loop_exit_conditions.py` | **新增** |
| `tests/eval/test_feedback_loop.py` | **新增** |
| `tests/skills/test_loop_skill_discovery.py` | **新增** |

---

## 四、禁止改动（黑名单）

- `src/multiscribe_agent/agents/executor.py`（执行路径不动，仅 Loop 节点内部升级）
- `src/multiscribe_agent/api/routes/workflows.py`（HTTP 端点签名不变；仅行为变化）
- `frontend/`、`docs/`、`codex/`（除本任务包外的所有文档）

---

## 五、详细任务

### T1：workflow/loop_node.py 多轮 + LoopSpec

```python
# src/multiscribe_agent/agents/workflow/loop_node.py  完整替换

"""Bounded workflow loop execution with multi-round self-evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from multiscribe_agent.agents.workflow.protocols import AgentStepExecutor, LoopReflector
from multiscribe_agent.core.errors import WorkflowError
from multiscribe_agent.domain.models import WorkflowStep


@dataclass(frozen=True, slots=True)
class LoopSpec:
    """Configuration for a multi-round self-evaluating loop step."""

    max_rounds: int = 3
    score_threshold: float = 8.0  # score > threshold exits early
    convergence_delta: float = 0.5  # score_diff < delta exits early
    min_score: float = 0.0
    max_score: float = 10.0


@dataclass(slots=True)
class LoopIteration:
    """One iteration of the loop, with score and feedback."""

    round: int
    output: str
    score: float | None
    feedback: str | None
    converged: bool
    reason: str  # "threshold" / "convergence" / "max_rounds" / "stuck"


@dataclass(frozen=True, slots=True)
class LoopResult:
    """Final loop outcome plus the full iteration history."""

    output: str
    history: list[LoopIteration]
    converged: bool
    exit_reason: str
    final_score: float | None


def _coerce_loop_spec(step: WorkflowStep) -> LoopSpec:
    """Read optional override fields from the workflow step or use defaults."""
    overrides = step.loop_config or {}
    return LoopSpec(
        max_rounds=int(overrides.get("max_rounds", step.max_iterations or 3)),
        score_threshold=float(overrides.get("score_threshold", 8.0)),
        convergence_delta=float(overrides.get("convergence_delta", 0.5)),
    )


async def execute_loop_step(
    step: WorkflowStep,
    step_input: str,
    executor: AgentStepExecutor,
    reflector: LoopReflector | None,
    *,
    trace_id: str,
) -> tuple[str, list[dict[str, object]]]:
    """Execute a multi-round self-evaluating agent step."""
    del trace_id
    if step.agent_id is None:
        raise WorkflowError("loop step requires agent_id")
    spec = _coerce_loop_spec(step)
    task = step_input
    current_input = step_input
    iterations: list[LoopIteration] = []
    output = ""
    for round_number in range(1, spec.max_rounds + 1):
        output = await executor.execute(step.agent_id, current_input)
        converged, score, feedback = await _evaluate(
            step.exit_condition, task, output, reflector, spec
        )
        prev_score = iterations[-1].score if iterations else None
        score_diff = (
            abs(prev_score - score) if (prev_score is not None and score is not None) else None
        )
        reason = _classify_exit(spec, score, score_diff, round_number, converged)
        iterations.append(
            LoopIteration(
                round=round_number,
                output=output,
                score=score,
                feedback=feedback,
                converged=converged,
                reason=reason,
            )
        )
        if converged:
            break
        if feedback is not None:
            current_input = f"{task}\n\nFeedback from previous attempt:\n{feedback}"

    history = [
        {
            "iteration": it.round,
            "output": it.output,
            "score": it.score,
            "feedback": it.feedback,
            "converged": it.converged,
            "reason": it.reason,
        }
        for it in iterations
    ]
    return output, history


async def _evaluate(
    exit_condition: str | None,
    task: str,
    output: str,
    reflector: LoopReflector | None,
    spec: LoopSpec,
) -> tuple[bool, float | None, str | None]:
    """Return (converged, score, feedback) for one iteration."""
    if exit_condition == "llm" or (exit_condition is None and reflector is not None):
        if reflector is None:
            raise WorkflowError("loop exit_condition 'llm' requires a reflector")
        assessment = await reflector.assess(task, output)
        score = _normalise_score(assessment.score, spec)
        return score > spec.score_threshold, score, assessment.feedback
    if exit_condition is None:
        return "DONE" in output, None, None
    match = re.fullmatch(r"output contains ['\"](.+)['\"]", exit_condition)
    if match is None:
        raise WorkflowError(f"unsupported loop exit_condition: {exit_condition}")
    return match.group(1) in output, None, None


def _normalise_score(raw: float, _spec: LoopSpec) -> float:
    """Pass through the score unchanged; caller guarantees 0-10 range."""
    return raw


def _classify_exit(
    spec: LoopSpec,
    score: float | None,
    score_diff: float | None,
    round_number: int,
    converged: bool,
) -> str:
    """Describe why an iteration stopped or continued."""
    if converged:
        return "threshold"
    if score_diff is not None and score_diff < spec.convergence_delta:
        return "convergence"
    if round_number >= spec.max_rounds:
        return "max_rounds"
    if score is not None and score < spec.min_score + 1:
        return "stuck"
    return "continue"
```

### T2：agents/reflector.py 确认 score 0-10 输出

```python
# src/multiscribe_agent/agents/reflector.py  调整 REFLECTOR_INSTRUCTION：

REFLECTOR_INSTRUCTION = """Assess whether the output satisfies the task.
Return only JSON: {"quality":"pass|fail","score":0.0,"feedback":"..."}.
The score must be between 0 and 10 (integers or 0.5 increments).
Do not include Markdown fences."""

# 并在 assess() 内把校验范围从 0-1 改为 0-10：
if not 0 <= float(score) <= 10:
    raise ValueError("reflection score must be between 0 and 10")
```

### T3：workflow/protocols.py 更新 LoopReflector

```python
# src/multiscribe_agent/agents/workflow/protocols.py  追加

from typing import Protocol


class LoopReflector(Protocol):
    """Adapter for the multi-round loop reflector."""

    async def assess(self, task: str, output: str) -> Reflection: ...
```

（保持现有签名，score 范围语义在 reflector 层保证。）

### T4：eval/feedback_loop.py 评估驱动

```python
# src/multiscribe_agent/eval/feedback_loop.py
"""Evaluate → trigger refinement workflow when score falls below threshold."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from multiscribe_agent.agents.workflow.graph import WorkflowGraph
from multiscribe_agent.domain.models import WorkflowDefinition

RefinementAction = Literal["retry", "switch_agent", "human_review"]


@dataclass(frozen=True, slots=True)
class RefinementDecision:
    """One decision returned by the feedback loop coordinator."""

    action: RefinementAction
    reason: str
    suggested_workflow: str | None
    score: float
    threshold: float


def trigger_refinement(
    score: float,
    threshold: float = 7.0,
    *,
    workflows_dir: Path | None = None,
    preferred_workflow: str | None = None,
) -> RefinementDecision:
    """Inspect the score and return the recommended action."""
    if score >= threshold:
        return RefinementDecision(
            action="retry",
            reason=f"score {score:.2f} below threshold {threshold:.2f}",
            suggested_workflow=preferred_workflow,
            score=score,
            threshold=threshold,
        )
    if score >= threshold - 2.0:
        return RefinementDecision(
            action="retry",
            reason="score near threshold — retry with current agent",
            suggested_workflow=preferred_workflow,
            score=score,
            threshold=threshold,
        )
    if workflows_dir is not None and workflows_dir.is_dir():
        candidates = sorted(workflows_dir.glob("*.yaml"))
        if candidates:
            return RefinementDecision(
                action="switch_agent",
                reason=f"score {score:.2f} far below threshold; try alternate workflow",
                suggested_workflow=candidates[0].stem,
                score=score,
                threshold=threshold,
            )
    return RefinementDecision(
        action="human_review",
        reason="no alternate workflows available; escalate to operator",
        suggested_workflow=None,
        score=score,
        threshold=threshold,
    )


def load_refinement_workflow(name: str, workflows_dir: Path) -> WorkflowDefinition:
    """Load a YAML workflow definition by stem (e.g. 'digest-retry')."""
    path = workflows_dir / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"workflow not found: {path}")
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return WorkflowDefinition.model_validate(raw)
```

### T5：data/skills/loop-engineering-patterns.md

```markdown
---
name: loop-engineering-patterns
description: 多轮自评迭代的最佳策略与退出条件配置
version: 1.0
triggers:
  - workflow.loop
  - agent.reflection
---

# Loop Engineering Patterns

## 退出条件优先级

1. **score_threshold 优先**：分数达到目标立即收敛，避免浪费 token。
2. **convergence_delta 次之**：连续两轮分数差 < 0.5 表示已饱和，停止。
3. **max_rounds 兜底**：避免无限循环，默认 3 轮。

## 常见反模式

- max_rounds=1：等于无自评，等同于一次性生成。
- score_threshold=10：永远不收敛，浪费 token。
- convergence_delta=0.1：过早收敛，质量低。

## 推荐参数

| 任务难度 | max_rounds | score_threshold | convergence_delta |
|---|---|---|---|
| 简单摘要 | 2 | 7.5 | 0.3 |
| 复杂分析 | 4 | 8.5 | 0.5 |
| 多步推理 | 5 | 9.0 | 0.7 |

## 与 P21 评估联动

当 P21 评估分数 < threshold，自动调用 `feedback_loop.trigger_refinement()`：
- retry：再次跑当前工作流
- switch_agent：切换到备用工作流（如 digest-retry）
- human_review：交给人工
```

---

## 六、测试与质量门

```bash
.venv\Scripts\python.exe -m pytest tests/agents/test_loop_node_multi_round.py \
    tests/agents/test_loop_exit_conditions.py tests/eval/test_feedback_loop.py \
    tests/skills/test_loop_skill_discovery.py -v -p no:cacheprovider --basetemp .pytest-tmp-p24

# 全量
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

# 静态门
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy src
```

---

## 七、完成定义

- [ ] 白名单 11 个文件全部创建/修改
- [ ] `pytest tests/agents/test_loop_node_multi_round.py` 等新测试全绿（≥ 10 用例）
- [ ] `pytest -q` 全量无回归（特别注意 `tests/agents/test_reflector.py` 范围调整后仍绿）
- [ ] ruff / mypy 全绿
- [ ] `data/skills/loop-engineering-patterns.md` 可被 scanner 发现
- [ ] `codex/reviews/P24-REVIEW.md` 填写完毕

---

## 八、文件清单

```
src/multiscribe_agent/agents/workflow/loop_node.py          [修改]
src/multiscribe_agent/agents/workflow/protocols.py          [修改]
src/multiscribe_agent/agents/workflow/__init__.py           [修改]
src/multiscribe_agent/agents/reflector.py                  [修改]
src/multiscribe_agent/eval/feedback_loop.py                [新增]
data/skills/loop-engineering-patterns.md                   [新增]
tests/agents/test_reflector.py                             [修改]
tests/agents/test_loop_node_multi_round.py                 [新增]
tests/agents/test_loop_exit_conditions.py                  [新增]
tests/eval/test_feedback_loop.py                           [新增]
tests/skills/test_loop_skill_discovery.py                  [新增]
```