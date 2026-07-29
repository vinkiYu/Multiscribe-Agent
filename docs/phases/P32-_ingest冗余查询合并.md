# 执行包：P32 — _ingest 冗余查询安全合并

> **阶段**：阶段五（架构债清理）
> **目标**：合并 `_recent_daily_candidates` 中两次冗余的 `published_date` 查询为一次，去掉 1 次 DB 往返，零行为变化。
> **依赖**：P31.2（已通过）。
> **预估**：0.5 个工作日。
> **来源**：`docs/phases/ARCHITECTURE_OPTIMIZATION_REPORT.md` 债 5，经 ZCode 2026-07-30 代码核实后**收窄范围**。

---

## 一、债务诊断修正（基于真实代码核实）

原报告说"_ingest 三次冗余查询"，经核实**只对了一半**：

| 查询 | 字段 | 窗口 | 是否冗余 | 原因 |
|---|---|---|---|---|
| #1 `published_date` | `[end-1d, end]`（2 天） | **冗余** | 被 #2 完全包含 |
| #2 `published_date` | `[end-6d, end]`（7 天） | 保留 | 兜底窗口，非冗余 |
| #3 `fetched_at` | `[end-1d, end]`（2 天） | 不冗余 | 不同字段 + snapshot 适配器专用 |

**原报告方案（让 run_all 返回 items 省掉重查）有语义陷阱**：3 次查询读的是完整历史语料（含前几天的文章、7 天兜底窗口、跨天 snapshot 排名），而 run_all 只返回本次新增 items。直接替换会静默丢掉历史窗口旧文章。

**本包只做安全子修复**：合并 #1+#2 为一次查询 + Python 端按 `published_date >= start` 分类。

---

## 二、用户已确认的决策

1. **债 5**：只做安全子修复（合并查询），不改 run_all 签名，不动 dashboard/MCP/协议。
2. **债 3（ArtifactStore 持久化）暂缓**：checkpoint/resume 不存在，遵循报告原建议等该功能落地时一起做。**本包不含债 3。**

---

## 三、任务拆解（1 个子任务）

### T1：P32.1 — 合并两次 `published_date` 查询

**改动文件**：

| 文件 | 操作 | 说明 |
|---|---|---|
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | **修改** | `_recent_daily_candidates` 删除 query #1，把 #2 结果按 `published_date >= start` 分类为 recent/fallback |
| `tests/agents/pipelines/test_daily_digest.py` | **修改** | 更新 `FakeSourceDataRepository.entries_by_field` 用法，验证查询次数从 3 降到 2 |

**关键约束**：
- 保留 query #3（`fetched_at` + snapshot 适配器）不动
- 分类逻辑必须**严格保持原语义**：recent 优先赋值，fallback 用 `setdefault` 只填空

**实现要点**（`daily_digest.py:594-632`，基于 2026-07-30 HEAD）：

```python
async def _recent_daily_candidates(
    self, start: str, fallback_start: str, end: str
) -> list[SourceData]:
    """...（docstring 不变）..."""
    # 合并：7 天窗口查询一次，Python 端分类 recent(2 天) vs fallback(7 天)
    all_published = await self._source_data_repo.get_by_date_range(
        fallback_start, end, query_field="published_date"
    )
    fetched_items = await self._source_data_repo.get_by_date_range(
        start, end, query_field="fetched_at"
    )
    configured_adapters = set(self._config.adapter_ids)
    candidates: dict[str, SourceData] = {}
    for item in all_published:
        if item.adapter_name not in configured_adapters:
            continue
        if item.adapter_name in _SNAPSHOT_ADAPTER_IDS:
            continue  # snapshot 适配器由 fetched_items 提供
        if item.published_date and item.published_date >= start:
            # 2 天窗口内 → recent（优先赋值，覆盖任何已存在）
            candidates[item.id] = self._with_digest_freshness(item, "recent")
        else:
            # 7 天兜底窗口 → fallback（只填空，不覆盖 recent）
            candidates.setdefault(item.id, self._with_digest_freshness(item, "fallback"))
    for item in fetched_items:
        if (
            item.adapter_name in configured_adapters
            and item.adapter_name in _SNAPSHOT_ADAPTER_IDS
        ):
            candidates[item.id] = self._with_digest_freshness(item, "snapshot")
    return list(candidates.values())
```

