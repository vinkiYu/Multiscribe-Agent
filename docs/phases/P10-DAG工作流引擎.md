# P10 — DAG 工作流引擎（拓扑排序 + Loop 节点）

> **状态**：未开始 · **依赖**：P1, P4 · **Loop Engineering 核心载体**

## 目标

实现自研 DAG 工作流引擎：Kahn 拓扑排序 + 批次并行 + 数据依赖自动建图 + 子工作流嵌套 + 环检测 + **Loop 节点**（迭代到收敛）。这是多 Agent 编排与 Loop Engineering 的核心。

## 前置依赖

P1（WorkflowDefinition/WorkflowStep，含 Loop 扩展字段 max_iterations/exit_condition），P4（AgentExecutor，工作流的 agent 节点复用它）。

## 可改范围（白名单）

- `src/multiscribe_agent/agents/workflow/__init__.py`
- `src/multiscribe_agent/agents/workflow/engine.py`（WorkflowEngine 核心）
- `src/multiscribe_agent/agents/workflow/graph.py`（建图：显式边 + 隐式数据依赖边）
- `src/multiscribe_agent/agents/workflow/loop_node.py`（Loop 节点：迭代 + exit_condition）
- `src/multiscribe_agent/agents/workflow/events.py`（workflow 事件类型）
- `tests/agents/workflow/test_engine.py`
- `tests/agents/workflow/test_graph.py`
- `tests/agents/workflow/test_loop.py`

## 禁止改动（黑名单）

- 不动 agents/executor.py（P4；本包调用它执行 agent 节点）。
- 不实现 daily_digest 流水线（P11；本包是通用引擎）。
- 不依赖具体插件（用 fake executor 测试）。

## 详细任务

### T1. `agents/workflow/graph.py` — 建图

移植原项目 `buildDependencyGraph` + `buildSuccessorMap`：

```python
@dataclass
class WorkflowGraph:
    steps: dict[str, WorkflowStep]           # id -> step
    edges: list[tuple[str, str]]             # 依赖边 (from, to): from 必须先于 to
    successors: dict[str, list[str]]         # 后继映射
    predecessors: dict[str, list[str]]       # 前驱映射

def build_graph(workflow: WorkflowDefinition) -> WorkflowGraph:
    """合并两类边：
    1. 显式边：step.next_step_id / step.next_step_ids
    2. 隐式边：step.input_map 的值引用了其他 step id → 自动建依赖边
    返回合并后的图。
    """

def detect_cycle(graph: WorkflowGraph) -> list[str] | None:
    """检测环，返回环上的节点 id 列表（用于报错），无环返回 None。"""

def topological_levels(graph: WorkflowGraph) -> list[list[str]]:
    """Kahn 算法分层：返回 [level0_ids, level1_ids, ...]，
    同一 level 内无依赖关系可并行。环存在时抛 WorkflowError。"""
```

- 隐式边逻辑：若 step B 的 `input_map = {"data": "A"}`（引用 step A 的输出），则 A→B 是边。
- input_map 值还可能引用 `"start"`（工作流初始输入），不产生边。
- `enabled=False` 的 step：保留在图里但执行时 pass-through（输入原样输出）。

### T2. `agents/workflow/events.py` — 事件

```python
@dataclass
class WorkflowEvent:
    type: Literal["workflow_start","step_start","step_complete","step_error",
                  "loop_iteration","workflow_complete","workflow_error"]
    data: dict[str, Any]
    trace_id: str
```

### T3. `agents/workflow/engine.py` — WorkflowEngine

```python
class WorkflowEngine:
    def __init__(self, agent_executor: AgentExecutor, workflow_store, reflector=None): ...
    async def run(self, workflow_id: str, input_data: Any, *, date: str | None = None) -> dict:
        """非流式：返回 {step_results: dict[str, Any], final: Any}。"""
    def stream(self, workflow_id: str, input_data: Any, *, date=None) -> AsyncIterator[WorkflowEvent]:
        """流式：yield 事件。"""
```

