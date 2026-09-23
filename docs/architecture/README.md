# 架构设计文档(当前有效)

> 当前有效的架构、模块所有权与依赖方向。任何 Agent 改码前应对照本文确认依赖方向。
> 术语以根目录 `CONTEXT.md` 为准;重大技术决策的"为什么"见 `docs/adr/`。
> **指令优先级**:安全规则(AGENTS.md §7)> 本文 > Spec/ADR > 当前代码与测试 > 验证证据 > 历史文档。
> 历史文档(如 `docs/phases/` 旧任务包)只用于解释"当时为什么这样做",不自动覆盖本文。

> **2026-09-22 修订说明**:原单文件 `docs/ARCHITECTURE.md` 与代码脱节(SQLite 单文件、向量/eval 标注"后置"),本版按当前代码事实重写,并迁移至 `docs/architecture/README.md`。

---

## 1. 技术栈(锁定)

| 维度 | 选型 | 备注 |
| :--- | :--- | :--- |
| 语言 | Python 3.12+ | src layout,`uv` + `pyproject.toml` |
| Web | FastAPI + Uvicorn | SSE 用 `sse-starlette` |
| LLM | LangChain(`langchain-openai/-anthropic/-google-genai`)+ LangGraph | provider 经中转(base_url)或官方端点 |
| 数据库 | **双方言**:SQLite + WAL(默认)/ PostgreSQL(`DB_DRIVER=postgres`) | 结构化列 + JSON blob;无正式迁移框架,`CREATE TABLE IF NOT EXISTS` 幂等 |
| 全文检索 | SQLite FTS5(bm25)/ PostgreSQL tsvector | 方言差异收敛在 `knowledge/fts_query.py` + `infra/dialect.py` |
| 向量 | **`VectorStorePort` 协议**:SQLite→`sqlite-vec`;PostgreSQL→pgvector | embedding 默认 `BAAI/bge-small-zh-v1.5`(512 维,惰性加载);reranker 默认关闭 |
| 工作流 | 自研 DAG(Kahn 拓扑 + 批次并行 + 子工作流嵌套 + Loop 自评) | |
| Agent 执行 | 自研 Harness(ReAct 循环 + 滑窗上下文 + 工具压缩 + 反思重试) | MCP 经官方 Python SDK 接入 |
| 模板 | Jinja2 | prompt + 推送渲染 |
| 可观测 | `structlog`(结构化+脱敏)+ OpenTelemetry(metrics/tracer + 告警规则) | |
| 测试 | pytest + pytest-asyncio | 151+ 用例(eval 域含四层指标/并行/归档) |
| 质量 | ruff(lint+format)+ mypy(strict)+ pre-commit | 统一入口 `verify`(见 AGENTS.md §3) |

更换任何依赖须经决策者批准,并记 ADR(`docs/adr/`)。

## 2. 模块清单与所有权

`src/multiscribe_agent/` 各包的**唯一所有权**——一个行为只有一个所有者:

