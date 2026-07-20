# Multiscribe-Agent v1.1.0

> 面向可运行 MVP 与架构稳定性的阶段性版本。该版本汇总 P0-P28 的实现成果，并将阶段五的架构债清理纳入正式发布基线。

**发布日期**：2026-07-20  
**版本类型**：功能发布 / 架构稳定性发布  
**兼容运行时**：Python 3.12+

## 版本亮点

### MVP 主链路

- 完成配置绑定、领域模型、SQLite 数据层与仓储。
- 支持 OpenAI 兼容 Provider、中转 API endpoint、自定义模型名称和代理配置。
- 完成 Agent Harness、ReAct 执行、Loop 自评、DAG 工作流和每日 Digest 流水线。
- 提供 RSS、GitHub Trending、AI Search、Follow OPML 等采集适配器。
- 提供飞书、企业微信、微信公众号、小红书、钉钉等发布器。
- 提供 FastAPI API、CLI、JWT 鉴权、调度器、结构化日志和健康检查。

### 知识、记忆与扩展生态

- 完成知识库、FTS5/RRF 检索、记忆系统和发布历史。
- 提供 MCP Server、Interop API、OpenAI Function Calling schema。
- 提供预置 Skill 系统、评估框架、回归 benchmark 和反馈精炼链路。
- 提供 OTel 可选接入、Prometheus metrics 和 trace_id 注入。

### 阶段五架构债清理

- P26：重复工具调用死锁检测、Token 预算预警事件、线程安全 EventBus、Loop 迭代持久化与恢复。
- P27：慢查询监控、SQL 审计与可疑模式检测、threshold/window/ratio 告警规则、double-submit cookie CSRF。
- P28：SQLite 多读单写连接池、jieba 中文 FTS 分词与降级、插件 API 版本检查、subprocess 插件沙箱、覆盖率与性能基准门禁。

## 验证结果

本版本在 Windows 工作区使用项目内 pytest 临时目录完成验证：

```text
325 passed, 4 deselected, 1 warning
Total coverage: 88%
Performance benchmarks: 3 passed
ruff check .: All checks passed!
ruff format --check .: 265 files already formatted
mypy src: Success: no issues found in 146 source files
git diff --check: passed
```

已有阶段 Review：

- `codex/reviews/P0-REVIEW.md` 至 `codex/reviews/P25.1-REVIEW.md`
- `codex/reviews/P26-REVIEW.md`
- `codex/reviews/P27-REVIEW.md`
- `codex/reviews/P28-REVIEW.md`

## 升级与启动

```bash
git checkout v1.1.0
uv sync --extra dev --extra text
copy .env.example .env
uv run python -m multiscribe_agent digest
```

至少配置一个 LLM API key 和一个发布目标 webhook。中转 API 使用对应 Provider 的 `*_API_BASE_URL`，自定义模型使用 `*_MODEL` 或项目配置中的 provider model 字段。

## 配置变更

- 新增/稳定化 `SLOW_QUERY_THRESHOLD_SECONDS`、`ENABLE_SQL_AUDIT`、`CSRF_ENABLED`。
- `jieba` 位于 `text` optional extra；未安装时自动降级到 SQLite Unicode FTS。
- 默认 CSRF middleware 对浏览器状态变更请求启用 double-submit cookie 校验；Bearer API、登录和 Interop 前缀按配置豁免。

## 已知限制

- 前端请求封装仍需后续补充自动读取 `multiscribe_csrf` 并发送 `X-CSRF-Token` 的逻辑。
- `PluginMetadata.min_system_version` 当前是声明字段，注册阶段主要校验 `api_version`。
- 插件沙箱的 `memory_limit_mb` 是配置契约，当前没有跨平台 OS 级内存配额实现。
- EventBus、告警引擎和 Loop checkpoint 均为进程内/本地 SQLite 语义，多 worker 或分布式部署需要外部协调组件。

## 发布内容

- Git commit：`v1.1.0` 发布提交
- Git tag：`v1.1.0`
- GitHub Release：`Multiscribe-Agent v1.1.0`

感谢所有参与需求梳理、阶段规划、实现、测试和 Review 的协作者。
