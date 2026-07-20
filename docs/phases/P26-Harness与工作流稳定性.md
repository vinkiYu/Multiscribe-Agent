# 执行包：P26 — Harness 与工作流稳定性

> **阶段**：阶段五（架构债清理）
> **目标**：修复评估报告 4 条 P1 缺陷（P1-1/P1-2/P1-3/P1-4），提升 Agent 运行时稳定性。
> **依赖**：P25.1（P0 门禁）。
> **预估**：4 个工作日。

---

## 一、目标与验收口径

**核心目标**：
- **P1-1**：ReAct 循环检测重复工具调用死锁，提前退出。
- **P1-2**：Token 预算预警机制（部分在 P25.1 已做 `should_warn_budget`，本包补**事件流**与 executor 联动）。
- **P1-3**：引入轻量领域事件总线，解耦跨模块通信。
- **P1-4**：Loop 节点迭代历史持久化，进程崩溃可恢复。

**验收口径**：
- 4 条缺陷修复，定向测试覆盖。
- 全量 pytest + ruff + mypy 全绿。

---

## 二、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | 连续 3 次调用同一工具 + 相同参数 → executor yield `loop_detected` 事件并退出 | `test_executor_deadlock_detection.py` |
| 2 | 预算占用 ≥ 80% → executor yield `budget_warning` 事件（不阻塞） | 单测 |
| 3 | `EventBus.publish("digest.completed", payload)` → 订阅者收到回调 | `test_event_bus.py` |
| 4 | `EventBus` 异步、线程安全、订阅异常隔离（一个订阅者抛错不影响其他） | 单测 |
| 5 | Loop 节点每轮迭代结果写入 `workflow_iterations` 表 | `test_loop_persistence.py` |
| 6 | 进程重启后 `resume_loop(workflow_run_id)` 能从最近一轮继续 | 单测 |
| 7 | 全量 pytest + ruff + mypy 通过 | 原始输出 |

---

## 三、可改范围（白名单）

| 文件路径 | 操作 | 涵盖缺陷 |
|---|---|---|
| `src/multiscribe_agent/agents/executor.py` | **修改** | P1-1, P1-2 |
| `src/multiscribe_agent/agents/events.py` | **修改**（新增 `loop_detected` / `budget_warning` 事件类型） | P1-1, P1-2 |
| `src/multiscribe_agent/core/event_bus.py` | **新增** | P1-3 |
| `src/multiscribe_agent/agents/workflow/loop_node.py` | **修改**（持久化钩子） | P1-4 |
| `src/multiscribe_agent/agents/workflow/iteration_store.py` | **新增** | P1-4 |
| `src/multiscribe_agent/infra/db.py` | **修改**（追加 `workflow_iterations` 表） | P1-4 |
| `src/multiscribe_agent/bootstrap.py` | **修改**（装配 EventBus 单例） | P1-3 |
| `tests/agents/test_executor_deadlock_detection.py` | **新增** | P1-1 |
| `tests/core/test_event_bus.py` | **新增** | P1-3 |
| `tests/agents/workflow/test_loop_persistence.py` | **新增** | P1-4 |

---

## 四、禁止改动（黑名单）

- `src/multiscribe_agent/agents/context.py`（P25.1 已改 token 预警 API；本包只读不写）
- `src/multiscribe_agent/agents/workflow/engine.py`（P25.1 已改超时；本包不改主循环）
- `src/multiscribe_agent/api/routes/*.py`（事件总线不直接暴露 HTTP）
- `frontend/`、`docs/`（除本包）、`codex/`

---

## 五、详细任务

### T1：P1-1 ReAct 死锁检测（`agents/executor.py`）

**问题定位**：`executor.py:122` 的 `for round in range(...)` 只看轮数上限，不检测「连续调用相同工具+相同参数」的死循环模式。

**修复**：

```python
# src/multiscribe_agent/agents/executor.py  在 stream() 方法内追加：

DEADLOCK_WINDOW = 3  # 检查最近 3 次工具调用
DEADLOCK_MAX_REPEATS = 3  # 连续 3 次相同调用视为死锁


# stream() 循环内，在 tool_calls 处理后追加：
recent_tool_calls: list[tuple[str, str]] = []  # (tool_name, args_hash)

# 每次执行工具调用前：
for call in tool_calls:
    args_hash = hashlib.sha256(
        json.dumps(call.arguments, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]
    signature = (call.name, args_hash)

    recent_tool_calls.append(signature)
    if len(recent_tool_calls) > DEADLOCK_WINDOW:
        recent_tool_calls.pop(0)

    # 检测死锁：最近 DEADLOCK_WINDOW 次全是同一签名
    if (
        len(recent_tool_calls) == DEADLOCK_MAX_REPEATS
        and len(set(recent_tool_calls)) == 1
    ):
        yield self._event(
            "loop_detected",
            {
                "tool": call.name,
                "args_hash": args_hash,
                "consecutive_repeats": DEADLOCK_MAX_REPEATS,
                "round": round_number,
            },
            trace_id,
        )
        # 提前退出，不继续执行重复调用
        return
```

