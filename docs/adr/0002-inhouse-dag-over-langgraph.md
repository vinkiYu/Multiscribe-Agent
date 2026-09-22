# ADR-0002 自研 DAG 工作流引擎,而非 LangGraph 全托管编排

- 状态:已采纳
- 日期:2026-07-17(P10),2026-09-22 补录
- 关联:`agents/workflow/graph.py`、`agents/pipelines/daily_digest.py`、`docs/phases/P10-DAG工作流引擎.md`

## 背景

每日日报需要多节点流水线(抓取→去重→策展→渲染→分发),节点间有数据依赖、部分节点需要"执行→自评→重试"的收敛循环。可选:用 LangGraph 声明图,或自研拓扑引擎。

## 备选方案

1. **LangGraph 全托管** — 上手快,但图执行语义由框架版本决定;与自研 Harness(滑窗/工具压缩/反思)叠两层编排概念;深度定制(如 Loop 自评反馈注入、per-target 失败隔离)需绕框架。
2. **自研 DAG + Loop 节点**(采纳)— Kahn 拓扑 + 同层 asyncio.gather 并行 + 子工作流递归;Loop 节点自带 max_iterations + llm/regex/'DONE' 三种退出条件,反馈注入下一轮。

## 取舍

- 采纳 2:编排语义完全自有、可测试(106 用例锁定),与 Harness 通过 `AgentStepExecutor` Protocol 解耦;LangChain 只用于 LLM Provider 层,不进入编排层。
- 代价:循环检测、拓扑、并发语义自行维护;新编排能力(如条件分支)需自己加。

## 后果

- "LangGraph 依赖仍在"仅服务 Provider 兼容路径;编排事实标准是自研 DAG。
- 后续任何"用 X 框架替换自研编排"的提案必须先以 ADR 形式提出,并证明自研引擎的测试资产可平移。
