# Review: `P10-DAG工作流引擎`

**执行包：** `docs/phases/P10-DAG工作流引擎.md`
**完成日期：** 2026-07-17
**执行者：** Codex

## 1. 范围核对

| 文件 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/agents/workflow/__init__.py` | 新增 | 工作流包导出 |
| `src/multiscribe_agent/agents/workflow/protocols.py` | 新增 | 注入式 Agent 与 Loop 评估协议 |
| `src/multiscribe_agent/agents/workflow/{engine,graph,loop_node,events}.py` | 新增 | DAG 执行、建图、循环、事件 |
| `tests/agents/workflow/{test_engine,test_graph,test_loop}.py` | 新增 | P10 单元测试 |
| `codex/reviews/P10-REVIEW.md` | 修改 | 本 review |

- [x] 所有改动均在 P10 白名单内。
- [x] `agents/executor.py`、领域端口、具体插件和 P11 流水线均未修改。

## 2. 验收条件

| # | 条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | 显式边与 input_map 隐式边合并 | 通过 | `test_build_graph_combines_explicit_and_input_map_edges` |
| 2 | 环检测与报错 | 通过 | `test_detect_cycle_returns_concrete_cycle`、`test_cycle_yields_workflow_error_and_stream_lifecycle_is_complete` |
| 3 | Kahn 分层与同层并行 | 通过 | `engine.py:77` 使用 `asyncio.gather(..., return_exceptions=True)`；`test_parallel_level_runs_concurrently` 断言最大并发数为 2 |
| 4 | input_map 与 0/1/N 前驱输入推导 | 通过 | `test_linear_execution_passes_previous_output`、`test_input_map_nested_workflow_and_disabled_pass_through` |
| 5 | 子工作流递归 | 通过 | `test_input_map_nested_workflow_and_disabled_pass_through` |
| 6 | Loop 收敛、上限、反馈注入 | 通过 | `test_llm_loop_retries_with_feedback_then_converges`、`test_loop_returns_last_output_at_iteration_limit`、`test_rule_exit_condition_stops_when_keyword_appears` |
| 7 | 非叶子空输出中断 | 通过 | `test_empty_output_halts_downstream_execution` |
| 8 | 完整 stream 生命周期事件 | 通过 | `test_cycle_yields_workflow_error_and_stream_lifecycle_is_complete`；Loop 产生 `loop_iteration` |
| 9 | AgentStepExecutor Protocol 注入 | 通过 | `protocols.py` 为 `@runtime_checkable`；`test_linear_execution_passes_previous_output` 验证 Fake 实例 `isinstance(..., AgentStepExecutor)`；引擎未导入 `AgentExecutor` |
| 10 | 全测与 strict mypy | 通过 | 下列原始门禁输出 |

## 3. 测试与质量门

### 3.1 `ruff check .`
```text
All checks passed!
```

### 3.2 `ruff format --check .`
```text
86 files already formatted
```

### 3.3 `mypy src`
```text
Success: no issues found in 56 source files
```

### 3.4 `pytest -q`
```text
........................................................................ [ 67%]
..................................                                       [100%]
106 passed, 3 deselected in 6.79s
```

### 3.5 P10 专项
```text
...........                                                              [100%]
11 passed in 0.25s
```

## 4. 详细任务完成情况

- **T0**：`AgentStepExecutor` 以运行时可检查 Protocol 注入；另定义最小 `LoopReflector` 适配边界。
- **T1**：建图合并显式和隐式依赖，校验未知节点与重复 ID；DFS 返回具体环路径，Kahn 输出可并行层级。
- **T2**：定义结构化 workflow/step/loop 生命周期事件和 trace ID。
- **T3**：引擎按层并发执行，支持输入推导、禁用节点透传、子工作流、错误和空输出中断。
- **T4**：循环默认最多三次，支持 `llm` 评估与 `output contains 'TOKEN'` 规则，保留迭代历史并把反馈注入下一次输入。
- **T5**：使用内存 workflow store 与 fake executor，无真实网络访问。

## 5. 规范自检

- [x] 完整类型注解，无裸 `Any`。
- [x] 异步执行和并发使用 `asyncio.gather`，无 async 内阻塞 I/O。
- [x] 无密钥、真实网络或未授权范围扩张。
- [x] 领域层没有反向依赖。

## 6. 新增依赖

无。

## 7. 风险、遗留与取舍

- `LoopReflector` 是工作流层的窄适配协议。P11/P12 装配时需要将 P4 的 `Reflector.assess(task, output, provider)` 适配为该两参数协议，并提供 provider；P10 不修改黑名单中的 P4 实现。
- 并行同层步骤的完成事件按拓扑层内稳定 ID 顺序发出，以保证 stream 可预测；实际 agent 调用仍是并发的。
- 未实现 P11 的 `daily_digest` 具体业务流水线，也未接入真实插件，符合本包边界。

## 8. BLOCKED

无。

## 9. 后续包提示

P11/P12 应在组合根注入 `AgentStepExecutor`（按 agent_id 解析定义后调用 P4 executor）以及可选的 `LoopReflector` 适配器。

## 10. 自评

本包满足 `P10-DAG工作流引擎.md` 的完成定义：是。
