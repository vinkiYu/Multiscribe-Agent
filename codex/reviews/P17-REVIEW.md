# Review: P17-记忆系统

**执行包**：`docs/phases/P17-记忆系统.md`
**完成日期**：2026-07-19
**执行者**：Codex

## 1. 范围核对

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/memory/**` | 新增 | 专属仓储、偏好、提取、检索和服务 |
| `src/multiscribe_agent/api/routes/memory.py` | 新增 | JWT 保护的 7 个 Memory API |
| `src/multiscribe_agent/knowledge/kb_service.py` | 修改 | P16 文档块到 P17 兼容 memory 记录的迁移 |
| `src/multiscribe_agent/bootstrap.py` | 修改 | MemoryService 注入、配置默认值、可选 LLM 分类器 |
| `src/multiscribe_agent/app.py` | 修改 | 注册 memory router |
| `src/multiscribe_agent/config.py` | 修改 | memory 默认阈值和推送时间 |
| `tests/memory/**` | 新增 | 11 项仓储、服务、提取、LLM 分类和 API 测试 |

所有实现改动均位于 P17 白名单；未修改 `domain/models.py`、`infra/db.py`、`entity_json.py`、`api/deps.py`、`api/security.py` 或 daily digest pipeline。

## 2. 验收条件逐条对照

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| 1 | `save()` SHA-256 去重 | ✅ | `test_save_deduplicates_by_url_and_content`、`test_save_batch_counts_only_unique_entries` |
| 2 | 偏好持久化 | ✅ | `test_preferences_default_then_round_trip`、`test_preferences_reject_invalid_push_time` |
| 3 | 从发布历史提取 | ✅ | `test_extract_and_merge_and_move_document`；提取器支持可选 LLM JSON tag 分类并降级为规则 tag |
| 4 | KB 文档迁移 | ✅ | `test_extract_and_merge_and_move_document`；迁移记录包含 JSON tags/data/sha256 |
| 5 | preferences GET/PUT JWT API | ✅ | `test_memory_api_crud_search_preferences_and_extract` 包含未认证 401 和 PUT/GET |
| 6 | entries CRUD/search JWT API | ✅ | 同一 API 测试覆盖 POST/GET/search/DELETE |
| 7 | extract API | ✅ | 同一 API 测试覆盖 POST `/api/memory/extract` |
| 8 | 至少 10 个测试 | ✅ | `tests/memory`: `11 passed` |
| 9 | 全量质量门绿 | ❌ | ruff/format/mypy 通过；全量 pytest 为 `229 passed, 3 failed, 4 deselected`，见风险 |
| 10 | 既有 200 测试无回归 | ❌ | 同上，失败来自 P16 可选运行时测试 |

## 3. 测试与质量门

```text
.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
200 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 119 source files

.venv\Scripts\python.exe -m pytest tests/memory -q -p no:cacheprovider
11 passed in 0.90s

.venv\Scripts\python.exe -m pytest tests/memory tests/mcp tests/skills -q -p no:cacheprovider --basetemp .pytest-tmp-final
33 passed in 0.90s

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-all
229 passed, 3 failed, 4 deselected in 25.64s
```

## 4. 详细任务完成情况

- **仓储与去重**：`MemoryCategoryRepository` 直接读写 `memory_categories`；`MemoryEntryRepository` 将 sha256、类别、条目元数据存入既有 JSON 列，并复用既有 FTS5 trigger。
- **偏好与提取**：偏好持久化为 `user-preferences` 分类；发布历史提取按 source 频率计算 importance，默认规则 tag 可被可用 LLM 的 JSON tag 结果增强。
- **服务/API**：`MemoryService` 统一 CRUD、搜索、提取与 KB 迁移；路由受既有 JWT 依赖保护。
- **P16 数据流**：`KBService.move_to_memory()` 现在写入 P17 可反序列化记录并对内容 hash 去重。

## 5. 规范符合性自检

- [x] 全量类型注解，`mypy src` 通过。
- [x] DB I/O 均为 async；文件/LLM 可选路径不执行真实网络测试。
- [x] 无硬编码密钥；分类失败只记录异常类型。
- [x] Domain/API 鉴权/DB schema 黑名单未修改。

## 6. 风险、遗留与取舍

- **阻塞风险**：全量 pytest 失败 3 项，均在 P16 范围：`tests/knowledge/test_api_kb.py`、`test_document_processor.py`、`test_embedding_service.py`。本机 `uv sync` 后 `sentence-transformers`/`pypdf` 可用，原测试把运行时缺失当作前提，导致尝试写 HuggingFace 模型缓存和无效 PDF 被底层库解析。相关实现和既有测试不在 P17 白名单，未擅自修改。
- **取舍**：LLM tags 是 best-effort，默认无 credential 时仅使用稳定规则 tags，避免启动时网络调用。
- **未做**：没有修改 P16 embedding/PDF 可选运行时策略；需要独立 P16 修复包后再解除全量门禁。

## 7. BLOCKED 项

- **阻塞点**：P17 不能声明完成，因为 P17 执行 prompt 要求全量 pytest 全绿；当前为 `229 passed, 3 failed, 4 deselected`。
- **需要决策**：安排 P16 回归包，明确可选 embedding/PDF 运行时的测试策略后重跑全量门禁。

## 8. 自评

- 我认为本包满足功能验收，但**不满足**任务包的全量质量门完成定义：❌
