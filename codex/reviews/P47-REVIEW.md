# Review: P47 - 运营仪表盘

**执行包**：`docs/phases/P47-运营仪表盘.md`
**完成日期**：2026-07-29
**执行者**：Codex
**状态**：已实现、已验证、仅本地提交（未推送）

## 1. 范围核对

| 文件 | 操作 | 用途 |
| --- | --- | --- |
| `src/multiscribe_agent/infra/repositories/daily_usage.py` | 新增 | `daily_usage` 的惰性建表、日粒度累加和区间查询。 |
| `src/multiscribe_agent/services/scheduler.py` | 修改 | 成功回调携带 `usage` 时写入日汇总；分析写失败不会影响任务成功状态。 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 构造并注入共享 `DailyUsageRepository`。 |
| `src/multiscribe_agent/core/publish_history.py` | 修改 | 提供按时间窗口聚合的发布状态汇总。 |
| `src/multiscribe_agent/api/routes/publish_history.py` | 修改 | 新增认证保护的 `GET /api/publish-history/summary`。 |
| `src/multiscribe_agent/api/routes/dashboard.py` | 修改 | 新增 `GET /api/dashboard/overview`，一次返回 usage、publish、iterations、task logs。 |
| `frontend/src/operations-dashboard.tsx` | 新增 | 展示 Token、发布成功率、Loop 迭代和任务日志。 |
| `frontend/src/App.tsx` | 修改 | 增加“运营中心”导航与视图分支。 |
| `frontend/src/services/api.ts` | 修改 | 增加运营总览类型和 API 调用。 |
| `tests/infra/repositories/test_daily_usage_repo.py` | 新增 | 覆盖建表、累加、日期范围。 |
| `tests/services/test_scheduler_usage_persistence.py` | 新增 | 覆盖 scheduler 到日用量仓储的写入及无 usage 兼容性。 |
| `tests/core/test_publish_history_summary.py` | 新增 | 覆盖发布状态分组与空结果。 |
| `tests/api/test_dashboard_overview.py` | 新增 | 覆盖 overview 的四类数据与认证。 |
| `tests/api/test_publish_history_routes.py` | 新增 | 覆盖 summary 路由聚合与认证。 |

白名单之外未作代码修改；`api/deps.py` 无需变更。黑名单中的 workflow、daily digest、task log repository、LLM、config 与 `docs/` 均未修改。

任务包要求同步 `docs/phases/README.md`，但该文件在开始前已是用户未提交修改，且 P47 明确将 `docs/` 列为黑名单，因此没有触碰或纳入提交。

## 2. 验收证据

| # | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | Scheduler callback 的 usage 生成/更新当日行 | PASS | `test_scheduler_persists_usage_and_keeps_legacy_results_compatible`；`SchedulerService.execute_task()` 成功日志更新后调用 `DailyUsageRepository.upsert()`。 |
| 2 | 同日 usage 是累加，不覆盖 | PASS | `test_daily_usage_lazily_creates_and_accumulates` 断言输入 `12`、输出 `7`、总量 `19`、调用 `2`、任务 `2`。 |
| 3 | 发布汇总返回 `{total, success, error}` | PASS | `test_summary_groups_delivery_status_and_empty_is_zero`、`test_publish_history_summary_returns_aggregates`。 |
| 4 | 总览接口一次返回四类数据 | PASS | `test_dashboard_overview_merges_usage_publish_iterations_and_logs` 断言四个顶级字段、usage 和迭代数据。 |
| 5 | 前端运营页提供四种运营视图 | PASS | `frontend/src/operations-dashboard.tsx`，`npm run build` 通过。 |
| 6 | 导航可切换到 operations 视图 | PASS | `App.tsx` 新增 `operations` NavKey、导航项、文案和渲染分支；TypeScript 生产构建通过。 |
| 7 | Python 与静态质量门无回归 | PASS | 见第 3 节。 |

## 3. 测试与质量门

P47 定向测试：

```text
8 passed in 0.74s
```

```text
.venv\Scripts\python.exe -m pytest tests/infra/repositories/test_daily_usage_repo.py tests/services/test_scheduler_usage_persistence.py tests/core/test_publish_history_summary.py tests/api/test_dashboard_overview.py tests/api/test_publish_history_routes.py -q -p no:cacheprovider --basetemp .pytest-tmp-p47-final
```

全量非 e2e 回归（使用 `HF_HUB_OFFLINE=1` 避免可选模型下载）：

```text
505 passed, 4 deselected, 1 warning in 22.92s
```

```text
.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
328 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 171 source files
```

前端：

```text
cd frontend; npm run build
vite build completed successfully
```

构建中有既有远程 Google Fonts 在构建期无法解析的提示，Vite 按原样保留 URL，构建成功退出；不是 TypeScript 或产物错误。

## 4. 实现说明

- **T1 Usage 持久化**：`DailyUsageRepository` 使用 `CREATE TABLE IF NOT EXISTS`，兼容已有 SQLite 文件且不触碰黑名单的 DB migration；`ON CONFLICT(date)` 对四类计数和 task count 做原子累加。
- **T2 Publish 聚合**：`PublishHistory.summary()` 复用已有时间窗口过滤，仅按 `status` 分组并将空结果标准化为零。
- **T3 Dashboard 聚合**：总览使用 UTC 当日，缺少 usage 时返回带日期的零值对象；迭代和任务日志均限制为最近 20 条。
- **T4 前端**：复用现有 API 客户端、工作台导航和数据面板样式，不引入新的前端依赖。

## 5. 规范自检

- 全量 mypy 通过，新增生产代码没有裸 `Any`。
- DB 与 scheduler I/O 均为 async；写入异常只记录结构化日志，不破坏主任务终态。
- 用量、汇总和总览接口均不记录或返回 Prompt、工具正文、凭据或 webhook。
- 新增 API 保持现有 JWT 认证边界，测试覆盖未认证 401。
- 无新增依赖、无真实外网测试调用。

## 6. 风险、遗留与取舍

- `daily_usage` 采用 UTC 日期，和 Scheduler 当前的幂等锁日期保持一致；若运营需要按用户时区汇总，应作为独立需求设计。
- 用量落库故障会被隔离，避免把已完成的日报误标为失败；代价是该次运营统计可能缺失，日志事件为 `scheduler_usage_persistence_failed`。
- 日用量、发布历史、迭代和任务日志当前均无 TTL；总览只读取最近 20 条，数据保留策略仍应由后续阶段补齐。
- 当前运营页完成编译和接口自动化覆盖，未启动浏览器进行人工视觉验收。
- 未实现 cursor 分页、历史区间 UI、成本金额换算或告警接线，均不在 P47 范围内。

## 7. BLOCKED 项

无。

## 8. 自评

本包满足 P47 完成定义：✅。本地提交后未推送 GitHub。
