# 架构设计文档

> 技术架构、分层、端口与数据流。任何 Agent 改码前应对照本文确认依赖方向。

## 1. 技术栈（锁定）

| 维度 | 选型 | 备注 |
| :--- | :--- | :--- |
| 语言 | Python 3.12+ | |
| 包管理 | `uv` + `pyproject.toml` | src layout |
| Web | FastAPI + Uvicorn | SSE 用 `sse-starlette` |
| LLM | LangChain + LangGraph | provider: openai/anthropic/google/ollama |
| DB | SQLite + WAL | 单文件 |
| 全文检索 | SQLite FTS5（bm25） | |
| 向量 | `sqlite-vec` + `sentence-transformers` | 后置 |
| 工作流 | 自研 DAG（Kahn 拓扑 + 批次并行 + 嵌套） | |
| MCP | `mcp` Python SDK | 后置 |
| 模板 | Jinja2 | prompt + 推送渲染 |
| 可观测 | `structlog` + OpenTelemetry | |
| 测试 | pytest + pytest-asyncio | |
| 质量 | ruff + mypy(strict) + pre-commit | |

## 2. 分层架构与依赖方向

```
┌─────────────────────────────────────────────┐
│  api/        FastAPI 路由（最薄）             │
├─────────────────────────────────────────────┤
│  agents/     Harness + Workflow + Pipelines  │
│  plugins/    adapters/publishers/tools/storage│
├─────────────────────────────────────────────┤
│  domain/     模型(Pydantic) + 端口(Protocol)  │  ← 零外部依赖，依赖根
├─────────────────────────────────────────────┤
│  infra/      db / repositories / embedding   │
│  llm/        Provider 抽象 + 实现             │
│  core/       logging / security / errors     │
└─────────────────────────────────────────────┘
```

**强约束**：
- `domain` 不导入 `infra`/`llm`/`agents`/`plugins`/`api`。它只定义模型和仓储**接口**（Protocol）。
- `infra` 实现 `domain` 的端口接口，不反向依赖上层。
- `agents`/`plugins` 依赖 `domain`（模型/端口）和 `llm`/`infra`（实现），通过依赖注入接收。
- `api` 只组装调用，不含业务逻辑；所有业务在 `agents`/`plugins`/`infra`。
- 跨层通信一律走**领域模型**，不传原始 dict。

## 3. 核心目录与职责

### `src/multiscribe_agent/`

| 目录 | 职责 | 关键模块 |
| :--- | :--- | :--- |
| `domain/` | 领域模型 + 端口 | `models.py`（UnifiedData/AgentDefinition/Workflow...），`ports.py`（Repository Protocol） |
| `core/` | 交叉关注点 | `logging.py`(structlog), `security.py`(JWT/脱敏), `errors.py`(领域异常), `telemetry.py`(OTel) |
| `infra/` | 持久化实现 | `db.py`, `repositories/`(kv/json/source_data/task_log/api_key), `embedding.py`(后置) |
| `llm/` | LLM 抽象 | `provider.py`(Protocol+工厂), `providers/`(openai/anthropic/google/ollama) |
| `agents/` | 智能体与编排 | `context.py`(HarnessContext), `executor.py`(ReAct), `planner.py`, `reflector.py`, `workflow/`(DAG engine), `pipelines/`(daily_digest) |
| `plugins/` | 插件系统 | `base.py`(四基类), `registry.py`, `discovery.py`, `builtin/{adapters,publishers,storages,tools}/` |
| `knowledge/` | 知识库/记忆（后置） | `document_processor.py`, `retriever.py`(混合检索), `kb_service.py`, `memory_service.py` |
| `observability/` | OTel 初始化（后置完善） | `tracer.py`, `meter.py` |
| `eval/` | 评估框架（后置） | `dataset.py`, `evaluator.py`, `benchmark.py` |

## 4. 核心数据流

### 4.1 Agent 执行流（ReAct + Harness）

```
API /api/agents/:id/run (SSE)
  → AgentExecutor.run(agent_id, input)
      → HarnessContext 组装（系统提示 + 滑动窗口 + 注入记忆/知识）
      → 循环 (max_rounds, 默认5):
          provider.stream(messages, tools)  → 事件: content/tool_calls_delta
          有 tool_calls?
            ├─ 是: 执行工具(本地/MCP) → tool_result 事件 → 入栈 → 下一轮
            └─ 否: final_content 事件 → break
      → Reflector 自评（可选触发重试）
  → SSE 事件流推给客户端
```

### 4.2 每日推送流水线（DAG 工作流）

```
节点1 抓取(ingest)    → UnifiedData[]
节点2 去重(dedupe)     → sha256/url 去重
节点3 AI精选(curate)   → Agent 打分 + 摘要 → top-N  [Loop 节点: 自评不达标→重生成]
节点4 渲染(render)     → Jinja2 生成各端格式(飞书卡片/企微MD/通用HTML)
节点5 推送(fanout)     → 并行发往已配置端
```
- 节点间通过 `input_map` 声明数据依赖，引擎自动建图。
- 节点3 是 **Loop 节点**：`max_iterations` + `exit_condition`（LLM 自评），体现 Loop Engineering。

### 4.3 混合检索（后置）

```
query → [向量召回 top-k] + [FTS5 bm25 top-k] → RRF 融合 → (可选 LLM 重排) → top-n
```

## 5. 关键设计模式

- **端口与适配器**：`domain/ports.py` 定义仓储 Protocol；`infra/repositories/` 实现；上层依赖 Protocol，便于测试 mock。
- **策略门面**：KnowledgeBaseService/MemoryService 持多实现，配置切换（hierarchical vs sqlite）。
- **单例 + reload**：`ServiceContext` 懒加载服务，配置变更时 `reload()`（停调度器/断 MCP/重 init）。
- **事件流**：Agent/Workflow 用 `async generator` 产出事件，API 层转 SSE。
- **约定优于配置**：插件带 `metadata` 即自动发现注册。

## 6. 数据库 Schema 概览

结构化表：`kv`(TTL) / `commit_history` / `source_data`(+FTS5) / `task_logs` / `agent_memories`(+FTS5) / `kb_documents` / `kb_chunks`(+FTS5) / `api_keys` / `embeddings`(后置)
JSON blob 表：`agents` / `skills` / `workflows` / `mcp_configs` / `schedules`

- 无正式迁移框架，靠 `CREATE TABLE IF NOT EXISTS` 幂等 + 启动修复（running→interrupted、FTS 回填）。
- JSON blob 用于字段不固定的实体（整体读写）；结构化列用于需索引/FTS 的实体。

## 7. 认证

- JWT（前端用户）：登录签发，Bearer 或 `?token=`。
- API Key（外部 AI）：`X-API-Key`，仅 `/api/ai/v1/*`，SHA-256 hash 存储。
- 默认密码机制：未配 SYSTEM_PASSWORD 时用 `admin123`，JWT 带 `must_change_password`。
- 配置脱敏：token/secret/password/key/cookie 字段日志与 Interop 返回时掩码。
