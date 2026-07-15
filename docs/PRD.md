# PRD — MultiscribeAgent 产品需求文档

> 版本：v1.0 · 日期：2026-07-15 · 状态：已定稿（待 MVP 验证）

## 1. 背景

PrismFlowAgent（流光）是一个 TypeScript 全栈系统：多源信息聚合 + AI 智能体 + 多端分发。它工作良好但存在技术债：
- TypeScript 全栈维护成本高；插件无热加载；无 schema 迁移；前端耦合重。
- 检索靠纯 LLM 多阶段导航（慢、贵、不稳）。
- 浏览器自动化发布（小红书）本质脆弱。

本重构目标是把它**迁到 Python 生态**，做**功能取舍**，并系统性引入 **Harness Engineering** 与 **Loop Engineering**，同时**新增飞书/企业微信机器人推送**和**每日资讯抓取→AI精选→多端推送流水线**。

## 2. 用户故事

- **US-1（每日资讯）**：作为信息工作者，我希望系统每天自动抓取我关心的源（RSS/GitHub Trending/Follow），AI 打分精选出最重要的几条，生成摘要，并在早上推送到我的飞书/企业微信，让我 3 分钟掌握动态。
- **US-2（Agent 编排）**：作为自动化爱好者，我希望用声明式 Agent + DAG 工作流组合多步骤任务（抓取→筛选→总结→发布），并能可视化运行过程。
- **US-3（知识沉淀）**：作为长期学习者，我希望把每日资讯中有价值的内容沉淀进知识库，并能用自然语言检索（后置）。
- **US-4（可观测与可评估）**：作为维护者，我希望看到每次 Agent 运行的 trace、token 成本、工具调用链，并能用数据集评估输出质量是否回归。

## 3. 功能清单

### 3.1 保留（从原项目）
| 能力 | 说明 |
| :--- | :--- |
| 声明式 Agent | provider+model+tools+skills+mcps 五维配置；ReAct 循环 |
| DAG 工作流引擎 | 拓扑排序 + 批次并行 + 数据依赖自动建图 + 子工作流嵌套 |
| 多模型抽象 | OpenAI/Claude/Gemini/Ollama 统一 tool calling（经 LangChain） |
| MCP 客户端 | stdio/sse/streamable-http，schema 清洗，命名隔离（后置） |
| Skill 系统 | 指令注入 + execute_command 联动（后置） |
| 插件化架构 | 四类插件 + 自动发现 + 注册中心 |
| 调度器 | APScheduler，4 类定时任务，热重载，task_logs |
| 知识库/记忆 | 分层索引（后置升级为混合检索） |
| Interop 互操作 | 外部 AI 自助注册→审批→发现→执行（后置） |
| 认证 | JWT + API Key 双轨 |

### 3.2 去掉
| 能力 | 原因 |
| :--- | :--- |
| 小红书浏览器自动化发布 | DOM 注入本质脆弱、慢、随平台改版失效 |
| 遗留 GitHubService.ts | 被新插件架构取代的冗余 |
| 双模式记忆/知识库冗余 | 统一为分层 + 混合检索（FTS5 降级保留） |
| 原完整 11 页前端 | 精简为 5 核心页（后置） |

### 3.3 新增
| 能力 | 说明 | 阶段 |
| :--- | :--- | :--- |
| **飞书机器人推送** | 自定义机器人 Webhook，交互卡片，签名校验 | MVP(P7) |
| **企业微信机器人推送** | Webhook，Markdown/图文消息 | MVP(P8) |
| **每日推送流水线** | DAG 工作流编排：抓取→去重→AI精选(+Loop自评)→渲染→fanout推送 | MVP(P11) |
| **Harness 增强** | 结构化上下文窗口(HarnessContext)/规划器/反思器 | MVP(P4)+后置 |
| **混合检索** | 向量召回 + FTS5 bm25 + RRF 融合 + 可选重排 | 后置(P16) |
| **可观测性** | OTel trace/metrics + structlog + Prometheus 端点 | MVP基础(P12)+后置(P23) |
| **评估框架** | 数据集 + LLM-as-judge + Benchmark 回归 | 后置(P21) |

## 4. 非目标（明确不做）

- 不做通用 CMS 或博客系统。
- 不做浏览器自动化发布（放弃小红书类平台）。
- 不做分布式/多节点部署（单机 SQLite 足够）。
- 不追求 1:1 复刻原前端。
- MVP 不含知识库/记忆/前端/评估/Interop/MCP/Skill。

## 5. 成功指标

| 指标 | 目标 | 衡量 |
| :--- | :--- | :--- |
| 每日推送可用 | 配置后无人值守连续 7 天成功推送 ≥1 端 | task_logs 成功率 |
| 推送质量 | AI 精选 top-N 命中率 ≥ 70%（人工抽检） | eval 数据集 |
| Agent 可观测 | 每次 run 有完整 trace + token 统计 | OTel 后端 |
| 重构收益 | 代码量/依赖数较原项目下降；插件新增 < 30 分钟 | 人工 |

## 6. 约束

- 单机部署，SQLite，无外部数据库/消息队列。
- 默认本地 embedding（可切 API）。
- Python 3.12+，Windows/Linux/macOS 兼容。
- GPL-3.0 兼容。

## 7. 里程碑

- **M1 MVP（P0–P13）**：每日抓取→AI精选→飞书/企微推送全链路跑通。
- **M2 后置（P14–P24）**：补全知识库/记忆/前端/评估/Interop/MCP/Skill。

详见 `docs/MVP.md` 与 `docs/phases/README.md`。