**设计要点**：
- 用 `args_hash` 而非完整 args 做签名（避免大对象比较开销）。
- 检测到后 yield 事件 + `return`（与 `max_rounds reached` 行为一致）。
- 不抛异常，调用方可通过事件感知。

---

### T2：P1-2 Token 预算预警事件（`agents/executor.py` + `agents/events.py`）

**问题定位**：P25.1 给 `HarnessContext` 加了 `should_warn_budget()`，但 executor 未消费该信号。

**修复**：

```python
# src/multiscribe_agent/agents/events.py  追加事件类型

class AgentEvent:
    ...
    # 在既有事件类型枚举中追加：
    # "loop_detected"
    # "budget_warning"


# src/multiscribe_agent/agents/executor.py  stream() 每轮开始前：
for round_number in range(1, self._max_rounds + 1):
    if context.should_warn_budget(threshold=0.8):
        yield self._event(
            "budget_warning",
            {
                "used_tokens": context.estimate_tokens(),
                "budget": context.token_budget,
                "remaining": context.estimated_tokens_remaining(),
                "round": round_number,
            },
            trace_id,
        )
    # ... 既有 round_start ...
```

**设计要点**：
- `budget_warning` 是**非阻塞**事件，Agent 继续运行，只是通知调用方。
- 调用方（如 API 层 SSE 流）可据此决定是否提前终止。

---

### T3：P1-3 领域事件总线（`core/event_bus.py` 新增）

**问题定位**：跨模块通信（如 digest 完成 → 通知 publisher；publish 失败 → 通知 monitor）目前通过直接函数调用，硬耦合。

**修复**：

```python
# src/multiscribe_agent/core/event_bus.py
"""Lightweight async in-process event bus with isolated subscriber failures."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)

AsyncSubscriber = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class EventBus:
    """Publish/subscribe bus; subscriber exceptions are logged and isolated."""

    _subscribers: dict[str, list[AsyncSubscriber]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def subscribe(self, topic: str, callback: AsyncSubscriber) -> None:
        """Register an async subscriber for a topic."""
        self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: AsyncSubscriber) -> None:
        """Remove a previously registered subscriber (no-op if missing)."""
        try:
            self._subscribers[topic].remove(callback)
        except ValueError:
            pass

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Notify all subscribers; failures are logged but do not propagate."""
        subscribers = self._subscribers.get(topic, [])
        if not subscribers:
            return
        results = await asyncio.gather(
            *(self._safe_call(sub, topic, payload) for sub in subscribers),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                log.warning(
                    "event_bus_subscriber_failed",
                    extra={"topic": topic, "error": str(result)},
                )

    async def _safe_call(
        self, sub: AsyncSubscriber, topic: str, payload: dict[str, Any]
    ) -> None:
        try:
            await sub(payload)
        except Exception as exc:
            log.warning(
                "event_bus_subscriber_error",
                extra={"topic": topic, "subscriber": getattr(sub, "__name__", "?"), "error": str(exc)},
            )
            raise  # 让 gather 收集，外层统一 log

    def clear(self) -> None:
        """Remove all subscribers (for test isolation)."""
        self._subscribers.clear()


# 进程级单例（由 bootstrap 持有，测试用 fixture 注入）
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the process-wide event bus (lazy-initialized)."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    """Override the singleton (for testing)."""
    global _event_bus
    _event_bus = bus
```

**装配**（`bootstrap.py`）：

```python
# src/multiscribe_agent/bootstrap.py  init() 内：
from multiscribe_agent.core.event_bus import get_event_bus

# 初始化（get_event_bus() 自带 lazy init）
self.event_bus = get_event_bus()
```

**典型用法**（示例，不在本包改 publishers，仅示范）：

```python
# 在 daily_digest 完成后（未来接入，本包不改）：
await context.event_bus.publish("digest.completed", {
    "date": run_date,
    "item_count": result_count,
    "targets": targets,
})
```

---

### T4：P1-4 Loop 节点迭代历史持久化

**问题定位**：`loop_node.py` 的 `history` 列表只在内存，进程崩溃或重启后丢失。

**修复**：新增 `iteration_store.py` + DB 表，Loop 每轮写入。

