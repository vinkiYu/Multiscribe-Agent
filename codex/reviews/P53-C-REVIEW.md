# P53-C Review: 数据源 FTS 搜索

## 结论

P53-C 已完成，建议提交 ZCode 复审。本阶段把已有的 SQLite FTS5 / PostgreSQL tsvector 搜索能力暴露为认证 HTTP 接口，并在控制台增加数据源搜索页面；未修改 `SourceDataRepository`、FTS 索引、jieba 分词或知识库/记忆页面。

## 变更摘要

- `src/multiscribe_agent/api/routes/source_data.py`
  - 新增认证路由 `GET /api/source-data/search`。
  - `q` 限制 200 字符，`limit` 限制 1-100；空白查询返回 400。
  - 复用 `context.source_data.search_fts()`，返回标题、URL、描述高亮、来源、分类和日期字段。
  - FTS5 非法 MATCH 表达式被隔离为 `[]`，不会返回 500。
- `src/multiscribe_agent/app.py`
  - 注册数据源搜索路由。仓库实际路由注册集中在 `app.py`，未创建任务包示例中不存在的 `api/__init__.py` router 对象。
- `frontend/src/services/api.ts`
  - 新增 `SourceData` 类型和 `sourceDataApi.search()`。
- `frontend/src/pages/source-search.tsx`
  - 新增关键词搜索、Enter 提交、加载/错误/空结果状态和结果列表。
  - 对后端 `<mark>` 高亮做安全解析，React 负责转义普通文本，不直接把原始描述整体注入 DOM。
- `frontend/src/App.tsx`、`styles.css`
  - 新增 `source-search` 导航入口、页面标题和搜索结果样式，支持窄屏布局。
- `tests/api/test_source_data_search.py`
  - 覆盖高亮结果、认证、空白查询和非法 FTS 表达式。
- `tests/infra/test_init_database_driver_dispatch.py` 与 `infra/db.py`
  - 同步 P53-B PostgreSQL `alert_history` 初始化后的 14 条 schema 顺序基线，并修正上一阶段遗留格式差异；不改变本阶段 FTS schema 行为。

## 验收证据

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| `GET /api/source-data/search` 返回 SourceData 投影 | 通过 | `tests/api/test_source_data_search.py::test_source_data_search_returns_highlighted_results` |
| 描述包含 `<mark>` 高亮 | 通过 | 同上，断言响应 description 包含 `<mark>` |
| 空白 query 返回 400 | 通过 | `test_source_data_search_handles_empty_and_invalid_fts_queries` |
| 非法 FTS 语法返回空数组 | 通过 | 同上 |
| 路由要求认证 | 通过 | `test_source_data_search_requires_authentication` |
| `sourceDataApi` 类型和调用参数正确 | 通过 | `frontend/src/services/api.ts`，`tsc -b` |
| 侧边栏入口和页面渲染 | 通过 | `frontend/src/App.tsx`、`source-search.tsx` |
| 无结果空状态和高亮视觉样式 | 通过 | `source-search.tsx`、`styles.css` |

## 测试记录

```text
.venv\Scripts\python.exe -m pytest tests/api/test_source_data_search.py -v -p no:cacheprovider --basetemp .pytest-tmp-p53c-target
3 passed

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p53c-full-final
624 passed, 6 deselected, 1 warning

.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
372 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 190 source files

cd frontend; npm run build
Build succeeded; Vite only reported existing remote font resolution and chunk-size warnings.

cd frontend; npm run lint
Passed
```

唯一 pytest warning 是 Starlette TestClient 与 httpx 的弃用提示，与本阶段改动无关。前端构建生成的 `frontend/dist` 文件未纳入提交。

## 风险与边界

1. 后端 FTS 结果的高亮由 SQLite `snippet()` 或 PostgreSQL `ts_headline()` 生成；前端仅解析 `<mark>`，其他 HTML 会被 React 当作文本转义，避免原始描述注入。
2. 非法 FTS 表达式统一返回空数组，便于用户搜索，但会把索引/数据库故障与“没有结果”区分开来的能力留给后续可观测性增强。
3. 查询只覆盖 `source_data`，不搜索 `daily_digest_archives.items`，因为后者没有 FTS 索引。
4. 当前页面没有搜索历史、分页或按来源/日期筛选；接口已经提供 bounded limit，后续可以增量扩展。
5. PostgreSQL schema 顺序测试的修正属于 P53-B 接线的过期断言同步，未改变既有 FTS SQL 或数据模型。

## 提交范围

本阶段提交应仅包含：

- `src/multiscribe_agent/api/routes/source_data.py`
- `src/multiscribe_agent/app.py`
- `frontend/src/services/api.ts`
- `frontend/src/pages/source-search.tsx`
- `frontend/src/styles.css`
- `frontend/src/App.tsx`
- `tests/api/test_source_data_search.py`
- `tests/infra/test_init_database_driver_dispatch.py`（P53-B 过期断言同步）
- `src/multiscribe_agent/infra/db.py`（P53-B 格式门禁修正）
- `codex/reviews/P53-C-REVIEW.md`

工作区中原有的 `P32/P33/P50` Review 修改未纳入本阶段提交。
