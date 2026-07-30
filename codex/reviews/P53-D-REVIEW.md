# P53-D 性能优化 Review

## 实现摘要

- `SourceDataRepository.save_batch()` 不再执行两次全表 `COUNT(*)`。改为按本批次 ID 查询已存在记录，保留批量 upsert，并按本批次去重后的新 ID 返回新增数。
- 新增 `SourceDataRepository.get_recent_candidates()`，使用一个 `published_date OR fetched_at` 查询返回日报候选；`_recent_daily_candidates()` 在真实仓储上使用单查询结果复现近期、回退和快照的原有筛选语义，并为旧仓储/测试替身保留双查询兼容路径。
- SQLite `executemany()` 的 SQL 审计从每个参数集一次写入改为每批一个审计事件，聚合记录绑定参数数量，消除 N 次审计 INSERT 和数据库往返。

## 验收证据

- `source_data.py` 已无针对 `source_data` 的 `COUNT(*)` 查询；数据库初始化中的 FTS 回填计数不属于 `save_batch()`。
- `db.py` 的 `executemany()` 不再循环调用 `_audit_write()`。
- 新增数、重复 upsert、日报候选和审计回归均通过现有测试。

## 测试记录

```text
pytest tests/infra/test_repositories.py tests/agents/pipelines/test_daily_digest.py tests/observability/test_sql_audit.py -q
50 passed

pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p53d-full
624 passed, 6 deselected, 1 warning

ruff check .
All checks passed!

ruff format --check .
372 files already formatted

mypy src
Success: no issues found in 190 source files
```

## 风险与边界

- 新增数计算需要先查询本批次 ID；批次超过 SQLite 变量上限时按 500 个 ID 分块查询，仍避免全表扫描，但极大批次会产生多个小查询。
- 批量审计现在按批次生成一条聚合审计记录，不再保留每条参数集独立的审计行；SQL 语句、操作类型和总绑定参数数量仍保留，适合性能审计，但若未来需要逐条审计应增加原生 `record_batch()` 接口和批量 `executemany` 写入。
- 真实仓储使用单查询路径，旧的仅实现 `get_by_date_range()` 的替身会走兼容双查询路径；这不影响生产数据库性能或结果。
- 测试过程中出现一次 OpenTelemetry console exporter 在测试输出流关闭后的既有 `ValueError`，不影响测试结果。

## 提交范围

本阶段仅涉及：

- `src/multiscribe_agent/infra/repositories/source_data.py`
- `src/multiscribe_agent/agents/pipelines/daily_digest.py`
- `src/multiscribe_agent/infra/db.py`
- `codex/reviews/P53-D-REVIEW.md`

