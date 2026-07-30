# P52-D 发布历史分页 Review

## 交付结论

P52-D 已完成。发布历史接口现在支持 `limit` + `offset` 分页，并返回 `records`、`total`、`limit`、`offset`、`has_more`；控制台发布记录页按 50 条一页展示页码和总数，支持上一页/下一页并在边界禁用按钮。

## 改动范围

- `src/multiscribe_agent/core/publish_history.py`
  - `query()` 新增 offset，SQL 使用 `LIMIT ? OFFSET ?`。
  - 提取 `_build_filters()`，统一 query/count 的 publisher、时间和 digest_date 过滤。
  - 新增 `count()`，返回同过滤条件下的记录总数。
- `src/multiscribe_agent/api/routes/publish_history.py`
  - 新增 `offset` 查询参数。
  - 返回结构化分页对象，`has_more` 使用 `offset + len(records) < total` 计算。
- `frontend/src/services/api.ts`
  - 新增 `PublishHistoryResponse` 类型。
  - `publishHistoryApi.list(options?)` 支持可选 `limit`/`offset`，无参数仍使用 50/0 默认值。
- `frontend/src/shared/ui.tsx`
  - PublishingPage 管理 offset，按页重新请求并展示「第 X / Y 页（共 N 条）」。
  - 上一页/下一页使用 lucide 图标并按边界禁用。
- `frontend/src/styles.css`
  - 新增 `.pagination-row` 和 `.pagination-info` 样式。
- `tests/test_publish_history.py`
  - 将既有 API 断言从旧数组契约更新为新分页对象的 `records` 字段；测试场景本身未改变。

## 验收证据

- `frontend/npm run lint`：通过。
- `frontend/npm run build`：通过；TypeScript 和 Vite 构建成功。构建仍有既存远程字体离线解析提示及 bundle size 提示。
- `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p52d`：`602 passed, 6 deselected, 1 warning`。
- `.venv/Scripts/python.exe -m ruff check .`：通过。
- `.venv/Scripts/python.exe -m ruff format --check .`：`364 files already formatted`。
- `.venv/Scripts/python.exe -m mypy src`：`Success: no issues found in 187 source files`。
- 分页请求的 offset、count 和 has_more 逻辑已在同一服务过滤器构建路径中接线；前端唯一 `publishHistoryApi.list` 调用点已完成适配。

## 风险与边界

1. 当前采用 offset 分页，数据量达到万级后深 offset 可能比 cursor 分页慢；按任务包约束暂不引入 cursor。
2. 发布历史页面尚未执行浏览器自动化/手工视觉验收；建议在 UI 回审时验证第一页上一页禁用、最后一页下一页禁用，以及翻页请求参数变化。
3. `count(*)` 与列表查询是两个请求内的独立 SQL，在高并发写入时总数与当前页可能存在瞬时差异，这是 offset 分页的既有取舍。

## 提交边界

本阶段源码、测试契约和 Review 一并提交，不推送 GitHub。P32/P33/P50 既有 Review 修改保持原样，未纳入本阶段提交。