```python
# src/multiscribe_agent/agents/workflow/iteration_store.py
"""Persist Loop node iteration history for crash recovery and audit."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from multiscribe_agent.infra.db import Database


@dataclass(frozen=True, slots=True)
class IterationRecord:
    workflow_run_id: str
    step_id: str
    round: int
    output: str
    score: float | None
    feedback: str | None
    converged: bool
    reason: str


class IterationStore:
    """CRUD wrapper for the workflow_iterations table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def append(self, record: IterationRecord) -> None:
        """Insert one iteration row."""
        await self._db.execute(
            """
            INSERT INTO workflow_iterations
                (workflow_run_id, step_id, round, output, score, feedback, converged, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.workflow_run_id,
                record.step_id,
                record.round,
                record.output[:8000],  # 防止超长输出撑爆表
                record.score,
                record.feedback,
                int(record.converged),
                record.reason,
            ),
        )

    async def list_for_step(
        self, workflow_run_id: str, step_id: str
    ) -> list[IterationRecord]:
        """Return all iterations for one step, ordered by round."""
        rows = await self._db.fetchall(
            """
            SELECT workflow_run_id, step_id, round, output, score, feedback, converged, reason
            FROM workflow_iterations
            WHERE workflow_run_id = ? AND step_id = ?
            ORDER BY round ASC
            """,
            (workflow_run_id, step_id),
        )
        return [
            IterationRecord(
                workflow_run_id=row["workflow_run_id"],
                step_id=row["step_id"],
                round=row["round"],
                output=row["output"],
                score=row["score"],
                feedback=row["feedback"],
                converged=bool(row["converged"]),
                reason=row["reason"],
            )
            for row in rows
        ]
```

```python
# src/multiscribe_agent/infra/db.py  追加表定义：

CREATE TABLE IF NOT EXISTS workflow_iterations (
    workflow_run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    round INTEGER NOT NULL,
    output TEXT NOT NULL DEFAULT '',
    score REAL,
    feedback TEXT,
    converged INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    recorded_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    PRIMARY KEY (workflow_run_id, step_id, round)
);

CREATE INDEX IF NOT EXISTS idx_workflow_iterations_run
ON workflow_iterations(workflow_run_id);
```

**loop_node.py 改造**（保留既有签名，新增可选 store 注入）：

```python
# src/multiscribe_agent/agents/workflow/loop_node.py  execute_loop_step 签名扩展：

async def execute_loop_step(
    step: WorkflowStep,
    step_input: str,
    executor: AgentStepExecutor,
    reflector: LoopReflector | None,
    *,
    trace_id: str,
    workflow_run_id: str | None = None,
    iteration_store: IterationStore | None = None,
) -> tuple[str, list[dict[str, object]]]:
    """Execute loop; optionally persist each iteration if store is provided."""
    # ... 既有逻辑 ...
    for round_number in range(1, spec.max_rounds + 1):
        output = await executor.execute(step.agent_id, current_input)
        # ... 评估、记录 history ...
        if iteration_store is not None and workflow_run_id is not None:
            await iteration_store.append(
                IterationRecord(
                    workflow_run_id=workflow_run_id,
                    step_id=step.id,
                    round=round_number,
                    output=output,
                    score=score,
                    feedback=feedback,
                    converged=converged,
                    reason=reason,
                )
            )
    # ... 返回 ...
```

**关键约束**：
- `iteration_store` 和 `workflow_run_id` 都是**可选**，不破坏既有调用方（engine 默认不传）。
- engine 可在后续按需传入（本包不强制改 engine，留给 P26 后续）。

---

## 六、测试与质量门

```bash
.venv\Scripts\python.exe -m pytest \
    tests/agents/test_executor_deadlock_detection.py \
    tests/core/test_event_bus.py \
    tests/agents/workflow/test_loop_persistence.py \
    -v -p no:cacheprovider --basetemp .pytest-tmp-p26

# 全量回归
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

# 静态门
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy src
```

---

## 七、完成定义

- [ ] 白名单 10 个文件全部创建/修改
- [ ] 4 条 P1 缺陷修复，定向测试全绿（≥ 14 用例）
- [ ] 全量 `pytest -q` 无回归
- [ ] ruff / mypy 全绿
- [ ] `codex/reviews/P26-REVIEW.md` 填写完毕

---

## 八、文件清单

```
src/multiscribe_agent/agents/executor.py                       [修改]
src/multiscribe_agent/agents/events.py                         [修改]
src/multiscribe_agent/core/event_bus.py                        [新增]
src/multiscribe_agent/agents/workflow/loop_node.py             [修改]
src/multiscribe_agent/agents/workflow/iteration_store.py       [新增]
src/multiscribe_agent/infra/db.py                              [修改]
src/multiscribe_agent/bootstrap.py                             [修改]
tests/agents/test_executor_deadlock_detection.py               [新增]
tests/core/test_event_bus.py                                   [新增]
tests/agents/workflow/test_loop_persistence.py                 [新增]
```