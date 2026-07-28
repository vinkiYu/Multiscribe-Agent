# Review: `P35-跨天去重与候选排序`

**执行包**：`docs/phases/P35-跨天去重与候选排序.md`  
**完成日期**：2026-07-28  
**执行者**：Codex

## 1. 范围核对

### 1.1 实际改动文件清单

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/infra/db.py` | 修改 | 创建 `pushed_content` 表、复合主键和 `pushed_at` 索引，并接入 `init_db` 迁移链。 |
| `src/multiscribe_agent/core/pushed_content.py` | 新增 | 提供 `add`、`recent_hashes`、`recent_urls` 仓储边界。 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | 组装仓储并注入每日推送流水线。 |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | 修改 | 接入跨天 hash/URL 去重、fallback 时间排序和成功发布后的指纹写入。 |
| `tests/core/test_pushed_content.py` | 新增 | 覆盖表结构、索引、幂等写入和日期边界。 |
| `tests/agents/pipelines/test_daily_digest.py` | 修改 | 覆盖跨天排除、窗口配置、fallback 排序和发布成功/失败写入闭环。 |
| `codex/reviews/P35-REVIEW.md` | 新增 | 本阶段执行证据与风险报告。 |

### 1.2 白名单合规性

- [x] 业务代码和测试均落在 P35 白名单内。
- [x] 未修改 P35 黑名单中的 services、其他 agents、publish_history、API、LLM、frontend、config 或 Redis 文件。
- [x] 工作区中既有的 `frontend/*`、`docs/phases/README.md`、资源压缩包、临时测试目录及其他用户改动均未纳入本阶段变更。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `pushed_content` 存在复合主键 `(content_hash, digest_date)` 与 `pushed_at` 索引 | ✅ | `src/multiscribe_agent/infra/db.py:359-376`；`test_pushed_content_schema_has_composite_primary_key_and_index`。 |
| 2 | 重复 `(content_hash, digest_date)` 写入幂等 | ✅ | `PushedContentRepository.add` 使用 `INSERT OR IGNORE`；`test_add_is_idempotent_for_same_hash_and_digest_date`。 |
| 3 | `recent_hashes/urls` 按 `since_date` 包含边界 | ✅ | 仓储 SQL 使用 `digest_date >= ?`；`test_recent_identities_use_inclusive_since_date_boundary`。 |
| 4 | 最近窗口内已推送 hash 候选被排除 | ✅ | `daily_digest.py:450-477`；`test_daily_digest_excludes_recent_pushed_hash_and_url_and_keeps_new_candidate`。 |
| 5 | URL 命中但标题/描述变化时仍被排除 | ✅ | 同一测试预置稳定 URL，并验证候选不进入 curator prompt。 |
| 6 | hash/URL 均不匹配的候选保留 | ✅ | 同一测试验证 `three` 仍进入 prompt 并最终保留。 |
| 7 | fallback 候选按 `published_date` 降序截断 | ✅ | `_sort_fallback_candidates` 位于 `daily_digest.py:191-194`；`test_daily_digest_fallback_candidates_are_sorted_newest_first`。 |
| 8 | 至少一个发布目标成功时写入全部 `DigestItem` | ✅ | `daily_digest.py:592-613`；`test_daily_digest_records_all_items_after_one_successful_publisher`。 |
| 9 | 所有发布目标失败时不写入 | ✅ | `test_daily_digest_does_not_record_items_when_all_publishers_fail`。 |
| 10 | 排除窗口等于 `fetch_days` 且可配置 | ✅ | `_recent_pushed_identities` 按 `run_date - fetch_days + 1` 计算边界；`test_daily_digest_fetch_days_controls_cross_day_exclusion_window`。 |
| 11 | 全量测试与静态质量门通过 | ✅ | 第 3 节原始输出。 |

## 3. 测试与质量门

### 3.1 定向测试

```text
============================= 24 passed in 0.94s =============================
```

命令：

```text
.\.venv\Scripts\python.exe -m pytest tests/core/test_pushed_content.py tests/agents/pipelines/test_daily_digest.py -v -p no:cacheprovider --basetemp .pytest-tmp-p35
```

### 3.2 全量 pytest

```text
442 passed, 4 deselected, 1 warning in 35.77s
```

命令：

```text
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p35-full
```

警告为现有 Starlette `TestClient` 与 httpx 的弃用提示。首次不指定 `--basetemp` 的运行受 Windows 默认临时目录权限影响，出现 74 个 fixture `PermissionError`；使用仓库内临时目录复跑后全量通过，未改动任何用户文件。

### 3.3 P35 白名单 Ruff

```text
All checks passed!
```

命令：

```text
.\.venv\Scripts\python.exe -m ruff check src/multiscribe_agent/infra/db.py src/multiscribe_agent/core/pushed_content.py src/multiscribe_agent/bootstrap.py src/multiscribe_agent/agents/pipelines/daily_digest.py tests/core/test_pushed_content.py tests/agents/pipelines/test_daily_digest.py
```

### 3.4 P35 格式检查

```text
2 files already formatted
```

命令：

```text
.\.venv\Scripts\python.exe -m ruff format --check src/multiscribe_agent/core/pushed_content.py tests/core/test_pushed_content.py
```

### 3.5 `mypy src`

```text
Success: no issues found in 161 source files
```

## 4. 详细任务完成情况

- **T1：独立跨天指纹存储**：新增 SQLite 迁移与 `PushedContentRepository`。URL 写入和读取均使用 `strip/rstrip/casefold` 规范化，查询边界为包含 `since_date`，且复合主键允许同一内容跨不同日期再次推送。
- **T2：每日流水线接入**：`_dedupe` 变为异步 DAG 节点，先加载 `fetch_days` 窗口内 hash/URL，再叠加批次内去重；保留的原始候选 hash 按规范化 URL缓存，用于发布后抵抗 LLM 改写标题/摘要造成的 hash 漂移。fallback 分支按发布时间降序，发布至少一个目标成功才为全部选中项落指纹。
- **组合根**：`ServiceContext` 在数据库初始化后创建仓储，并把它传入每日推送任务，旧构造调用因参数追加在末尾保持兼容。

## 5. 规范符合性自检

- [x] 新增代码有类型注解和公共 docstring。
- [x] 数据库 I/O 使用现有异步 `Database` 边界；无同步阻塞 I/O。
- [x] URL、hash、标题写入不包含凭据；日志未增加正文或密钥输出。
- [x] 新仓储位于 core，依赖 infra 数据库边界，未修改 domain 或黑名单模块。
- [x] 测试使用内存 SQLite、fake publisher/repository，无真实网络调用。

## 6. 新增依赖

无。未修改 `pyproject.toml` 或 `uv.lock`。

## 7. 风险、遗留与取舍

- **风险**：content hash 的主来源是 `_dedupe` 阶段的 `UnifiedData.title + description`。若某个选中项无法在该阶段建立 URL 映射，发布时才回退到 `DigestItem.title + summary`；稳定 URL 仍是跨天排除的主保险。
- **风险**：仓储查询将窗口内所有 hash/URL 读入内存 set。当前日报规模很小；若未来推送量显著增长，需要分页查询或按日期清理策略。
- **取舍**：没有复用现有 `publish_history`，避免其脱敏预览字段不能可靠支持去重，也保持发布结果与跨天候选身份的职责分离。
- **遗留**：本阶段没有实现来源权重或语义相关性排序；fallback 仅按发布时间排序，符合任务包范围。
- **未做的事**：未修改 API、发布器、调度器、LLM provider 或 SQLite 既有业务表。

## 8. BLOCKED 项

无。代码实现和验证未遇到需要决策者澄清的阻塞。

## 9. 对后续包的提示

- 后续如果支持多主题日报，`pushed_content` 需要增加主题维度，否则不同主题共享同一跨天排除集合。
- 后续如果需要按发布目标分别追踪成功状态，应在独立表扩展 `publisher_id`，不要改变当前“任一渠道成功即记录内容”的语义。
- `PushedContentRepository` 是独立 core 边界，可供后续清理任务或运营查询复用。

## 10. 自评

- 我认为本包满足 `P35-跨天去重与候选排序.md` 的完成定义：✅
- 代码已完成测试，已提交本地 commit；未推送到远端，等待决策者审结。
