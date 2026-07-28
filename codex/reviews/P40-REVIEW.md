# Review: P40 — daily_digest 成本可观测

执行包：`docs/phases/P40-daily_digest成本可观测.md`  
完成日期：2026-07-29  
执行者：Codex

## 1. 范围核对

本阶段实际修改/新增的白名单文件：

| 文件 | 操作 | 说明 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/agents/workflow/protocols.py` | 修改 | 新增观察型 executor 与 loop assessment 协议 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 透传 Agent/Reflector usage，保留 terminal error 语义 |
| `src/multiscribe_agent/agents/workflow/loop_node.py` | 修改 | LoopIteration usage 字段及事件序列化 |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | 修改 | per-run 聚合器、观察接口分支和 run 返回值 |
| `tests/agents/pipelines/test_daily_digest.py` | 修改 | 聚合、回退和 per-run 隔离测试 |
| `tests/agents/workflow/test_loop_node.py` | 新增 | loop reflector usage 透传测试 |
| `tests/test_bootstrap_agent_step_executor.py` | 新增 | bootstrap 接缝和 reflector sink 测试 |
| `codex/reviews/P40-REVIEW.md` | 新增 | 本审查报告 |

P40 之外的既有工作树改动（前端、logo、`docs/phases/README.md`、压缩包及 `daily_digest.py` 中此前的业务修复）未被回退；其中 `daily_digest.py` 的既有业务修复未纳入本次暂存提交。

## 2. 验收条件

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :---: | :--- |
| 1 | `_StoredAgentStepExecutor.execute_observed` 返回 `(content, usage)` | 通过 | `bootstrap.py:166-174`；`test_execute_observed_returns_content_and_usage` |
| 2 | `_MutableLoopAssessment` 携带 `usage` | 通过 | `bootstrap.py:132-136`；reflector sink 测试断言 assessment.usage |
| 3 | `_ProviderLoopReflector.assess` 传递 `reflection.usage` | 通过 | `bootstrap.py:116-123`；`test_provider_loop_reflector_forwards_usage_to_sink` |
| 4 | `LoopIteration` 含 reflector usage | 通过 | `loop_node.py:26-36, 139-154`；`test_loop_history_serializes_reflector_usage` |
| 5 | `_dump_iteration` 序列化 usage | 通过 | `loop_node.py:196-207`；loop 测试断言两轮 usage 字典 |
| 6 | daily digest 持有 input/output/total/call 聚合器 | 通过 | `daily_digest.py:94-119, 319-397`；端到端 usage 断言 |
| 7 | observing executor 的 curate/overview 调用被累计 | 通过 | `daily_digest.py:575-588, 626-636`；3 次 Agent + 2 次 reflector 得到 `40/8/48/5` |
| 8 | 普通 executor 回退且 usage 为零 | 通过 | `daily_digest.py:588-595, 636-637`；普通 `FakeCurator` 测试返回四项零值 |
| 9 | `run()` 返回 `usage` 子对象 | 通过 | `daily_digest.py:269-292`；daily digest 端到端断言完整字段 |
| 10 | 聚合器按 run 隔离 | 通过 | `_engine()` 每次创建 `_DigestUsage`，并发 sink 使用浅拷贝 adapter；`test_daily_digest_usage_accumulator_is_isolated_per_run` |
| 11 | 全量测试和质量门通过 | 通过 | 见第 3 节原始输出 |

## 3. 测试与质量门

### 定向测试

命令：

```text
.\.venv\Scripts\python.exe -m pytest tests/agents/pipelines/test_daily_digest.py tests/agents/workflow/test_loop_node.py tests/test_bootstrap_agent_step_executor.py -q -p no:cacheprovider --basetemp .pytest-tmp-p40
```

原始结果：

```text
28 passed in 0.70s
```

### Ruff

命令：`.\.venv\Scripts\python.exe -m ruff check .`  
原始结果：

```text
All checks passed!
```

### Ruff format

命令：`.\.venv\Scripts\python.exe -m ruff format --check .`  
原始结果：

```text
306 files already formatted
```

### Mypy

命令：`.\.venv\Scripts\python.exe -m mypy src`  
原始结果：

```text
Success: no issues found in 164 source files
```

### 全量非 e2e 测试

命令：

```text
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p40-full
```

原始结果：

```text
465 passed, 4 deselected, 1 warning in 34.85s
```

警告是现有 OpenTelemetry console exporter 在测试进程关闭后写入已关闭输出流（`ValueError: I/O operation on closed file`），不影响退出码或测试结果；本阶段未扩大到 observability exporter 生命周期治理。

## 4. 实现摘要

- `AgentRunResult.usage` 通过 `_StoredAgentStepExecutor.execute_observed[_with_memory]` 到达 daily digest；不改变原有 `execute`、memory 注入和 terminal error 行为。
- `_ProviderLoopReflector` 将 `Reflection.usage` 放入 `_MutableLoopAssessment`，并支持 run-local sink；`LoopIteration` 和 workflow `loop_iteration` 事件可见该 usage。
- `DailyDigestPipeline._engine()` 每次创建 `_DigestUsage`，curate/overview 通过 opt-in protocol 累加输入、输出、总 token 和调用次数，普通 executor 保持零值兼容。
- 对可设置 sink 的 reflector adapter 使用浅拷贝后绑定当前 run 的 sink，避免复用同一 pipeline/adapter 时相互覆盖统计；未引入 `RunBudget`、provider、数据库或新依赖。

## 5. 风险、取舍与遗留项

- 当前返回的是 token 原始计数，不是金额；金额需要 provider 价目表和后续成本看板。
- usage 仍是本次运行返回值，没有持久化到 task log 或独立表；运营历史查询留给后续阶段。
- provider 返回 `usage=None` 时无法可靠知道调用次数，兼容策略是保持零值，不猜测 token。
- 浅拷贝只隔离 adapter 壳上的 sink；如果未来 reflector 自身新增可变运行状态，应继续改为显式 run-scoped wrapper。
- 定向测试末尾可见现有 OTel exporter 关闭流警告，建议在后续 observability 阶段修复 exporter shutdown 顺序。

## 6. 自评

本阶段实现满足 P40 的功能、兼容性、per-run 隔离和质量门要求，可交由 ZCode 进行阶段复审。未提交 P40 范围外的工作树改动，也未推送 GitHub。

