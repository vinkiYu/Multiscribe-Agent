# Review: P32 — `_ingest` 冗余查询安全合并

**执行包**：`docs/phases/P32-_ingest冗余查询合并.md`
**完成日期**：2026-07-30
**执行者**：Codex
**结论**：通过，建议交 ZCode 复审

## 1. 范围核对

本阶段仅修改白名单内的两个代码文件：

| 文件 | 变更 |
| --- | --- |
| `src/multiscribe_agent/agents/pipelines/daily_digest.py` | 合并两个 `published_date` 查询，并在 Python 端分类 freshness |
| `tests/agents/pipelines/test_daily_digest.py` | 增加查询次数、recent/fallback 优先级和 snapshot 回归测试 |

未修改任务包黑名单文件、运行时配置、数据库 schema、依赖或 API 契约。

## 2. 验收条件

| # | 验收条件 | 状态 | 证据 |
| --- | --- | --- | --- |
| 1 | `_recent_daily_candidates` 由 3 次 DB 查询降为 2 次 | 通过 | `daily_digest.py:608-613`；`test_recent_daily_candidates_uses_two_queries`（`test_daily_digest.py:846`）断言字段顺序与宽窗口边界 |
| 2 | recent 仅出现在两天窗口 | 通过 | `daily_digest.py:621` 使用 `published_date >= start`；`test_recent_label_confined_to_two_day_window`（`test_daily_digest.py:873`） |
| 3 | fallback 填补 2-7 天窗口且不覆盖 recent | 通过 | `daily_digest.py:627` 使用 `setdefault`；`test_fallback_label_fills_gaps_without_overwriting_recent`（`test_daily_digest.py:898`）覆盖同 ID 重叠顺序 |
| 4 | snapshot 仍只从 `fetched_at` 查询进入 | 通过 | `daily_digest.py:619` 跳过 published snapshot，`daily_digest.py:628-631` 保留 fetched 查询；`test_snapshot_label_unchanged`（`test_daily_digest.py:923`） |
| 5 | 候选集行为无回归 | 通过 | 现有 daily digest 全套测试与全量 pytest 均通过 |
| 6 | 全量 pytest、ruff、format、mypy 通过 | 通过 | 见第 3 节原始输出 |

## 3. 测试与质量门

### 定向测试

```text
42 passed in 0.68s
```

命令：

```text
.venv\Scripts\python.exe -m pytest tests/agents/pipelines/test_daily_digest.py -q -p no:cacheprovider --basetemp .pytest-tmp-p32-final-target
```

### Ruff

```text
All checks passed!
```

命令：`.venv\Scripts\python.exe -m ruff check src tests`

### Format

```text
353 files already formatted
```

命令：`.venv\Scripts\python.exe -m ruff format --check src tests`

### Mypy

```text
Success: no issues found in 182 source files
```

命令：`.venv\Scripts\python.exe -m mypy src`

### 全量测试

使用本地模型缓存离线运行，避免知识库测试联网下载模型：

```text
587 passed, 6 deselected, 1 warning in 22.29s
```

命令：

```text
$env:HF_HUB_OFFLINE='1'; .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p32-full-rerun
```

唯一 warning 为依赖侧 `StarletteDeprecationWarning`（`httpx` 与 Starlette TestClient 的兼容提示），与本阶段改动无关。

## 4. 实现摘要

原先分别查询两天和七天 `published_date` 窗口。现在一次查询七天宽窗口，再根据 `published_date >= start` 赋予 `recent`，否则用 `setdefault` 赋予 `fallback`，因此保留原先 recent 覆盖 fallback 的优先级。`github_trending` 等 snapshot 适配器在 published 查询中跳过，继续仅由两天 `fetched_at` 查询提供，避免改变快照语义。数据库接口、`IngestionRunner` 签名和外部 API 均未改变。

## 5. 风险与取舍

- 净收益是减少 1 次数据库往返（3 次降为 2 次），`fetched_at` 查询因字段和 snapshot 语义不同无法合并。
- 仍使用仓储返回的日期字符串进行 ISO 时间比较；现有数据由统一 UTC ISO 格式写入，保持原实现行为。
- OTel console exporter 在部分 pytest 进程关闭输出流后可能打印 `ValueError: I/O operation on closed file`，属于现有测试基础设施噪声，不影响断言和退出码。
- 未实施任务包明确排除的 `run_all` 返回 items、ArtifactStore 持久化或其他架构债清理。

## 6. 自评

本阶段满足任务包的范围、语义等价性、测试和质量门要求，结论为**通过**，等待 ZCode 复审。
