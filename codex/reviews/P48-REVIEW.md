# Review: P48 - 策展准确性轻量 Eval

**执行包**：`docs/phases/P48-策展Eval.md`
**完成日期**：2026-07-29
**执行者**：Codex
**状态**：已实现、已验证、待本地提交（不推送）

## 1. 范围核对

| 文件 | 操作 | 用途 |
| --- | --- | --- |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | 修改 | 从既有 `loop_iteration` 事件汇总 curation Loop 指标，返回并持久化评估结果。 |
| `src/multiscribe_agent/agents/curator_judge.py` | 新增 | 默认关闭的 LLM-as-judge 框架和严格 JSON 输出校验。 |
| `src/multiscribe_agent/infra/repositories/curation_evaluations.py` | 新增 | `curation_evaluations` 惰性建表、幂等 upsert、查询和汇总。 |
| `src/multiscribe_agent/api/routes/curation_evaluations.py` | 新增 | 认证保护的评估列表与汇总接口。 |
| `src/multiscribe_agent/api/routes/dashboard.py` | 修改 | overview 增加 `evaluation` 数据块。 |
| `src/multiscribe_agent/app.py` | 修改 | 注册新的评估路由。 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 注入 `CurationEvaluationRepository` 至日报运行链路。 |
| `frontend/src/operations-dashboard.tsx` | 修改 | 增加“策展质量评估”指标和最近记录表。 |
| `frontend/src/services/api.ts` | 修改 | 增加评估 API 数据类型。 |
| `tests/agents/test_curator_judge.py` | 新增 | Judge 默认禁用、启用校验、日报回传与持久化。 |
| `tests/infra/repositories/test_curation_evaluations.py` | 新增 | 仓储幂等、日期查询和聚合。 |
| `tests/api/test_curation_evaluations_routes.py` | 新增 | 认证列表/汇总路由。 |
| `tests/api/test_dashboard_overview.py` | 修改 | overview 返回 evaluation 数据块。 |

修订后的任务包明确允许使用实际入口 `src/multiscribe_agent/app.py`。黑名单中的 `loop_node.py`、`reflector.py`、`eval/`、`infra/db.py`、`executor.py` 与全部 `docs/` 未修改。

任务包的完成定义仍写有更新 `docs/phases/README.md`，但 `docs/` 同时处于黑名单，且该文件在开工前已存在用户未提交修改；因此未触碰或提交该文件。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | `daily_digest.run()` 返回 `loop_summary` 和 `workflow_run_id` | PASS | `test_daily_digest_returns_loop_summary_and_workflow_run_id`，验证两个字段均存在。 |
| 2 | `loop_summary` 含 rounds/converged/exit_reason/final_score | PASS | 同一测试断言 `1 / true / threshold / 9.0`。 |
| 3 | Repository upsert 不重复写且更新有效 | PASS | `test_upsert_is_idempotent_per_workflow_run`，同一 run 两次写入后仅保留一行。 |
| 4 | `query()` 支持日期过滤与倒序 | PASS | `test_query_filters_by_date_and_orders_newest_first`。 |
| 5 | `summary()` 返回评分、收敛率、运行数、退出原因分布 | PASS | `test_summary_returns_quality_convergence_and_exit_reason_metrics`，断言 `avg_score=8.0`、`converge_rate=50.0`。 |
| 6 | `GET /api/curation-evaluations` 认证并返回列表 | PASS | `test_curation_evaluation_routes_are_authenticated_and_aggregate`。 |
| 7 | `GET /api/curation-evaluations/summary` 认证并返回聚合 | PASS | 同一测试及匿名 401 测试。 |
| 8 | `/api/dashboard/overview` 返回 evaluation | PASS | `test_dashboard_overview_merges_usage_publish_iterations_and_logs` 断言 `avg_final_score=9.0`。 |
| 9 | 运营中心显示评估质量面板 | PASS | `operations-dashboard.tsx` 包含今日评分、收敛率、最近退出原因和最近评估表；前端构建通过。 |
| 10 | CuratorJudge 默认不引入 LLM 调用 | PASS | `test_curator_judge_is_disabled_by_default_without_provider_call` 断言 provider 调用次数为 0。 |
| 11 | ruff / mypy / pytest 全绿 | PASS | 见第 3 节。 |

## 3. 测试与质量门

P48 定向测试：

```text
11 passed in 0.65s
```

日报流水线回归及 P48 测试：

```text
36 passed in 0.82s
```

```text
.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
334 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 174 source files
```

全量非 e2e 测试：

```text
514 passed, 4 deselected, 1 warning in 23.17s
```

全量 pytest 使用 `HF_HUB_OFFLINE=1`，避免可选模型下载。唯一 warning 为已存在的 Starlette/httpx 测试依赖弃用提示。

前端：

```text
cd frontend; npm run build
vite build completed successfully
```

Vite 保留既有远程 Google Fonts URL 的构建期解析提示，未影响 TypeScript 编译或生产产物。

## 4. 实现说明

- **T1**：日报不修改已稳定的 Loop 节点，而是消费 `WorkflowEngine.stream()` 已发出的 `loop_iteration` 事件；`_LoopIterationAccumulator` 汇总轮次、最终分、最近 delta、平均迭代分、退出原因和 reflector usage。每次成功运行同时返回 `loop_summary`/`workflow_run_id`，并以 run ID 去重写入评估表。
- **T2**：评估仓储使用 `CREATE TABLE IF NOT EXISTS`，不触碰 `infra/db.py`。`workflow_run_id` 为唯一键，upsert 只更新固定字段；汇总返回 `avg_score`、`avg_final_score`、收敛率、平均轮次和 reason 计数。
- **T3**：`CuratorJudgeConfig.enabled=False` 为默认值。Judge 未注入生产日报调用链，只有明确创建为 enabled 后才调用 Provider，避免 P48 增加成本和延迟。
- **T4/T5**：新增两个 JWT 保护的评估读接口，并将当天汇总和最多 10 条记录合并到运营总览。
- **T6**：运营中心显示今日平均分、Loop 收敛率、最新退出原因与最近十条评估记录，退出原因有中文映射。

## 5. 规范符合性自检

- 新增生产代码有完整注解，`mypy src` 全绿，无裸 `Any`。
- SQLite 操作均为 async；所有查询值通过参数绑定。
- 新路由沿用既有 JWT 认证边界，匿名请求自动化断言 401。
- 新增日志、API 响应及评估表不保存 Prompt、原始候选全文、API key 或 webhook。
- 无新增依赖、无真实网络或真实 LLM 测试调用。

## 6. 风险、遗留与取舍

- `CuratorJudge` 是已测试的可选框架，但默认关闭且尚无 Settings/UI 开关。这是任务包的 Layer 1 决策，避免默认额外 LLM 成本；启用策略、模型选择和 ground truth 校准属于后续 Layer 2。
- 评估数据来自当前 Loop 自评，而非人工标注真值，适合运营趋势与异常观察，不能等同于离线准确率基准。
- `curation_evaluations` 目前没有 TTL/清理任务；查询和 dashboard 已做 10/200 条界限，长期保留策略待后续阶段处理。
- 当前 overview 按 UTC 当日聚合，保持与 P47 scheduler usage 日期语义一致。
- 前端已完成编译验证，未额外启动浏览器做人工视觉截图。

## 7. BLOCKED 项

无。任务包中的路由文件路径已由决策者修订为实际的 `src/multiscribe_agent/app.py` 后执行。

## 8. 自评

本包满足 P48 完成定义：✅。Review 随本阶段本地 commit 提交，未推送 GitHub。
