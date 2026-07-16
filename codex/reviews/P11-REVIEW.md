# Review: `P11-每日推送流水线`

**执行包：** `docs/phases/P11-每日推送流水线.md`
**完成日期：** 2026-07-17
**执行者：** Codex

## 1. 范围核对

| 文件 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/agents/pipelines/__init__.py` | 新增 | 流水线包导出 |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | 新增 | 五节点 DAG、去重、精选、Loop、调度适配 |
| `src/multiscribe_agent/agents/pipelines/prompts.py` | 新增 | 精选与概览 prompt |
| `src/multiscribe_agent/renderers/models.py` | 新增 | `CuratedDigest` 共享模型 |
| `src/multiscribe_agent/renderers/__init__.py` | 修改 | 导出 `CuratedDigest` |
| `src/multiscribe_agent/services/publishing.py` | 新增 | 并发 fan-out 发布服务 |
| `src/multiscribe_agent/services/__init__.py` | 修改 | 导出 `PublishingService` |
| `tests/agents/pipelines/test_daily_digest.py` | 新增 | 流水线端到端 mock 测试 |
| `tests/services/test_publishing.py` | 新增 | fan-out 容错测试 |
| `codex/reviews/P11-REVIEW.md` | 新增 | 本 review |

- [x] 所有改动均在 P11 白名单内。
- [x] 未修改 `workflow/engine.py`、ingestion、Feishu/WeCom publisher 或其它黑名单文件。
- [x] 复用 P7/P8 既有 `DigestItem`，只新增其聚合容器 `CuratedDigest`，未复制模型。

## 2. 验收条件

| # | 条件 | 状态 | 证据 |
| :--- | :--- | :--- |
| 1 | 5 节点 DAG 与 input_map 依赖，且引擎可运行 | 通过 | `test_workflow_declares_five_nodes_and_data_dependencies`；`test_daily_digest_runs_end_to_end_with_dedupe_top_n_loop_and_fanout` |
| 2 | 精选 JSON、按评分排序、top-N 截断 | 通过 | 端到端测试的无序评分输入断言输出顺序 `Three, One` 与 `result_count == 2` |
| 3 | Loop 自评、反馈再生成、上限由 P10 执行 | 通过 | `RetryOnceReflector` 首轮 retry；端到端测试断言第二次 curator prompt 含 `improve summaries`；stream 测试断言 2 个 `loop_iteration` |
| 4 | URL / SHA-256 去重 | 通过 | 端到端注入同一规范化 URL 的 3 条来源，断言 `total_scanned == 2` |
| 5 | fan-out 并发多端与单端容错 | 通过 | `test_fanout_isolates_target_failure_and_returns_per_target_status`；端到端中 `good=success`、`bad=error` |
| 6 | 非法 JSON 兜底 | 通过 | `_decode_json` 先严格解析、后恢复嵌入 JSON；`test_stream_exposes_loop_iteration_and_invalid_json_becomes_workflow_error` 覆盖无法恢复时的 `WorkflowError` |
| 7 | 注册到 TaskExecutorRegistry | 通过 | `register_daily_digest_executor`；`test_registered_scheduler_callback_runs_daily_digest_task` 获取并调用 `daily_digest` 回调 |
| 8 | 全测、无真实网络 | 通过 | mock ingestion/repository/curator/publisher；下列全库原始输出 |

## 3. 测试与质量门

### 3.1 `ruff check .`
```text
All checks passed!
```

### 3.2 `ruff format --check .`
```text
93 files already formatted
```

### 3.3 `mypy src`
```text
Success: no issues found in 61 source files
```

### 3.4 `pytest -q`
```text
........................................................................ [ 64%]
.......................................                                  [100%]
111 passed, 3 deselected in 6.68s
```

### 3.5 P11 专项
```text
.....                                                                    [100%]
5 passed in 0.30s
```

## 4. 详细任务完成情况

- **T1**：复用 P7/P8 的 `DigestItem`；新增不可变 `CuratedDigest`，避免跨 renderer 重复定义。
- **T2**：提供严格 JSON 精选 prompt 与可选概览 prompt；精选输出支持 Markdown fence 等噪声中的嵌入 JSON 恢复。
- **T3**：`PublishingService.fanout` 使用 `asyncio.gather(return_exceptions=True)`，每端独立渲染和发布，返回每端状态。
- **T4**：五节点工作流依次执行 ingest、dedupe、curate Loop、overview、fanout；采集后按完整 UTC 日范围读取持久化数据，按 URL 或 SHA-256 去重，调度回调可从 `ScheduleTask.config` 构建运行配置。
- **T5**：新增无网络 mock 测试，覆盖端到端数据流、Loop 反馈、非法 JSON、target 容错和 P9 注册。

## 5. 规范自检

- [x] 完整类型注解；严格 mypy 通过。
- [x] 外部边界均为异步；fan-out 使用并发 gather。
- [x] 无真实 LLM、RSS 或 webhook 调用；测试全部使用 fake/mock。
- [x] 无硬编码密钥，日志只记录目标和异常类型。
- [x] 未反向改变 domain 或前置阶段实现。

## 6. 新增依赖

无。

## 7. 风险、遗留与取舍

- 实际 webhook/secret 仍由组合根在构造 `PublishingService` 时注入 `publisher_options`；P11 不存储或输出这些敏感配置，P12 负责应用装配。
- P10 的多 input_map 值目前以 Python 映射字符串进入 AgentStepExecutor；P11 使用 `ast.literal_eval` 安全恢复该受控内部值。后续若 P10 改为结构化 executor 输入，可移除此兼容适配。
- `DigestItem.original_id` 未新增：P7/P8 的既有共享模型没有该可选字段，P11 仅在 curation 内部以 UnifiedData ID 关联 URL/来源，发布模型保持兼容。
- 未实现真实 e2e 推送，符合任务包要求；P13 负责真实 e2e。

## 8. BLOCKED

无。

## 9. 后续包提示

P12 应在应用组合根创建 `DailyDigestPipeline`、注入真实 curator/LoopReflector、来源仓储和带 webhook options 的 `PublishingService`，随后调用 `register_daily_digest_executor`。

## 10. 自评

本包满足 `P11-每日推送流水线.md` 的完成定义：是。
