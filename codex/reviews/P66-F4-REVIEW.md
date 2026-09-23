# Review: `P66.4-Scope与Context接入`

**执行包**：`docs/phases/P66.4-Scope与Context接入.md`
**完成日期**：2026-09-23
**执行者**：Codex
**分支**：`feature/p66-rag-pipeline`

**阶段提交**：

- `4fe5484 feat(rag): add admin ownership migration primitives`
- `4f4b90a feat(agent): connect scoped rag evidence to context`
- `77ce0ef test(rag): lock scoped retrieval regression`

## 1. 范围核对

| 文件路径 | 操作 | 用途 |
| :--- | :--- | :--- |
| `src/multiscribe_agent/config.py` | 修改 | 默认 RAG user 从 `default` 改为 `admin` |
| `src/multiscribe_agent/domain/models.py` | 修改 | `KBDocument.owner_user_id` 默认值与规范化校验 |
| `src/multiscribe_agent/knowledge/kb_service.py` | 修改 | KB 摄取接收并持久化 owner；`search()` 未修改 |
| `src/multiscribe_agent/rag/adapter.py` | 修改 | SourceData 默认 admin，KB 使用文档自身 owner |
| `src/multiscribe_agent/rag/migrations.py` | 新增 | 双方言、幂等的派生索引 owner 回填 |
| `src/multiscribe_agent/agents/context_provider.py` | 修改 | 新增结构化 Evidence 和 `RagContextProvider` |
| `src/multiscribe_agent/agents/executor.py` | 修改 | `user_id` 贯穿 run/run_result/stream 到 ContextProvider |
| `src/multiscribe_agent/api/routes/agents.py` | 修改 | JWT `sub` 注入 Agent 执行 scope |
| `src/multiscribe_agent/api/routes/knowledge.py` | 修改 | JWT `sub` 注入 KB 摄取 owner |
| `src/multiscribe_agent/bootstrap.py` | 修改 | RAG 服务、owner 迁移与旧 Provider 降级装配 |
| `scripts/eval_rag_baseline.py` | 修改 | 新路径默认评测 user 改为 admin |
| `tests/agents/*`、`tests/rag/*`、`tests/knowledge/test_api_kb.py` | 修改/新增 | Scope、Evidence、迁移、owner 和回归覆盖 |

范围核对结果：

- ✅ `knowledge/retriever.py`、`services/search_source_data.py` 零 diff。
- ✅ `kb_service.search()` 零 diff；该文件只改 `ingest_file/ingest_text` owner 写入。
- ✅ 未切换 `SearchSourceDataTool`，未改 embedding/reranker，未增加依赖。
- ✅ 未提交 `.env`、运行库或 `data/eval/reports`。

## 2. 验收条件

| # | 验收条件 | 状态 | 证据 |
| :--- | :--- | :--- | :--- |
| T1 | `RAG_DEFAULT_USER_ID` 默认 `admin` | ✅ | `SystemSettings.rag_default_user_id` 默认值已修改；`test_rag_default_user_is_admin` 通过，环境变量仍可覆盖。 |
| T2 | owner 回填幂等、无 default 残留、bootstrap fail-open | ✅ | 真实库首次回填 registry/chunks 各 4218 行，第二次各 0 行；回填后两表均为 `admin=4218`、`default=0`。`test_backfill_rag_owner_is_idempotent`、`test_bootstrap_owner_migration_is_fail_open` 通过。 |
| T3 | KBDocument owner + 摄取归属 | ✅ | 旧 JSON 缺字段时读取为 admin；新 API/Service 摄取持久化 JWT subject；`RagDocumentAdapter` 使用 `document.owner_user_id`。`test_legacy_kb_json_gets_admin_owner_by_default`、`test_kb_ingest_persists_owner_user_id`、API owner 断言通过。 |
| T4 | `RetrievedContext.evidence` additive + `RagContextProvider` | ✅ | Evidence 保留 title/url/source/scope；兼容 `knowledge` 文本格式；现有 Executor 继续注入 knowledge 字符串。`test_rag_context_provider_passes_user_and_agent_scope` 通过。 |
| T5 | user 硬隔离 + agent 软过滤接线 | ✅ | API JWT `sub` → Executor `user_id` → `RetrievalScope.user_id`；AgentDefinition.id → `RetrievalScope.agent_id`。`test_executor_automatically_injects_generic_retrieved_context` 和 Provider scope 捕获断言通过。 |
| T6 | 六类隔离/降级/迁移测试 | ✅ | P66.4 focused suite `37 passed`；user 双用户隔离、agent 结果子集、Provider 降级、空 user 回退、迁移幂等、KB owner 均有断言。 |
| T7 | 新路径冻结指标逐位不变 | ✅ | `data/eval/reports/rag-new_20260923-014716.md/.json`：overall Recall@5 `0.6500`、MRR `0.58125`、citation `1.0000`、semantic Recall@5 `0.1667`，与 P66.3 一致。 |
| 装配降级 | RAG 初始化失败时回落旧 Provider | ✅ | `_init_kb()` 将 RAG 建表/服务装配置于 best-effort 边界；`test_bootstrap_falls_back_when_rag_schema_init_fails` 验证 KB 仍可用且 `rag_service=None`。 |
| `del agent_id` 消失 | ContextProvider 不再丢弃 agent | ✅ | `rg -n "del agent_id" src/multiscribe_agent/agents/context_provider.py` 无输出。 |

