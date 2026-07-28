# Review: `P34-调度幂等分布式锁`

**执行包**：`docs/phases/P34-调度幂等分布式锁.md`
**完成日期**：2026-07-28
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `pyproject.toml` | 修改 | 增加 `redis>=5.0,<6` 主依赖。 |
| `uv.lock` | 修改 | 锁定 Redis 5.3.1 及项目依赖关系。 |
| `src/multiscribe_agent/config.py` | 修改 | 新增 Redis URL、锁 TTL、strict mode 和配置层保真重建。 |
| `src/multiscribe_agent/infra/redis_client.py` | 新增 | Redis 异步客户端懒加载单例与关闭生命周期。 |
| `.env.example` | 修改 | 增加 Redis 与调度锁中文/英文配置说明。 |
| `src/multiscribe_agent/services/scheduler_lock.py` | 新增 | `SchedulerLock` 协议、Redis SET NX EX 锁、Lua owner-token 释放和 NoOp 实现。 |
| `src/multiscribe_agent/services/scheduler.py` | 修改 | 在 `execute_task` 统一接入锁、skipped/error/strict fallback 和 finally 释放。 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 组装 Redis 锁并在 reload/close 释放 Redis 客户端。 |
| `src/multiscribe_agent/domain/models.py` | 修改 | TaskLog 文档补充 skipped 语义，并放行实际存在的 status Literal 校验。 |
| `tests/infra/test_redis_client.py` | 新增 | Redis 配置、懒加载、关闭测试。 |
| `tests/services/test_scheduler_lock.py` | 新增 | NX、TTL、owner-token、strict/unavailable 测试。 |
| `tests/services/test_scheduler.py` | 修改 | 调度并发、释放、strict/relaxed、run_now 入口测试。 |
| `tests/test_config.py` | 修改 | `MULTISCRIBE_` 调度锁配置覆盖测试。 |
| `codex/reviews/P34-REVIEW.md` | 新增 | 本阶段 Review。 |

### 1.2 白名单合规性

- [x] 业务代码和测试均在 P34 白名单内；`uv.lock` 属于全局依赖可复现授权。
- [x] 未修改 schedules API、CLI、Agent/pipeline/workflow、采集发布、LLM、frontend、DB schema。
- [x] Review 文件按执行 Prompt 要求显式加入，未纳入用户其他工作区改动。

工作区中既有且未触碰的变更包括 frontend、`daily_digest.py`、`src.zip`、`UI/`、`.tmp-pytest/` 等。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | 同一 `(task_id, run_date)` 第二次执行记 skipped 且不调用 callback | ✅ | `test_lock_busy_is_skipped_without_calling_callback`：callback 次数为 1，日志包含 skipped。锁 key 见 `services/scheduler.py:131-136`。 |
| 2 | 正常完成后释放锁，当天再次触发可执行 | ✅ | `test_released_lock_allows_next_run_and_run_now_uses_same_guard`：两次 callback、两次 release 均通过。 |
| 3 | Redis 不可达 + strict=True 记 error 且不执行 | ✅ | `test_unavailable_lock_strict_mode_records_error_without_callback` 通过；`_try_acquire` 将连接异常转为 unavailable。 |
| 4 | Redis 不可达 + strict=False 告警并放行 | ✅ | `test_unavailable_lock_relaxed_mode_warns_and_runs` 通过；执行器仅在 `allow_without_lock=True` 时继续。 |
| 5 | cron/run_now/CLI 共用同一锁边界 | ✅ | 所有入口最终调用 `execute_task`；`test_released_lock_allows_next_run_and_run_now_uses_same_guard` 覆盖直接调度路径与 `run_now`，CLI 源码入口已核对为同一方法。 |
| 6 | redis 主依赖可安装 | ✅ | `pyproject.toml` 与 `uv.lock` 均含 `redis>=5.0,<6`；环境导入版本为 `5.3.1`。 |
| 7 | 三项配置支持 `MULTISCRIBE_` env 覆盖 | ✅ | `test_environment_overrides_scheduler_lock_settings` 断言 URL、TTL、strict mode。 |
| 8 | Lua 释放脚本不误删其他 owner 的锁 | ✅ | `test_redis_lock_uses_nx_and_release_only_deletes_own_token` 先用 stale token 释放并断言 key 仍在，再用真实 token 删除。 |
| 9 | 全量 pytest、ruff、mypy | ⚠️ | 全量 pytest 与 mypy 通过；P34 白名单 ruff/format 通过。无范围 `ruff check .`/`format --check .` 被既有 `.tmp-pytest`、`.pytest-tmp` 生成文件及用户修改的 `src/multiscribe_agent/api/routes/settings.py` 干扰，未擅自清理或修改。详见第 3 节。 |

