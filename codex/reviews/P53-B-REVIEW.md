# P53-B Review: 告警历史与去重

## 结论

P53-B 已完成，建议提交 ZCode 复审。本阶段实现告警事件持久化、按规则 5 分钟 cooldown 去重、认证查询 API 和运营中心展示；未修改告警规则定义、Publisher callback 行为或其他前端页面。

## 变更摘要

- `infra/db.py`
  - SQLite schema 新增 `alert_history` 表及 `fired_at`、`rule_name` 索引。
  - PostgreSQL 初始化路径同步创建同名表和索引，避免切换后首次告警写入失败。
- `core/alert_history.py`
  - 新增 `AlertRecord` 和 `AlertHistoryRepository`。
  - 支持记录、按时间倒序查询、按 acknowledged 状态过滤和 operator 确认。
  - 使用无外部依赖的 26 字符 ULID 作为主键，metadata 以 JSON 文本存储。
- `observability/alerts.py`
  - `AlertEngine` 增加 `_last_fired` 和 `DEFAULT_COOLDOWN_SECONDS = 300`。
  - `_fire()` 通过 `_record_to_history()` 持久化后继续执行原有 callbacks。
  - 持久化失败只记录结构化日志，不阻塞飞书/企微等告警发布；无事件循环时不会错误消耗 cooldown。
- `bootstrap.py`
  - 初始化 `AlertHistoryRepository` 并通过 `attach_alert_history()` 注入 AlertEngine。
- `api/routes/alerts.py` 与 `app.py`
  - 新增受认证保护的 `GET /api/alerts`，支持 `limit` 和 `acknowledged` 查询参数。
- `frontend/src/services/api.ts`
  - 新增 `AlertRecord` 类型和 `alertsApi.list()`。
- `frontend/src/operations-dashboard.tsx`
  - 新增告警历史 panel，按时间展示规则、指标、阈值、当前值和确认状态，并覆盖空状态。

## 验收证据

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| `alert_history` 表和两个索引创建 | 通过 | `infra/db.py` SQLite schema 与 PostgreSQL 初始化分支 |
| Repository 返回唯一 ULID | 通过 | `tests/core/test_alert_history.py`，断言 26 字符 ID |
| 查询按时间倒序并支持 ack 过滤 | 通过 | `test_alert_history_records_queries_and_acknowledges` |
| 同一 `rule_name` 300 秒内只触发一次 | 通过 | `test_alert_engine_persists_once_during_rule_cooldown` |
| `_fire()` 调用历史记录且失败不阻断 callback | 通过 | `tests/observability/test_alert_history_wiring.py` |
| bootstrap 注入历史 Repository | 通过 | `bootstrap.py` 的 `attach_alert_history` 接线 |
| `/api/alerts` 认证与响应 | 通过 | `tests/api/test_alert_routes.py` |
| 前端 API 类型、空状态和告警 panel | 通过 | `frontend/src/services/api.ts`、`operations-dashboard.tsx` |

## 测试记录

```text
.venv\Scripts\python.exe -m pytest tests/core/test_alert_history.py tests/observability/test_alert_history_wiring.py tests/api/test_alert_routes.py -v -p no:cacheprovider --basetemp .pytest-tmp-p53b-final-target
5 passed

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p53b-full
621 passed, 6 deselected, 1 warning

.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
370 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 189 source files

cd frontend; npm run build
Build succeeded; Vite only reported existing remote font resolution and chunk-size warnings.

cd frontend; npm run lint
Passed
```

唯一 pytest warning 是 Starlette TestClient 与 httpx 的弃用提示，与本阶段改动无关。API 定向测试第一次因系统临时目录权限失败，改用仓库内 `--basetemp` 后通过；这不是产品代码失败。

## 风险与边界

1. cooldown 状态保存在进程内 `_last_fired`，服务重启后窗口重置；历史记录仍持久化，但本阶段不做跨进程/分布式 cooldown。
2. API 只读告警历史，acknowledge Repository 已实现但没有新增确认端点，按任务包约束留给后续阶段。
3. 本阶段不自动清理历史数据；保留周期和归档策略留给后续运营治理任务。
4. 告警持久化与发布 callback 是串行执行的，数据库写入慢时会延迟通知，但失败会被隔离，不会丢失原 callback 执行机会。
5. ULID 生成使用本地时间毫秒和加密随机字节；排序查询仍以数据库 `fired_at` 为主，不能将 ID 顺序作为事件时间的唯一真相。

## 提交范围

本阶段提交应仅包含：

- `src/multiscribe_agent/infra/db.py`
- `src/multiscribe_agent/core/alert_history.py`
- `src/multiscribe_agent/observability/alerts.py`
- `src/multiscribe_agent/bootstrap.py`
- `src/multiscribe_agent/api/routes/alerts.py`
- `src/multiscribe_agent/app.py`
- `frontend/src/services/api.ts`
- `frontend/src/operations-dashboard.tsx`
- `tests/core/test_alert_history.py`
- `tests/observability/test_alert_history_wiring.py`
- `tests/api/test_alert_routes.py`
- `codex/reviews/P53-B-REVIEW.md`

工作区中原有的 `P32/P33/P50` Review 修改未纳入本阶段提交。