| 包 | 所有职责 | 关键模块 | 禁止 |
| :--- | :--- | :--- | :--- |
| `domain/` | 领域模型(Pydantic)+ 仓储/服务 **Protocol** | `models.py`(30 模型)、`ports.py` | 导入任何其他包;出现 IO |
| `core/` | 交叉关注点 | `logging.py`(structlog+脱敏)、`security.py`(JWT/脱敏)、`errors.py`(领域异常)、`telemetry.py` | 业务逻辑 |
| `config.py`(根) | Settings(pydantic-settings,含 AliasChoices 环境别名) | — | 绕过 Settings 直读 os.environ(脚本入口 os.environ 覆写除外) |
| `infra/` | 持久化实现:双方言 db、连接池、repositories(source_data/kv/task_log/api_key/memory)、postgres 子系统 | `db.py`、`dialect.py`、`repositories/`、`postgres/` | 反向依赖 agents/api;直接被上层 new(须经 ServiceContext/bootstrap 装配) |
| `llm/` | Provider 抽象 + 实现 + usage 归一 | `provider.py`、`providers/openai.py`(trust_env=False) | 持有业务状态 |
| `agents/` | Harness、DAG workflow 引擎、daily_digest pipeline、ContextProvider、curator_judge | `executor.py`、`context.py`、`workflow/`、`pipelines/` | 直接写库(经仓储);绕过 Provider 直连 SDK |
| `plugins/` | 四类插件(Adapter/Publisher/Storage/Tool)+ 注册发现 + 审批边界 | `base.py`、`registry.py`、`discovery.py`、`builtin/`、`security.py` | custom 插件未审计入主进程 |
| `knowledge/` | 知识库:摄取(切分/去重)、RAG 索引落库、VectorStorePort、embedding | `kb_service.py`、`vector_store.py`、`embedding_service.py` | 依赖 agents/api/memory(检索协议层保持单向);旧 Retriever 已在 P66.6 删除 |
| `rag/` | P66 统一 RAG 契约与运行时检索:KnowledgeDocument/Chunk、RetrievedEvidence、RetrievalScope、RagService、BM25/向量融合与可选 reranker | `models.py`、`ports.py`、`service.py`、`bm25.py`、`dense.py` | 对外只暴露 RagService;数据库和具体向量方言藏在适配层 |
| `memory/` | 长期记忆、用户偏好、chat 会话、digest 上下文 | `memory_service.py`、`preference_store.py`、`retriever.py` | — |
| `services/` | 应用服务:采集编排、candidate_filter、chat_service、interop(对外 API key) | `ingestion.py`、`chat_service.py` | 跳过 domain 模型传裸 dict |
| `eval/` | 评测体系:curation benchmark(P/R/F1)、四层指标 schema、安全门、trace、ledger、drift、week pipeline | `curation_benchmark.py`、`metrics_schema.py`、`safety_gate.py`、`orchestrator/` | 评测逻辑散落 scripts |
| `api/` | FastAPI 路由(薄)+ SSE | `routes/`(24 路由) | 业务逻辑、直查 SQL |
| `mcp/`、`skills/`、`renderers/`、`observability/` | MCP 配置注册、技能条目、渲染器(飞书/企微/通用)、OTel tracer/meter+告警规则 | — | — |
| `bootstrap.py`(根) | **组合根**:装配上述全部、调度注册、reload/close | — | 被其他包 import(单向:bootstrap → 所有) |

## 3. 依赖方向(强约束)

```
bootstrap(组合根) → 一切
api → services → agents/plugins → domain(模型+Protocol)
agents/plugins → llm / knowledge / memory / infra(经注入)
rag → (pydantic + stdlib only; P66.2+ 的适配器由 knowledge/infra 实现)
infra / llm / knowledge / memory → domain
domain → (pydantic + stdlib only)
eval → domain / llm(评测独立于生产链路,不反向注入)
```

禁止:

- `domain` 导入 infra/llm/agents/plugins/api(唯一零依赖层);
- 上层绕过 Protocol 直接依赖具体实现类型;
- `api` 路由内写业务规则或 SQL;
- 兄弟包深路径互探(只走包公开入口 `__init__`/主模块);
- `eval` 被生产链路反向依赖(评测是旁路)。

跨层功能:先改合同(domain 模型/Protocol),再分别改消费者;禁止用临时深层导入打通链路。

## 4. 核心数据流

### 4.1 Agent 执行流(ReAct + Harness)

```
API /api/agents/:id/run (SSE)
  → AgentExecutor.run(agent_id, input)
      → HarnessContext(系统提示 + 滑动窗口 + ContextProvider 注入 memory/knowledge)
      → 循环(默认 5 轮): provider.stream(messages, tools)
          tool_calls? → 执行(本地 Tool / MCP)→ tool_result 入栈
          否则       → final_content
      → Reflector 自评(可选,带重试上限)
```

### 4.2 每日推送流水线(DAG)

```
ingest → dedupe → curate(Loop: 自评收敛) → overview → fanout(飞书 ∥ 企微)
```

- 节点经 `input_map` 声明依赖,引擎自动建图;per-target 失败隔离。
- curate 使用 `CURATE_PROMPT`(agents/pipelines/prompts.py):硬拒规则 + 边界关键词 + 数量上限/下限;**该文件是生产与评测共用契约**(P57-F1 黑名单)。

