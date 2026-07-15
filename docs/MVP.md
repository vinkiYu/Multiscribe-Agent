# MVP 边界定义

> 目标：用最短路径跑通"每日抓取 → AI 精选 → 多端推送"主链路，验证架构与 Harness/Loop 设计。

## 1. MVP 必须具备的能力（对应 P0–P13）

| # | 能力 | 包 |
| :--- | :--- | :--- |
| 1 | 工程基线：pyproject、src layout、ruff/mypy/pytest、pre-commit、CLI 入口 | P0 |
| 2 | 配置管理（Settings 三层合并）+ 核心领域模型 | P1 |
| 3 | SQLite DB + 仓储（KV/JSON/SourceData/TaskLog）+ FTS5 | P2 |
| 4 | LLM Provider（OpenAI + Anthropic，tool calling + 流式） | P3 |
| 5 | Agent Harness：ReAct 循环 + 事件流 + HarnessContext（窗口管理） | P4 |
| 6 | 插件骨架：四类基类 + 注册中心 + 自动发现 | P5 |
| 7 | RSS 适配器（真实抓取 → UnifiedData 入库） | P6 |
| 8 | 飞书机器人推送（Webhook + 卡片 + 签名） | P7 |
| 9 | 企业微信机器人推送（Webhook + Markdown） | P8 |
| 10 | 调度器（APScheduler，热重载，task_logs） | P9 |
| 11 | DAG 工作流引擎（拓扑+并行+嵌套+环检测） | P10 |
| 12 | 每日推送流水线（抓取→去重→AI精选+Loop自评→渲染→fanout） | P11 |
| 13 | FastAPI 骨架 + JWT 认证 + 手动触发 + structlog | P12 |
| - | MVP 收尾：e2e 真实推送、README、Docker、.env.example | P13 |

## 2. MVP 非目标（明确延后）

- 知识库、记忆系统（→ P16/P17）
- Web 前端（→ P20，MVP 用 API + CLI）
- 评估框架（→ P21）
- Interop 互操作层（→ P22）
- MCP 客户端（→ P18）
- Skill 系统（→ P19）
- Follow/GitHub Trending/AI 搜索适配器（→ P14，MVP 先用 RSS）
- GitHub/RSS/公众号发布（→ P15，MVP 先用飞书/企微推送）
- 完整 OTel（→ P23，MVP 仅 structlog）
- 向量检索（→ P16，MVP 知识库尚未引入）

## 3. MVP 验收场景（第一条推送）

**端到端冒烟**：
1. `cp .env.example .env` 并填入：1 个 OpenAI 或 Anthropic key、1 个飞书机器人 webhook(+secret)、1 个企微机器人 webhook。
2. `uv run python -m multiscribe_agent serve` 启动。
3. 配置一个 RSS 源（如 Hacker News）。
4. 手动触发「每日推送」任务（CLI 或 API）。
5. **预期**：
   - RSS 抓取成功，source_data 入库（可见 task_log）。
   - AI 对条目打分精选 top-5，生成中文摘要。
   - 飞书群收到一张含 5 条精选的交互卡片（标题+摘要+链接）。
   - 企业微信群收到一份 Markdown 精选列表。
   - Loop 自评节点至少跑一轮（日志可见 self_assessment）。
6. 配置一个 cron 定时，次日同一时间自动推送成功。

**通过判据**：上述全链路在一次手动触发中跑通，且 task_logs 记录完整、structlog 无 ERROR。

## 4. MVP 质量基线

- `ruff check .` / `ruff format --check .` / `mypy src` 全绿。
- `pytest` 全绿，核心模块有单测（领域模型、仓储、DAG 引擎、飞书/企微渲染、流水线编排）。
- 外部 I/O（真实 RSS、真实 LLM、真实 webhook）用 `@pytest.mark.e2e` 标记，默认跳过，CI/手动时启用。

## 5. MVP 完成定义（Definition of Done）

- P0–P13 全部通过 review（六条标准）。
- 端到端冒烟场景复现成功。
- `README.md` 可指引新用户 10 分钟内跑通。
- `Dockerfile` + `docker-compose.yml` 可一键起服务。
