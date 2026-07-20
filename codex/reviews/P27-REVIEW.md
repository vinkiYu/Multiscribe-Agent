# Review: P27-安全加固与可观测性补全

**执行包**：`docs/phases/P27-安全加固与可观测性补全.md`  
**完成日期**：2026-07-20  
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件

| 文件 | 操作 | 说明 |
| --- | --- | --- |
| `src/multiscribe_agent/infra/db.py` | 修改 | 慢查询计时、metrics、SQL 审计接线 |
| `src/multiscribe_agent/observability/sql_audit.py` | 新增 | 写操作审计与可疑模式检测 |
| `src/multiscribe_agent/observability/alerts.py` | 新增 | threshold/window/ratio 规则引擎 |
| `src/multiscribe_agent/observability/alert_rules.yaml` | 新增 | 三条默认告警规则 |
| `src/multiscribe_agent/api/middleware/csrf.py` | 新增 | double-submit cookie CSRF middleware |
| `src/multiscribe_agent/app.py` | 修改 | 默认注册 CSRF middleware |
| `src/multiscribe_agent/config.py` | 修改 | 慢查询、审计、CSRF 配置 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 装配审计、告警和指标 |
| `tests/infra/test_slow_query_logging.py` | 新增 | 慢查询日志和指标测试 |
| `tests/observability/test_alert_rules.py` | 新增 | 三种规则和 callback 测试 |
| `tests/observability/test_sql_audit.py` | 新增 | 写操作与可疑 SQL 测试 |
| `tests/api/test_csrf_protection.py` | 新增 | 403、GET、Bearer 豁免测试 |

上述文件均在 P27 白名单内；路由签名、`meter.py` 和 frontend 未改动。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | 慢查询输出 `slow_query` warning 并计数 | PASS | `infra/db.py:252-279`；`tests/infra/test_slow_query_logging.py:40-67` |
| 2 | `SLOW_QUERY_THRESHOLD_SECONDS` 可配置 | PASS | `config.py:266-275`；同一测试构造低阈值实例验证触发 |
| 3 | 支持 threshold/window/ratio | PASS | `observability/alerts.py:18-76`；`tests/observability/test_alert_rules.py:15-58` |
| 4 | 规则命中触发 callback | PASS | `alerts.py:78-96`；`tests/observability/test_alert_rules.py:61-86` |
| 5 | INSERT/UPDATE/DELETE 写入 `sql_audit_log` | PASS | `db.py:223-251`、`sql_audit.py:36-76`；`tests/observability/test_sql_audit.py:12-30` |
| 6 | DROP/UNION/-- 等模式产生 warning | PASS | `sql_audit.py:13-20, 78-96`；`tests/observability/test_sql_audit.py:33-54` |
| 7 | 浏览器 POST 缺 token 返回 403 | PASS | `csrf.py:19-50`；`tests/api/test_csrf_protection.py:17-42` |
| 8 | GET 与 Bearer 请求豁免 CSRF | PASS | `csrf.py:34-50`；`tests/api/test_csrf_protection.py:44-62` |
| 9 | 全量 pytest、ruff、mypy 通过 | PASS | 见第 3 节 |

## 3. 测试与质量门

### 3.1 全量 pytest

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-rerun
325 passed, 4 deselected, 1 warning in 32.98s
```

### 3.2 静态质量门

```text
.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
265 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 146 source files

git diff --check
通过（exit code 0）
```

## 4. 详细任务完成情况

- **T1 慢查询监控**：`execute`、`executemany`、`fetchone`、`fetchall` 的底层执行均计时；超过配置阈值写 structlog warning，并尽力更新既有 metrics registry。
- **T2 SQL 审计**：写操作审计使用同一 writer connection 的 `ContextVar`，避免审计 INSERT 递归和连接池死锁；审计表保存截断 SQL、操作类型、参数数量、可疑命中和时间。
- **T3 告警规则**：规则从 YAML 解析并校验类型，窗口规则按平均值、比率规则按超阈值样本比例计算；callback 异步调度且异常隔离。
- **T4 CSRF**：使用随机 non-HttpOnly cookie 与 `X-CSRF-Token` header 的 double-submit 校验，并使用 `secrets.compare_digest`；安全方法、Bearer API 和配置的登录/Interop 前缀豁免。

## 5. 规范符合性自检

- [x] 所有新增模块通过 `mypy --strict`。
- [x] SQL 参数仍走参数化执行；审计日志不记录 secret/token 值。
- [x] CSRF 保护在 app factory 默认开启，可由配置显式关闭。
- [x] 观察能力不可用时不会阻断主数据库流程。
- [x] 新增行为有定向测试并通过全量回归。

## 6. 依赖

无新增运行时依赖；告警 YAML 使用项目已有 `PyYAML`。

## 7. 风险、遗留与取舍

- frontend 按 P27 黑名单未改动；浏览器端需要后续在 fetch 封装中读取 `multiscribe_csrf` 并发送 `X-CSRF-Token`。当前后端对登录、Interop 前缀和 Bearer API 有明确豁免，避免破坏现有程序化客户端。
- `AlertEngine` 是进程内指标规则 evaluator，不是持久化告警平台；目前 callback 由调用方注册，后续可接 webhook、去重和冷却窗口。
- 审计日志只审计 INSERT/UPDATE/DELETE，符合本包验收；DDL 或 SELECT 审计不在本包范围。
- pytest 有一个既有 Starlette/httpx deprecation warning，不影响质量门。

## 8. BLOCKED

无。环境临时目录权限问题已通过项目内 `--basetemp` 处理。

## 9. 对后续包的提示

- 前端接入 CSRF header 后，应保留 `/api/login` 和 `/api/auth/login` 豁免，否则无法建立会话。
- 建议下一阶段为告警 callback 增加去重、重试和持久化状态，并将慢查询计数纳入默认 AlertEngine 采集链路。

## 10. 自评

本包四项 P1 缺陷均完成后端实现，定向行为由测试覆盖，全量回归和静态门通过。**判定：PASS，建议进入后续阶段；frontend CSRF header 和告警外发属于明确 follow-up。**
