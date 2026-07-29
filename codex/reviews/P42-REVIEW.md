# Review: P42-预览审核后续风险加固

执行包：`docs/phases/P42-预览审核后续风险加固.md`
完成日期：2026-07-29
执行者：Codex

## 1. 范围核对

本阶段补齐 P41 识别的两个风险：approve 并发重复 fan-out，以及 pending/rejected 归档被公开日报接口读取。

实际改动文件：

| 文件 | 操作 | 作用 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 暴露与 SchedulerService 共用的 `scheduler_lock` 实例 |
| `src/multiscribe_agent/api/routes/digest.py` | 修改 | approve 使用按日期 Redis 锁，处理 strict/relaxed 降级并保证 finally release |
| `src/multiscribe_agent/core/daily_digest_archive.py` | 修改 | `list/get` 增加向后兼容的 `published_only` 过滤参数 |
| `src/multiscribe_agent/api/routes/daily_news.py` | 修改 | 公共读取显式启用 `published_only=True` |
| `tests/api/test_digest_routes.py` | 修改 | 锁 key、TTL、释放、占用和 Redis 不可用分支测试 |
| `tests/core/test_daily_digest_archive.py` | 修改 | 归档过滤和兼容默认行为测试 |
| `tests/api/test_daily_news_routes.py` | 新增 | 公共日报隐藏 pending/rejected 测试 |
| `codex/reviews/P42-REVIEW.md` | 新增 | 本阶段 review |

未修改 P42 黑名单文件：`scheduler_lock.py`、`scheduler.py`、`daily_digest.py`、`infra/db.py`、`services/`、`llm/` 和前端目录。工作树中 P41 之前已有的前端/logo/压缩包及日报业务改动仍未纳入本阶段。

## 2. 验收条件逐条证据

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `ServiceContext.scheduler_lock` 在 init 后保存生产 Redis lock，并与 SchedulerService 复用同一实例 | 通过 | `src/multiscribe_agent/bootstrap.py:244,363-372` |
| 2 | approve 使用日期锁，第二个并发请求返回 409 | 通过 | `digest.py:48-57`；`test_approve_rejects_when_lock_is_held_or_unavailable_in_strict_mode` |
| 3 | approve 完成或异常后释放 owner token | 通过 | `digest.py:69-77`；`test_approve_uses_date_scoped_lock_and_releases_owner_token` |
| 4 | 锁 key 按日期隔离，TTL 为 300 秒 | 通过 | `digest.py:51`；测试断言 `multiscribe:digest:approve:2026-07-29` 和 `300` |
| 5 | Redis 不可用且 strict=true 时返回 409 | 通过 | `digest.py:52-58`；strict unavailable 测试 |
| 6 | Redis 不可用且 strict=false 时允许降级执行 | 通过 | `digest.py:52`；`test_approve_allows_lock_unavailable_when_configured_for_relaxed_mode` |
| 7 | `archive.list(published_only=True)` 排除 pending/rejected | 通过 | `daily_digest_archive.py:154-179`；归档过滤测试 |
| 8 | `archive.get(published_only=True)` 对 pending/rejected 返回 None | 通过 | `daily_digest_archive.py:103-128`；归档过滤测试 |
| 9 | `published_only=False` 默认保留旧的全量读取行为 | 通过 | `daily_digest_archive.py:107,158`；归档测试断言默认 list 返回 4 条 |
| 10 | `GET /api/daily-news` 不返回 pending/rejected | 通过 | `daily_news.py:28-31`；`test_public_daily_news_excludes_pending_and_rejected_archives` |
| 11 | public API 正常返回已发布日报 | 通过 | 同一 public route 测试断言 `approved` 和 `published` 两条记录可见 |
| 12 | 全量 pytest、ruff、format、mypy 通过 | 通过 | 见第 3 节原始输出 |

说明：`published_only=True` 将 `published` 和 `approved` 都视为公共可见终态。P41 的 `approved` 表示已审核并完成正式群发，若只过滤到 `published` 会导致审核通过的日报从公共页面消失，因此这里采用两个明确的公开状态。

## 3. 测试与质量门

### 3.1 定向测试

命令：

```text
.venv\Scripts\python.exe -m pytest tests/api/test_digest_routes.py tests/api/test_daily_news_routes.py tests/core/test_daily_digest_archive.py -v -p no:cacheprovider --basetemp .pytest-tmp-p42
```

原始结果：

```text
10 passed in 0.23s
```

### 3.2 `ruff check .`

```text
All checks passed!
```

### 3.3 `ruff format --check .`

```text
309 files already formatted
```

### 3.4 `mypy src`

```text
Success: no issues found in 164 source files
```

### 3.5 全量非 e2e 回归

命令：

```text
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p42-full
```

原始结果：

```text
476 passed, 4 deselected, 1 warning in 33.01s
```

唯一 warning 为既有 Starlette `httpx` deprecation warning；未执行真实 Redis、webhook 或 LLM e2e，P42 验收要求为本地 fake lock 和非 e2e 回归。

## 4. 实现摘要

- `ServiceContext` 在创建调度器时先构造一个 `RedisSchedulerLock`，保存到 `scheduler_lock`，再把同一对象传给 `SchedulerService`。
- approve 在读取归档前获取 `multiscribe:digest:approve:{date}` 租约；已占用或 strict 模式不可用均返回 409，relaxed 模式沿用现有 `allow_without_lock` 降级策略。
- approve 的 fan-out、状态迁移和 pushed-content 写入均位于 `try/finally` 保护范围，只有持有有效 owner token 时才 release。
- 归档 `list/get` 保留默认全量行为，同时支持 `published_only=True`；公共日报接口使用该参数，审核中和拒绝的内容不再出现在导航或按日期查询中。

## 5. 风险、遗留与取舍

- approve 锁 TTL 固定为 300 秒；如果极端慢的 webhook fan-out 超过 TTL，租约可能过期并允许第二个请求进入。后续可增加续租或按 publisher 超时上限校准 TTL。
- relaxed 模式在 Redis 不可用时仍允许审批，跨进程重复风险由部署配置承担；生产环境建议保持 strict 模式。
- approve 全部 publisher 失败时仍沿用 P41 行为标记 `approved`，未在 P42 扩展部分发布状态或失败重试。
- P42 不包含前端审核 UI、pending 超时自动处理和审批意见记录。

## 6. 自评

本阶段完成 P42 白名单内的锁复用、approve 并发保护、公共归档过滤和测试覆盖，12 条验收条件均有代码或测试证据，质量门和全量回归通过，可交由 ZCode 复审。