**语义等价性证明**：
- 原 query #1（2 天）结果 ⊆ query #2（7 天）结果（窗口包含关系）
- 原 recent 用 `candidates[id] = ...`（赋值），fallback 用 `setdefault`（填空）
- 合并后：遍历 #2 全集，`published_date >= start` 的等价原 #1 → 赋值 recent；其余 → setdefault fallback
- snapshot 适配器在 published 循环中跳过（原逻辑里 #1/#2 也会进 candidates，但 #3 会用 `candidates[id] =` 覆盖——合并后直接跳过更干净，等价）
- **结果集完全相同**

---

## 四、白名单与黑名单

### 白名单（可改文件，共 2 个）

```
src/multiscribe_agent/agents/pipelines/daily_digest.py     [T1]
tests/agents/pipelines/test_daily_digest.py                [T1]
docs/phases/P32-_ingest冗余查询合并.md                      [本任务包文档]
```

### 黑名单（禁止改动）

- `src/multiscribe_agent/services/ingestion.py`（不改 run_all/run_single 签名）
- `src/multiscribe_agent/api/routes/dashboard.py`（不改 /ingest API）
- `src/multiscribe_agent/mcp/tools/rss_tools.py`（不改 fetch_rss）
- `src/multiscribe_agent/agents/pipelines/daily_digest.py` 的 `IngestionRunner` Protocol（不改）
- `src/multiscribe_agent/agents/artifacts.py`（债 3 不在本包）
- 其余黑名单同 P31.x（workflow/、executor.py、reflector.py、domain/models.py、llm/providers/、api/、frontend/）

---

## 五、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | `_recent_daily_candidates` 现在只发 2 次 DB 查询（原 3 次）| `test_recent_daily_candidates_uses_two_queries` |
| 2 | recent 标签仍只出现在 2 天窗口内的文章 | `test_recent_label_confined_to_two_day_window` |
| 3 | fallback 标签出现在 2-7 天窗口的文章（且不覆盖 recent）| `test_fallback_label_fills_gaps_without_overwriting_recent` |
| 4 | snapshot 标签仍只出现在 fetched_at 查询的 github_trending | `test_snapshot_label_unchanged` |
| 5 | 合并前后候选集完全相同（回归验证）| 现有 daily_digest 全部测试无变化通过 |
| 6 | 全量 pytest + ruff + mypy 通过 | 原始输出 |

---

## 六、测试与质量门

```bash
.venv\Scripts\python.exe -m pytest tests/agents/pipelines/test_daily_digest.py \
    -v -p no:cacheprovider --basetemp .pytest-tmp-p32

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m ruff format --check src tests
.venv\Scripts\python.exe -m mypy src
```

---

## 七、完成定义

- [ ] 白名单 2 个文件修改 + 1 个文档创建
- [ ] 6 条验收条件全部通过
- [ ] 全量 pytest 无回归（预期 583，0 新增或仅查询次数断言新增）
- [ ] ruff / mypy 全绿
- [ ] `codex/reviews/P32-REVIEW.md` 填写完毕

---

## 八、风险与取舍

1. **只去 1 次查询而非 3→1**：query #3（fetched_at）查的是不同字段不同适配器，无法合并。本次净收益是 1 次 DB 往返，不是 2 次。
2. **不解决债务报告原方案**：让 run_all 返回 items 省掉重查——那会改变语义（丢历史窗口）且有爆炸半径（dashboard/MCP/协议）。本包明确不做。
3. **`published_date` 为空的边界**：合并后若 `item.published_date` 为 None（snapshot 类无发布时间），归类为 fallback——但这类在原逻辑里也走 fallback 路径（#2 的 setdefault），等价。且 snapshot 适配器在 published 循环中被显式跳过，无影响。
4. **债 3 暂缓**：ArtifactStore 持久化遵循报告原建议，等 checkpoint/resume 落地时一起做。本包不含。

---

## 九、文件清单

```
src/multiscribe_agent/agents/pipelines/daily_digest.py     [修改: T1]
tests/agents/pipelines/test_daily_digest.py                [修改: T1]
docs/phases/P32-_ingest冗余查询合并.md                      [本任务包文档]
```