## 3. 测试与质量门

### 3.1 统一验证入口

本机没有可用 `uv` 命令，使用项目 `.venv` 直接执行同一个 `verify` 入口：

```text
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:HAYSTACK_TELEMETRY_ENABLED='false'
.\.venv\Scripts\python.exe -m multiscribe_agent.verify
```

原始输出摘要：

```text
=== verify: ruff check src ===
All checks passed!
=== verify PASS: ruff check src ===

=== verify: ruff format --check src tests ===
458 files already formatted
=== verify PASS: ruff format --check src tests ===

=== verify: mypy src ===
Success: no issues found in 239 source files
=== verify PASS: mypy src ===

763 passed, 3 skipped, 11 deselected, 2 warnings in 33.33s
=== verify PASS: pytest (hermetic scope) ===

verify: ALL GREEN
```

两条 warning 为既有 Starlette/httpx deprecation 和项目根 `.pytest_cache` ACL；pytest 的 `tmp_path` 仍使用项目外唯一 basetemp，不影响结果。

### 3.2 专项与 API 回归

```text
tests/rag + context provider/context optimization:
37 passed in 3.13s

knowledge API + agents/workflows + KB service:
7 passed in 6.55s

knowledge API owner assertion:
1 passed in 6.94s
```

### 3.3 真实回填

```text
before_registry= [('default', 4218)]
before_chunks= [('default', 4218)]
first= RagOwnerMigrationReport(registry_updated=4218, chunks_updated=4218, already_marked=False)
second= RagOwnerMigrationReport(registry_updated=0, chunks_updated=0, already_marked=True)
after_registry= [('admin', 4218)]
after_chunks= [('admin', 4218)]
registry_default= 0
chunks_default= 0
```

### 3.4 RAG 指标回归

```text
report=data\eval\reports\rag-new_20260923-014716.md
json=data\eval\reports\rag-new_20260923-014716.json
overall Recall@5=0.65
overall MRR=0.58125
overall citation_coverage=1.0
semantic Recall@5=0.16666666666666666
```

## 4. 实现说明

- owner 回填只执行 `WHERE user_id='default'`，非 legacy owner 不受影响；marker 用于审计，但每次仍安全执行精确 UPDATE，从而可处理 marker 创建后才出现的旧数据。
- `kb_documents.data` 不批量重写；旧 JSON 由 Pydantic 默认 admin 惰性兼容，新写入自然带 owner。
- `RagContextProvider` 同时返回结构化 `evidence` 和带来源的兼容 `knowledge` 字符串；RAG 异常返回 `rag:degraded`，且日志不写 query、正文或异常消息。
- API 请求使用 JWT `sub`；CLI、调度和其他非 API 调用传 `None`，由 Provider 使用配置中的默认 admin。
- RAG schema 或迁移失败均为 fail-open：保留旧 KB 服务和 `MemoryKnowledgeContextProvider`，不阻断启动。

## 5. 风险与取舍

- `agent_id` 现在会真实缩小结果集合；历史索引行若没有 `agent_id`，Agent scoped 查询不会命中这些通用行。这符合当前 `RetrievalScope` 的软过滤定义，但后续若需要“Agent 专属 + 用户通用”并集语义，应由新任务包明确修改 SQL 规则。
- bootstrap 使用 RAG Provider 时不再同时调用旧 `MemoryKnowledgeContextProvider`；这是任务包规定的换芯行为。长期记忆若需要与 RAG Evidence 并行融合，应另做组合 Provider，而不是在本包扩大范围。
- 评测首条查询包含本地 embedding 冷启动，单条约 4.45 秒；稳态 overall p95 为 45.10ms。质量指标无回退，冷启动优化不属于本包。
- PostgreSQL owner UPDATE 和 tsvector 路径通过双方言 abstraction 与类型门禁，但本轮没有启动真实 PostgreSQL 实例做集成验证。
- Git hook 环境仍因 Windows PATH/cache/联网限制不可用；三次提交前后均独立执行 ruff、mypy、专项测试和最终 `verify`。

## 6. BLOCKED 项

无。

## 7. 自评

- P66.4 计划内实现、真实回填、Scope 接线、指标回归与受控质量门均已完成：✅。
- 建议交 ZCode 复审后进入 P66.5；当前未 push、未合并。
