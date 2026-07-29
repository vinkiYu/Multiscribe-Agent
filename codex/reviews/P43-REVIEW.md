# Review: P43-运营告警闭环与适配器健康看板

执行包：`docs/phases/P43-运营告警闭环与适配器健康看板.md`  
完成日期：2026-07-29  
执行者：Codex

## 1. 范围核对

本阶段修改仅落在任务包白名单：

| 文件 | 变更 |
| --- | --- |
| `src/multiscribe_agent/observability/meter.py` | 告警采样接线、错误/查询指标 |
| `src/multiscribe_agent/observability/publisher_alert_callback.py` | 新增发布器告警回调 |
| `src/multiscribe_agent/services/publishing.py` | 发布异常记录 `error_count` |
| `src/multiscribe_agent/infra/db.py` | 每次查询记录快/慢样本，保留旧回退 |
| `src/multiscribe_agent/config.py` | 新增 `alert_targets` 及两个环境变量别名 |
| `src/multiscribe_agent/bootstrap.py` | MetricsRegistry 接入 AlertEngine，注册告警发布回调 |
| `.env.example` | 增加系统告警发布器配置示例 |
| `tests/observability/test_meter.py` | 指标采样与导出测试 |
| `tests/observability/test_alert_wiring.py` | 端到端告警接线、回调隔离、配置别名测试 |
| `frontend/src/services/api.ts` | 适配器健康类型及 list/enable/disable API |
| `frontend/src/App.tsx` | 健康看板导航、路由和页面入口 |
| `frontend/src/adapter-health.tsx` | 新增适配器健康列表与手动启停页面 |

任务包黑名单文件未修改；工作区中原有的日报前端、`daily_digest.py`、IDE/UI 压缩包等用户改动均未纳入本阶段。

## 2. 验收条件逐条证据

| # | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | `MetricsRegistry.alert_engine` 可由 bootstrap 注入 | PASS | `meter.py:24`、`bootstrap.py:281`；定向测试通过 |
| 2 | 发布成功/失败分别发送 `publish_failure=0.0/1.0` | PASS | `meter.py:85`；`test_meter.py::test_metrics_registry_notifies_publish_failure_ratio_samples` |
| 3 | LLM 调用发送 `llm_latency` 样本 | PASS | `meter.py:92`；`test_metrics_registry_notifies_llm_latency` |
| 4 | `record_error()` 增加计数并发送 `error_count=1.0` | PASS | `meter.py:95-98`；`test_metrics_registry_records_errors_and_query_timing` |
| 5 | 查询按阈值发送 `slow_query=0.0/1.0` | PASS | `meter.py:100-105`、`infra/db.py:258-260`；同上测试及完整回归 |
| 6 | 发布器异常同时记录发布失败和通用错误 | PASS | `services/publishing.py:68-69`；全量发布服务测试通过 |
| 7 | 快/慢查询均进入 `record_query_timing`，旧 registry 有回退 | PASS | `infra/db.py:251-276`；`tests/infra/test_slow_query_logging.py` 通过 |
| 8 | bootstrap 将 MetricsRegistry 与 AlertEngine 接通 | PASS | `bootstrap.py:278-282` |
| 9 | 配置 `alert_targets` 时注册 PublisherAlertCallback | PASS | `bootstrap.py:317-325`；回调实现见 `publisher_alert_callback.py:14` |
| 10 | 发布失败比例可触发 AlertEngine callback | PASS | `test_alert_wiring.py::test_publish_ratio_reaches_callback` |
| 11 | 告警发布器按目标隔离失败 | PASS | `publisher_alert_callback.py:30-41`；`test_publisher_alert_callback_isolates_target_failures` |
| 12 | `ALERT_TARGETS` 与 `MULTISCRIBE_ALERT_TARGETS` 均可配置 | PASS | `config.py:368-372`；`test_alert_targets_support_both_environment_aliases` |
| 13 | 前端显示适配器 ID、失败数、启停状态、状态/错误/时间 | PASS | `frontend/src/adapter-health.tsx:37-38` |
| 14 | 前端启用/停用操作调用对应 API 并刷新 | PASS | `frontend/src/services/api.ts:306-310`、`adapter-health.tsx:28-35` |
| 15 | 全量 pytest、ruff、mypy 和前端构建通过 | PASS | 见第 3 节原始输出 |

## 3. 测试与质量门禁

### 定向告警测试

命令：

```text
.venv\Scripts\python.exe -m pytest tests/observability/test_meter.py tests/observability/test_alert_wiring.py tests/observability/test_alert_rules.py -v -p no:cacheprovider --basetemp .pytest-tmp-p43
```

原始结果：`14 passed in 0.23s`。

### ruff

```text
.venv\Scripts\python.exe -m ruff check .
All checks passed!
```

```text
.venv\Scripts\python.exe -m ruff format --check .
311 files already formatted
```

### mypy

```text
.venv\Scripts\python.exe -m mypy src
Success: no issues found in 165 source files
```

### 全量非 e2e 测试

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p43-full
482 passed, 4 deselected, 1 warning in 36.44s
```

### 前端构建

```text
cd frontend
npm run build
✓ built in 2.89s
```

构建输出包含既有的 Google Fonts 离线解析 warning，字体 URL 保留为运行时解析；TypeScript、Vite 构建均成功。

## 4. 设计说明、风险与取舍

- `publish_failure` 和 `slow_query` 使用每次调用的 0/1 样本，满足现有 ratio 规则的分母语义；Prometheus 仍保留原有计数和直方图输出。
- `infra/db.py` 优先使用新 `record_query_timing`，旧测试/部署 registry 仍可通过 `record_slow_query` 或 `_record_counter` 回退，不改变 SQLite 数据结构。
- `PublisherAlertCallback` 只发送规则、指标、阈值、描述和时间，不发送 prompt、凭据或工具结果正文；每个目标独立捕获异常。
- 当前告警回调沿用 `AlertEngine` 的异步调度和现有规则，未新增去重/持久化；同一规则在窗口内重复触发的抑制属于后续运营治理工作。
- `error_count` 当前在发布器直接失败路径记录，Agent 内部错误仍由既有事件/日志链路处理，避免越过本阶段 whitelist 修改 executor。
- 健康看板复用现有 CSS 数据行布局，未修改用户正在调整的日报样式；在窄屏下依赖已有 `.data-row` 响应式规则换行。

## 5. BLOCKED

无。

## 6. 后续建议

后续可为告警增加冷却/去重、告警历史持久化和前端告警记录页；同时可将 `error_count` 扩展到更多明确的用户可见失败边界。

## 7. 自评

本阶段满足 P43 任务包的实现、测试和质量门禁要求，建议提交规划层复审。