核心执行（移植原 `runWorkflow`）：
1. 加载 workflow 定义。`build_graph` + `detect_cycle`（有环报错）+ `topological_levels`。
2. 维护 `step_results: dict[str, Any]`（含 `step_results["start"] = input_data`）。
3. 按 level 顺序执行；同 level 用 `asyncio.gather(return_exceptions=True)` **并行**。
4. 每步 `execute_step`：
   - `enabled=False`：pass-through（输出 = 输入）。
   - `step_type="agent"`：调 `agent_executor.run(step.agent_id, step_input)`，取 result.content。
   - `step_type="workflow"`：递归 `self.run(step.workflow_id, step_input)`（子工作流）。
   - **Loop 节点**：若 step 有 `max_iterations`，走 `loop_node` 逻辑。
5. **input 推导**（移植 `executeStep`）：
   - 有 input_map：构造 `{param: step_results[source_id]}`；单键直接透传值。
   - 无 input_map：0 前驱用 `step_results["start"]`；1 前驱透传；N 前驱合并 `{step_id: output}`。
6. **空响应中断**：某 step 输出空且**有后继** → 中断整个 workflow（yield workflow_error 或带说明 complete）；无后继则容忍空继续。
7. yield step_start/step_complete/step_error 事件。

### T4. `agents/workflow/loop_node.py` — Loop 节点（Loop Engineering 核心）

```python
async def execute_loop_step(step: WorkflowStep, step_input: Any,
                            agent_executor, reflector, *, trace_id) -> tuple[Any, list[dict]]:
    """Loop 节点执行：迭代最多 max_iterations 次。

    每轮：
    1. 执行 agent（带上一轮反馈，若有）
    2. reflector.assess(task, output) → Reflection
    3. reflection.should_retry == False 或 达 max_iterations → 返回
    4. 否则带 feedback 重跑

    返回 (最终输出, 迭代历史)。每轮记 loop_iteration 事件。
    """
```

- 这是「执行→评估→精炼→收敛」的 Loop 闭环。
- `exit_condition` 字段：支持 `"llm"`（用 reflector 自评）或规则表达式（简单关键字判断，如 "output contains 'DONE'"）；MVP 实现 llm 模式 + 基础规则。
- `max_iterations`：硬上限（默认 3），防死循环。
- 收敛或达上限都正常返回（达上限时在历史标注 `converged=False`）。

### T5. 测试（fake agent executor）

- `tests/agents/workflow/test_graph.py`：
  - 显式边（next/next_ids）建图正确。
  - 隐式边（input_map 引用）自动建边。
  - 环检测（造一个 A→B→C→A，detect_cycle 返回节点列表）。
  - topological_levels 分层正确（并行层 vs 串行层）。
  - enabled=False 保留在图。
- `tests/agents/workflow/test_engine.py`（用 FakeAgentExecutor，按 agent_id 返回预设输出）：
  - 线性 A→B→C 执行顺序正确，input 透传正确。
  - 并行分支（同 level）确实并行（用 asyncio.Event 计时或顺序标记验证）。
  - input_map 命名注入正确。
  - 子工作流嵌套执行。
  - enabled=False pass-through。
  - 空响应中断（有后继时停）。
  - 环 → 抛 WorkflowError。
  - stream 事件序列完整。
- `tests/agents/workflow/test_loop.py`：
  - 第 1 轮 fail → 第 2 轮 pass → 收敛（2 轮）。
  - 持续 fail → max_iterations 上限退出（标 converged=False）。
  - 规则 exit_condition 命中即停。

## 验收条件

1. 建图：显式边 + 隐式数据依赖边合并正确（测试覆盖三种边来源）。
2. 环检测有效（造环能检出并报错）。
3. Kahn 分层 + 同层并行（有并行证据）。
4. input 推导（input_map 命名 / 无 map 的 0/1/N 前驱规则）正确。
5. 子工作流递归嵌套执行。
6. Loop 节点：收敛 / 达上限两种终止，反馈注入生效。
7. 空响应中断规则正确。
8. stream 事件序列完整。
9. 全测试绿，mypy strict。

## 测试方式

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/agents/workflow -q
```
建议附一个多分支+并行+Loop 的复杂 workflow 的执行事件序列输出，作为强证据。原始输出贴 review。

## 完成定义

验收全满足；并行执行有明确证据（非伪并行）；Loop 收敛逻辑可观察。P11 流水线将作为本引擎的第一个真实工作流。
