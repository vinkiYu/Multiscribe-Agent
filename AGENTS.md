# MultiscribeAgent — Agent 开发指南（强制首读）

> 本文是任何在本仓库中工作的 AI Agent（含 Codex 执行 Agent）的**强制首读**。
> 开工前必须完整阅读本文 + `docs/conventions/*`，再阅读所执行的 `docs/phases/Px-*.md`。

---

## 0. 角色与工作流（铁律）

| 角色 | 职责 | 红线 |
| :--- | :--- | :--- |
| **决策者（人）** | 目标、约束、优先级、最终判断 | 只拍板，不改码 |
| **规划（ZCode）** | 澄清需求、拆任务、定验收、做 review | 只出方案与判定，不直接改码 |
| **执行（Codex）** | 进库改码、跑测试、交结果、自报 review | **只按任务包执行，不自由发挥** |

**循环**：决策者定目标 → 规划拆任务包 → Codex 按包执行并产 review → 决策者把 review 发回规划 → 规划按六条标准判定放行/退回。

**Codex 六条红线**：
1. 只改当前 `Px-*.md` 的「可改范围（白名单）」内文件，禁动黑名单。
2. 开工前必读：`AGENTS.md` → 相关 `docs/conventions/*` → 当前 `Px-*.md`。
3. 测试是硬门：必须跑全部质量命令并贴**原始输出**，不过不得声称完成。
4. 完工必须按 `codex/REVIEW_TEMPLATE.md` 自报 review。
5. 遇歧义**停下问**，禁止在 review 里悄悄猜测实现。
6. 不硬编码任何密钥；日志不得泄露隐私。

---

## 1. 项目定位

MultiscribeAgent 是 PrismFlowAgent（TypeScript）的 **Python 重构版**。

- **核心**：声明式 Agent + 自研 DAG 工作流引擎 + 多模型（LangChain）+ 插件化采集/发布。
- **特色**：Harness Engineering（结构化上下文/规划/反思）、Loop Engineering（执行→评估→精炼收敛）、可观测性、评估框架。
- **新增**：飞书机器人、企业微信机器人推送端；每日资讯抓取 → AI 精选 → 多端推送流水线。

详见 `docs/PRD.md`。

## 2. 技术栈（锁定，不得擅自更换）

| 维度 | 选型 |
| :--- | :--- |
| 语言/运行时 | Python 3.12+ |
| 包管理 | `uv` + `pyproject.toml`（src layout） |
| Web 框架 | FastAPI + Uvicorn；SSE 用 `sse-starlette` |
| LLM 抽象 | LangChain（`langchain-openai`/`-anthropic`/`-google-genai`）+ LangGraph |
| 数据库 | SQLite + WAL；结构化列 + JSON blob |
| 全文检索 | SQLite FTS5（bm25） |
| 向量检索 | `sqlite-vec` + `sentence-transformers`（本地）/ 可选 API embedding |
| 工作流引擎 | 自研 DAG 拓扑排序（Kahn + 批次并行 + 子工作流嵌套） |
| MCP | `mcp` 官方 Python SDK |
| 模板 | Jinja2 |
| 可观测性 | `structlog`（结构化日志）+ OpenTelemetry（trace/metrics） |
| 测试 | pytest + pytest-asyncio |
| 质量 | ruff（lint+format）+ mypy（严格）+ pre-commit |

更换任何依赖须经决策者批准，并在本文件记录。

## 3. 常用命令

```bash
uv sync                          # 安装依赖（首次/拉取后）
uv run pytest                    # 跑全部测试
uv run pytest tests/path/ -q     # 跑指定测试
uv run ruff check .              # lint
uv run ruff format .             # 格式化
uv run mypy src                  # 类型检查
uv run python -m multiscribe_agent --version   # 版本
uv run python -m multiscribe_agent serve       # 启动 API
uv run python -m multiscribe_agent eval --dataset xxx --agent yyy  # 评估（后置）
```

**提交前必跑**：`ruff check . && ruff format --check . && mypy src && pytest`，全绿方可提交。

## 4. 目录结构

