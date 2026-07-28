# Review: P39-适配器健康度与自动降级

**执行包**: `docs/phases/P39-适配器健康度与自动降级.md`
**完成日期**: 2026-07-29
**执行者**: Codex

## 1. 范围核对

本阶段实现 source adapter 的持久化健康状态、连续失败自动禁用、publisher 告警和手动恢复 API。

| 文件 | 操作 | 说明 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/infra/db.py` | 修改 | 创建 `adapter_health` 表和禁用索引，并接入 `init_db()` |
| `src/multiscribe_agent/core/adapter_health.py` | 新增 | `AdapterHealth` 状态模型及 SQLite repository |
| `src/multiscribe_agent/config.py` | 修改 | 增加失败阈值和告警 publisher 配置 |
| `.env.example` | 修改 | 增加两项配置示例及中英文注释 |
| `tests/core/test_adapter_health.py` | 新增 | schema、成功归零、阈值、幂等告警标记、手动禁用和环境配置测试 |
| `src/multiscribe_agent/services/ingestion.py` | 修改 | 采集成功/失败写健康状态，`run_all()` 跳过已禁用适配器 |
| `src/multiscribe_agent/services/adapter_health_alerter.py` | 新增 | 复用 publisher 发送纯文本告警并隔离告警失败 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 组合 health repository/alerter 并注入采集服务 |
| `src/multiscribe_agent/api/routes/adapter_health.py` | 新增 | 健康状态查询、手动 enable/disable API |
| `src/multiscribe_agent/app.py` | 修改 | 注册 adapter-health 路由 |
| `tests/services/test_ingestion.py` | 修改 | 自动禁用、跳过、恢复、告警和告警失败隔离测试 |
| `tests/api/test_adapter_health_routes.py` | 新增 | 查询、enable/disable 和认证测试 |

P39 禁止修改的 adapter 实现、publisher 实现、AlertEngine、agents、scheduler、publishing、LLM 和 frontend 文件均未修改。工作区中已有的 UI、README、logo、daily digest 等用户改动保持未提交。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `adapter_health` 表以 `adapter_id` 为 PK，保存失败数、禁用状态、状态、错误、运行时间 | PASS | `src/multiscribe_agent/infra/db.py:401`；`test_adapter_health_schema_and_success_reset` |
| 2 | 成功结果将连续失败归零并标记 success | PASS | `AdapterHealthRepository.record_result()`；core 测试 |
| 3 | 失败结果递增并保存截断错误 | PASS | `record_result()`；core 测试验证 200 字符上限 |
| 4 | 达到阈值后自动 disabled，且只产生一次 `just_disabled` | PASS | 阈值测试验证第 3 次为 true、第 4 次为 false |
| 5 | 已禁用适配器不重复告警 | PASS | repository 的 `just_disabled` 只在跨越阈值时设置；`run_all()` 跳过后续调用 |
| 6 | `run_all()` 在调度 callback 前跳过 disabled adapter 并返回 0 | PASS | `src/multiscribe_agent/services/ingestion.py:116-126`；ingestion 测试 |
| 7 | 手动 enable 清零并允许下一次 run_all 执行 | PASS | ingestion 测试先跳过、enable 后再次执行；API enable 测试 |
| 8 | 到达阈值时通过 publisher 收到含 adapter ID 和失败次数的纯文本告警 | PASS | `AdapterHealthAlerter`；`test_adapter_health_alerter_publishes_plain_text_without_blocking` |
| 9 | 告警 publisher 失败不阻塞采集主流程 | PASS | `IngestionService._alert_disabled()` 和告警失败测试 |
| 10 | 阈值和告警目标支持两种 env alias | PASS | `tests/core/test_adapter_health.py::test_adapter_health_settings_accept_prefixed_environment` |
| 11 | GET 健康列表 API | PASS | `GET /api/adapter-health`；API 测试 |
| 12 | POST enable/disable API | PASS | `POST /api/adapter-health/{id}/enable|disable`；API 测试 |
| 13 | 全量质量门通过 | PASS | 下节原始输出 |

## 3. 测试与质量门

### 3.1 定向测试

命令：

```text
.venv\Scripts\python.exe -m pytest tests/core/test_adapter_health.py tests/services/test_ingestion.py tests/api/test_adapter_health_routes.py -q -p no:cacheprovider --basetemp .pytest-tmp-p39-target
```

原始结果：`16 passed in 1.14s`

### 3.2 Ruff

命令：`.venv\Scripts\python.exe -m ruff check .`

原始结果：`All checks passed!`

### 3.3 格式检查

命令：`.venv\Scripts\python.exe -m ruff format --check .`

原始结果：`304 files already formatted`

### 3.4 Mypy

命令：`.venv\Scripts\python.exe -m mypy src`

原始结果：`Success: no issues found in 164 source files`

### 3.5 全量测试

命令：`.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p39-final`

原始结果：`459 passed, 4 deselected, 1 warning in 34.48s`

唯一 warning 是依赖栈中 Starlette/httpx 的弃用提示，不属于 P39 改动。

## 4. 实现摘要

- `AdapterHealthRepository` 使用 SQLite UPSERT 保证单适配器单行状态；成功清零，失败递增，首次跨越阈值时设置 `just_disabled=True`。
- `IngestionService.run_single()` 在原有 task log 成功/失败边界旁写健康状态；健康 DB 或告警异常只记录 warning，不改变采集结果。
- `run_all()` 在创建并发任务前读取 disabled 集合，已禁用适配器返回 0 且不构造/调用 adapter。
- `AdapterHealthAlerter` 复用已注册 publisher 和现有 publisher options，逐目标隔离失败。
- API 继承现有 console auth 和 CSRF 约束；enable 会清零失败 streak，disable 可为尚未运行过的 adapter 创建可查询行。

## 5. 风险、遗留与取舍

- `last_error` 按任务要求截断为 200 字符，但不做完整堆栈持久化；详细异常仍保留在 task log 中，运维需结合两处记录排查。
- 告警目标配置错误时只产生结构化 warning，健康状态仍可从 API 查询；不会因为告警不可达而阻塞日报采集。
- 自动降级只保护 `run_all()` 调度路径；手动 `run_single()` 仍可显式执行并继续记录健康结果，这是 dashboard 手工诊断所需的行为。
- 本阶段未接入前端健康看板、自动冷却恢复和 AlertEngine，这些均按任务包明确留给后续阶段。
- 未执行真实外部 RSS、AI Search 或 webhook e2e；单元/API 测试均使用内存数据库和 fake adapter/publisher。

## 6. 自评

P39 白名单内实现和测试均已完成，验收条件 13 项全部有证据，质量门全绿，无阻塞项，建议进入 ZCode 复审。