### 4.3 混合检索(当前形态)

```
query → [FTS bm25 top-k (kb_chunks_fts / source_data_fts)]
      + [embedding → VectorStorePort.top_k]
      → RRF(K=60) 融合 → 可选 reranker → top-n
```

- 向量不可用时自动降级为纯 FTS(`KBCapabilities.degraded`),不报错中断。
- `RetrievalScope` 在 BM25、向量召回和最终证据回表时重复应用 user/agent/doc_type 边界；`SearchSourceDataTool` 和 KB API 均通过 RagService 进入该链路。旧 `knowledge/retriever.py` 与 KBService 内的 RRF 分支已在 P66.6 删除。

### 4.4 评测链路(P64)

```
source_data 表 → sample_curation_dataset.py → fixtures(100 池,带标注)
  → run_eval_curation.py → run_curation_benchmark(并行,Semaphore)
      → per-sample 计数(_SampleRun) → 四层指标聚合
      → 多维门禁(_check_and_write_baseline: 相对降幅+绝对上限+phase_f1)
          ├ 通过 → 归档旧 baseline → 覆盖写
          └ 拒绝 → rejected-run ledger → RegressionDetected
  → report md(结果/过程/效率/安全层) + traces(jsonl.gz)
  → WeekPipeline(周跑):collect→clean→bench→gate→analyze→feedback
```

## 5. 关键设计模式

- **端口与适配器**:domain 定义 Protocol,infra/knowledge/llm 实现;上层仅依赖 Protocol。
- **组合根单例**:ServiceContext 懒加载 + `reload()`(停调度/断 MCP/重建)+ `close()`。
- **事件流**:Agent/Workflow 用 async generator 产事件,API 转 SSE。
- **约定优于配置**:插件带 `metadata` 即自动发现。
- **门禁文化**:git pre-commit(格式/类型/测试)+ eval 多维回归门禁 + rejected ledger。

## 6. 数据库 Schema 概览

结构化表:`kv`(TTL)/ `source_data`(+FTS)/ `task_logs` / `agent_memories`(+FTS)/ `kb_documents`(+FTS)/ `kb_chunks`(+FTS)/ `kb_chunk_dedup` / `kb_categories` / `api_keys` / `chat_sessions` / `curation_evaluations` / `publish_history`
向量表:SQLite `kb_chunks_vec`(sqlite-vec)/ PostgreSQL `chunk_vectors`(pgvector)
JSON blob 表:`agents` / `skills` / `workflows` / `mcp_configs` / `schedules` / `kb_documents.data`

- 无正式迁移框架:`CREATE TABLE IF NOT EXISTS` 幂等 + 启动修复(running→interrupted、FTS 回填);Postgres 迁移见 `docs/phases/Stage6B-*` 与 `docs/postgres-migration-guide.md`。
- JSON blob 用于字段不固定实体(整体读写);结构化列用于需索引/FTS/向量检索的实体。

## 7. 认证与安全边界

- JWT(前端用户,Bearer/`?token=`)+ API Key(外部 AI,`X-API-Key`,SHA-256 存储,仅 `/api/ai/v1/*`)。
- 默认密码 `admin123`(未配 SYSTEM_PASSWORD 时),JWT 带 `must_change_password`。
- 脱敏:token/secret/password/key/cookie 在日志与 Interop 返回中掩码。
- `plugins/custom/` 是受信任加载路径(主进程内),入目录前必须人工审计;`sandbox.py` 尚未接入该路径。
- LLM 出站代理仅来自显式配置(`httpx` `trust_env=False`),不读机器级代理环境变量。

## 8. 前端

- `prototype/`:React 19 + Vite 单页(`multiscribe-prototype`),13 页;构建产物与 node_modules 不入库。
- 旧 console 前端已废弃;P58-P63 期间的 agents/chat/source-search/curation-quality 页面待在新前端重做(备份在仓库外 `prototype-console-backup-20260815/`)。

---

*Last Updated: 2026-09-22(按当前代码事实重写;后续架构变更须同步本文 + 相关 ADR)*
