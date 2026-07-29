# Review: P41-推送前预览审核

执行包：`docs/phases/P41-推送前预览审核.md`
完成日期：2026-07-29
执行者：Codex

## 1. 范围核对

本阶段实现了日报的“预览群先收、人工确认后正式群发”流程。实际纳入本阶段提交的文件如下：

| 文件 | 操作 | 作用 |
| :--- | :--- | :--- |
| `.env.example` | 修改 | 增加 `preview_mode` / `preview_targets` 的 schedule 配置示例 |
| `src/multiscribe_agent/infra/db.py` | 修改 | 为日报归档创建并迁移 `approval_status` 列 |
| `src/multiscribe_agent/core/daily_digest_archive.py` | 修改 | 持久化、读取和更新审核状态 |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | 修改 | 增加预览模式分支、归档状态和依赖注入 |
| `src/multiscribe_agent/api/routes/digest.py` | 修改 | 增加 approve/reject API 和目标解析 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 将归档仓储注入日报 pipeline |
| `tests/core/test_daily_digest_archive.py` | 新增 | 归档 schema、迁移和状态读写测试 |
| `tests/agents/pipelines/test_daily_digest.py` | 修改 | 默认模式回归和 preview-first 测试 |
| `tests/api/test_digest_routes.py` | 新增 | approve/reject API 测试 |
| `codex/reviews/P41-REVIEW.md` | 新增 | 本阶段交付 review |

P41 白名单外已有改动未纳入本提交：`docs/phases/README.md`、`frontend/`、`multiscribe-logo.svg`、`.idea/`、`UI/`、`frontend.v0.zip`、`src.zip`，以及 `daily_digest.py` 中此前已有的三处容错/文本清洗修复。

## 2. 验收条件逐条证据

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `daily_digest_archives` 含 `approval_status`，默认 `published`，兼容旧表 | 通过 | `src/multiscribe_agent/infra/db.py:387-405`；`tests/core/test_daily_digest_archive.py:test_archive_schema_and_approval_state_round_trip`、`test_archive_migration_adds_status_to_legacy_table` |
| 2 | `set_approval_status` / `get_approval_status` 读写正确 | 通过 | `src/multiscribe_agent/core/daily_digest_archive.py:116-138`；归档状态测试覆盖 `pending/approved/rejected/published` |
| 3 | `preview_mode=off` 保持原有全量发布行为 | 通过 | `src/multiscribe_agent/agents/pipelines/daily_digest.py:693-723`；原有端到端日报测试通过 |
| 4 | `preview_first` 只发送 `preview_targets`，归档为 `pending` | 通过 | `daily_digest.py:670-691`；`test_daily_digest_preview_first_only_publishes_review_targets` |
| 5 | approve 从归档重建 digest、正式群发并标记 `approved` | 通过 | `src/multiscribe_agent/api/routes/digest.py:40-56`；`test_approve_rebuilds_digest_excludes_preview_and_records_pushed_content` |
| 6 | approve 排除 `preview_targets`，预览群不重复接收 | 通过 | `digest.py:90-120`；API 测试断言正式调用目标仅为 `wecom_bot` |
| 7 | 非 `pending` approve 返回 409 | 通过 | `digest.py:72-87`；API 测试覆盖 `published` 状态 |
| 8 | 不存在的日期返回 404 | 通过 | `digest.py:80-81`；API 测试覆盖缺失日期 |
| 9 | reject 标记 `rejected` 且不调用 publisher | 通过 | `digest.py:59-69`；`test_reject_marks_pending_digest_without_fanout` |
| 10 | approve 成功后写入 `pushed_content` | 通过 | `digest.py:160-180`；API 测试断言记录已写入；仅在至少一个正式目标成功时写入 |
| 11 | schedule task 可配置预览字段 | 通过 | `DailyDigestConfig.from_mapping` 位于 `daily_digest.py:139-185`；配置解析测试覆盖 |
| 12 | 全量 pytest、ruff、format、mypy 通过 | 通过 | 见第 3 节原始输出 |

## 3. 测试与质量门

### 3.1 定向测试

命令：

```text
.venv\Scripts\python.exe -m pytest tests/core/test_daily_digest_archive.py tests/agents/pipelines/test_daily_digest.py tests/api/test_digest_routes.py -v -p no:cacheprovider --basetemp .pytest-tmp-p41
```

原始结果：

```text
30 passed in 0.30s
```

### 3.2 `ruff check .`

```text
All checks passed!
```

### 3.3 `ruff format --check .`

```text
308 files already formatted
```

### 3.4 `mypy src`

```text
Success: no issues found in 164 source files
```

### 3.5 全量非 e2e 回归

命令：

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p41-full
```

原始结果：

```text
471 passed, 4 deselected, 1 warning in 33.19s
```

未执行真实 webhook/LLM e2e；P41 的验收只要求本地 mock/单元测试，且总执行 prompt 默认跳过 e2e。定向测试进程退出时曾输出一次 OTel console exporter 对已关闭输出流的异常堆栈，但 pytest 退出码为 0；全量结果只包含既有的 Starlette `httpx` deprecation warning。

## 4. 实现摘要

- 归档状态采用 `published -> pending -> approved/rejected` 的显式状态字段，旧归档迁移后默认为 `published`。
- `preview_first` 在归档写入 `pending` 后只 fan-out 到审核目标，不写入 `pushed_content`；审核群的结果仍记录到发布历史，便于审计。
- approve 从归档快照无损重建 `CuratedDigest`，目标可按请求体、日报 schedule 配置或启用 publisher 推导，并去重、排除预览目标。
- reject 是终态操作，不触发任何正式发布。
- approve 正式发布至少一个目标成功后，按 P35 的 URL/内容哈希规则写入 `pushed_content`。

## 5. 风险、遗留与取舍

- 审核入口目前是 API，没有前端审核页面；运营方需要调用 `POST /api/digest/{date}/approve` 或 `reject`。
- approve 的目标解析会读取第一个匹配的 `daily_digest` schedule；多日报任务场景应在后续阶段增加 task id/date 绑定，避免配置歧义。
- approve 当前在 publisher 全部失败时仍将状态置为 `approved`，但不会写入 `pushed_content`；后续可增加 `approved/partially_published/publish_failed` 状态或失败重试策略。
- 公开 `GET /api/daily-news` 当前会读取归档中的 `pending` 内容；P41 白名单未要求修改该接口，因此若产品要求“审核通过前不可被公共页面看到”，需要后续增加 pending 过滤或鉴权。
- approve/reject API 未复用 P34 调度锁；多个管理员并发 approve 可能造成重复 fan-out，后续应增加按日期的审核幂等锁或原子状态迁移。
- P41 不包含 pending 超时自动处理、审批意见记录、多级审批和前端展示，这些属于后续产品范围。
- 本提交未包含工作树中用户已有的日报容错修复和前端资源改动。

## 6. 自评

本阶段满足 P41 任务包定义和 12 条验收条件，测试与质量门均通过，可交由 ZCode 复审。上述 API 审核界面、超时策略和全失败状态治理是明确的后续增强项，不影响本阶段核心预览审核闭环。