```
MultiscribeAgent-main/
├── AGENTS.md                   # 本文件（强制首读）
├── docs/
│   ├── PRD.md  MVP.md  ARCHITECTURE.md
│   ├── conventions/            # 编码规范、Plugin 契约（硬约束）
│   └── phases/                 # 分阶段任务包（Px-*.md）+ 进度看板
├── codex/
│   ├── EXEC_PROMPT.md          # Codex 总执行 prompt
│   └── REVIEW_TEMPLATE.md      # 完工自报模板
├── src/multiscribe_agent/
│   ├── api/                    # FastAPI 路由层（薄）
│   ├── core/                   # 交叉关注点：logging/security/errors/telemetry
│   ├── domain/                 # 领域模型（pydantic）+ 仓储接口（Port）
│   ├── infra/                  # db/repositories/embedding/file 持久化实现
│   ├── llm/                    # Provider 抽象 + 各家实现
│   ├── agents/                 # Harness + workflow engine + pipelines
│   ├── plugins/                # adapters/publishers/storages/tools + registries
│   ├── knowledge/              # 知识库 + 记忆（后置）
│   ├── observability/          # OTel tracer/meter
│   └── eval/                   # 评估框架（后置）
├── tests/                      # 镜像 src 结构
└── data/                       # 运行时数据（gitignore）
```

### 分层依赖方向（强约束）

```
api → agents/services → domain（模型/端口）
                ↘ plugins → domain
                ↘ infra（实现）→ domain
```

- **domain 层零外部依赖**（只有 pydantic + 标准库 + 仓储 Protocol），不导入 infra/plugins/agents。
- **infra 实现仓储接口**，不反向依赖 agents。
- **api 层最薄**，只组装调用，不含业务逻辑。

## 5. 代码规范（要点，详见 docs/conventions/coding-standards.md）

- **命名**：类 `PascalCase`；函数/变量 `snake_case`；常量 `UPPER_SNAKE`；文件 `snake_case.py`。
- **类型**：全量类型注解；`mypy --strict` 通过；禁用 `Any`（除非处理动态配置，且须注释说明）。
- **import**：标准库 → 第三方 → 本项目，分组空行；用 `from __future__ import annotations` 延迟求值。
- **异步**：I/O 全异步（`async def`）；不得在 async 中调用阻塞 I/O（必要时 `asyncio.to_thread`）。
- **错误处理**：`try/except` 包裹外部 I/O；用 `structlog` 记录；抛领域异常而非裸字符串。
- **日志**：用 `structlog`，结构化键值；不打印密钥/token/隐私。
- **测试**：每个公共函数/类有覆盖；用 `pytest-asyncio`；mock 外部 I/O，不打真实网络（除非 e2e 标记）。

## 6. Plugin 契约（要点，详见 docs/conventions/plugin-contract.md）

四类插件：**Adapter**（采集）/ **Publisher**（发布）/ **Storage**（存储）/ **Tool**（Agent 工具）。

- 每个插件类必须有 `metadata` 类属性（dataclass），含 `id/type/name/description/icon/config_fields`。
- `config_fields: list[ConfigField]`，ConfigField 支持 7 种 type + `scope`（adapter 级 / item 级）。
- 自动发现：扫描 `plugins/builtin/**` 与 `plugins/custom/**`，凡带 `metadata` 即注册。
- Tool 必须提供 JSON Schema `parameters`；handler 为 `async def`。

## 7. 安全准则

- **严禁**硬编码密钥、token、密码。配置走 `.env` + Settings + KV。
- 日志对敏感字段做脱敏（token/secret/password/key/cookie → 掩码）。
- `execute_command` 类工具必须有白名单/黑名单。
- 文件读写做路径穿越校验。

## 8. 阶段化重构记录区

> 每个 phase 通过后，规划在此追加一行。格式：`| Px | 名称 | 状态 | 通过日期 | 备注 |`

| Phase | 名称 | 状态 | 通过日期 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| P0 | 工程基线与规范 | 未开始 | — | — |

（其余见 `docs/phases/README.md` 看板）

## 9. Agent 操作流程（每次开工）

1. **读**：`AGENTS.md` → 相关 `docs/conventions/*` → 当前 `docs/phases/Px-*.md` → `codex/EXEC_PROMPT.md`。
2. **确认范围**：列出将改动的文件，与白名单/黑名单核对。
3. **改码**：遵循规范；增量提交。
4. **自测**：跑 `ruff check . && ruff format --check . && mypy src && pytest`，贴原始输出。
5. **自报 review**：按 `codex/REVIEW_TEMPLATE.md` 填写，逐条对照验收条件。
6. **遇阻**：BLOCKED 项写明原因，停下等指令，不猜。

---

*Last Updated: 2026-07-15*