## 3. 测试与质量门

### 3.1 定向测试

```text
============================= 21 passed in 0.56s =============================
```

覆盖 `tests/services/test_scheduler.py`、`tests/services/test_scheduler_lock.py`、`tests/infra/test_redis_client.py`、`tests/test_config.py`。

### 3.2 全量 pytest

```text
434 passed, 4 deselected, 1 warning in 39.14s
```

警告为现有 Starlette `TestClient` 与 httpx 的弃用提示；无 P34 测试失败。

### 3.3 P34 文件 `ruff check`

```text
All checks passed!
```

### 3.4 P34 文件 `ruff format --check`

```text
10 files already formatted
```

### 3.5 `mypy src`

```text
Success: no issues found in 160 source files
```

### 3.6 无范围全局 ruff 的阻塞证据

```text
E401/I001/E702/W292 ... .tmp-pytest\...\plugin.py
I001 ... src\multiscribe_agent\api\routes\settings.py
Found 32 errors.
19 files would be reformatted, 306 files already formatted
```

这些路径均不是 P34 改动；用户已有临时测试产物和 API 文件保持不变。

## 4. 详细任务完成情况

- **T1**：`SystemSettings` 增加 `redis_url`、`scheduler_lock_ttl_seconds`、`scheduler_lock_strict_mode`，Redis 客户端只在首次使用时构造，并由 `close_redis()` 释放。新增依赖已锁定。
- **T2**：`RedisSchedulerLock.acquire()` 使用 `SET NX EX`，生成随机 owner token；`release()` 使用 Lua 比对 token 后删除。`SchedulerService.execute_task()` 在唯一入口按 UTC 日期生成 `multiscribe:scheduler:lock:{task_id}:{run_date}`，busy 写 skipped，strict Redis 不可达写 error，relaxed 放行，持锁生命周期使用 finally。
- **配置层保真修复**：由于当前用户 `.env` 已配置自定义模型/目标，原 `ConfigService` 的 `model_validate(model_dump())` 会重新读取 `.env` 覆盖显式 `base_settings`。在同一白名单配置文件中改为 `_env_file=None` 重建，确保测试/部署显式设置不被意外覆盖。
- **状态契约**：任务包假设 `status` 是普通字符串，但实际模型有 Literal 校验；按任务包“若有 status 枚举校验则放行 skipped”条件加入 Literal 值。

## 5. 规范符合性自检

- [x] 新增代码有类型注解与公共 docstring。
- [x] Redis I/O 使用 async API；无真实 Redis 测试连接。
- [x] Redis 失败仅记录异常类型和 strict 状态，不记录 URL、token 或凭据。
- [x] 锁释放失败告警不影响业务回调错误状态。
- [x] 无 DB schema、API、CLI 或 Agent 反向依赖改动。

## 6. 新增依赖

| 包 | 版本约束 | 用途 |
| :--- | :--- | :--- |
| `redis` | `>=5.0,<6` | Redis asyncio 客户端与分布式调度锁。 |

## 7. 风险、遗留与取舍

- **风险**：默认 strict mode 下 Redis 不可达会拒绝日报执行，可能造成漏推；这是任务包明确的“重复推送比漏推更严重”决策，运营可用 `SCHEDULER_LOCK_STRICT_MODE=false` 逃生。
- **风险**：锁粒度固定为 UTC 日；未来一天多次日报需要扩展 key 粒度。
- **取舍**：直接构造 `SchedulerService` 时使用 NoOp 锁以保持既有单元测试/调用兼容；生产组合根始终注入 Redis 锁。
- **遗留**：全局静态命令仍受工作区用户已有临时目录和 API 文件影响；本阶段没有删除、格式化或提交它们。
- **未做的事**：未修改 SQLite schema、publish_history 唯一约束、API/CLI 路由、跨天去重或采集并发。

## 8. BLOCKED 项

- **阻塞点**：无代码实现阻塞；无范围全局 ruff 的工作区污染未能在不触碰用户文件的前提下清除。
- **已等待**：无。

## 9. 对后续包的提示

- `task_log.status="skipped"` 已成为稳定语义，运营看板应与 error 分开统计。
- P35 可直接复用 `SchedulerLock` 协议；跨天去重与 Redis 锁不共享 SQLite 状态。

## 10. 自评

- 我认为本包核心实现和验收测试满足 P34；✅
- 全局 ruff 的外部工作区阻塞已诚实记录，待用户清理既有临时目录和 API 改动后可重跑无范围静态命令。
