# 阶段进度看板

> 每个原子工作包的状态总览。规划（ZCode）通过 review 后更新本表。
> 状态：⚪ 未开始 / 🔵 进行中 / 🟢 已通过 / 🟡 需修订 / ⏸️ 阻塞

## MVP（P0–P13）

| 包 | 名称 | 状态 | 通过日期 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| [P0](./P0-工程基线.md) | 工程基线与规范 | 🟢 已通过 | 2026-07-15 | 质量门全绿(独立复核);全局授权 git+uv.lock;pre-commit 原地 8/8 通过 |
| [P1](./P1-配置与领域模型.md) | 配置 + 领域模型 | 🟢 已通过 | 2026-07-15 | 18 模型+5 Protocol+ConfigService;domain 零外部依赖(独立复核 clean);21 测试全绿 |
| [P2](./P2-DB与仓储.md) | DB + 仓储 + FTS5 | 🟢 已通过 | 2026-07-16 | 5 仓储实现 ports;SQL 全参数化+表名/字段白名单防注入;FTS5 三情况触发器(独立验证 update/delete 同步);KV TTL+覆盖往返验证;31 测试全绿 |
| [P3](./P3-LLM-Provider.md) | LLM Provider 抽象 | 🟢 已通过 | 2026-07-16 | OpenAI+Anthropic Provider;归一化/流式合并/模型解析(arg→models[0]→ProviderError)均独立验证;零真实网络(全 mock);langchain<1+follow_imports skip(仅第三方,自身仍 strict);46 测试全绿 |
| [P4](./P4-Agent-Harness.md) | Agent Harness（ReAct+事件流） | 🟢 已通过 | 2026-07-16 | HarnessContext 窗口截断(32→5条/1589→181 token,首组+原子组保留)+工具压缩+token 单调,均独立验证;ReAct 事件流序列正确+trace_id 一致;工具异常隔离继续;反思器 retry 上限防无限循环;59 测试全绿 |
| [P5](./P5-插件骨架.md) | 插件骨架（基类+注册+发现） | 🟢 已通过 | 2026-07-16 | 四基类 ABC+四 Registry+自动发现;ExecuteCommandTool 安全边界(白黑名单+7种注入向量拦截+超时+截断,均独立攻击测试);ToolRegistry 双注册;72 测试全绿 |
| [P6](./P6-RSS适配器.md) | RSS 适配器 | 🟢 已通过 | 2026-07-16 | RSS→UnifiedData 字段映射(guid>link>id 优先级,published_date UTC ISO 规范化,summary 300 截断,均独立验证);网络失败容错返回 [];IngestionService run_single/run_all task_log 完整+失败隔离;78 测试全绿(1 e2e 跳过) |
| [P7](./P7-飞书机器人.md) | 飞书机器人推送 | 🟢 已通过 | 2026-07-16 | 签名算法(HMAC-SHA256+base64,与独立计算值一致验证)+卡片渲染(header+markdown elements+footer note)+指数退避重试(1/2/4s)+业务错误码触发重试,均独立验证;86 测试(2 e2e 跳过) |
| [P8](./P8-企业微信机器人.md) | 企业微信机器人推送 | 🟢 已通过 | 2026-07-16 | URL 拼接(完整/key-only/http)+errcode 处理(0 成功/非零带 errmsg)+Markdown 受限语法(##/**/>/[text](url),无表格/base64)+DigestItem 复用 P7+重试 500→200;93 测试(3 e2e 跳过) |
| [P9](./P9-调度器.md) | 调度器（APScheduler） | 🟢 已通过 | 2026-07-17 | TaskExecutorRegistry(task_type→callback)+AsyncIOScheduler+CronTrigger.from_crontab;task_log 完整生命周期(running→success/error);cron 校验(非法不注册);回调异常隔离;reload 热重载;95 测试全绿 |
| [P10](./P10-DAG工作流引擎.md) | DAG 工作流引擎 + Loop 节点 | 🟢 已通过 | 2026-07-17 | Kahn 拓扑排序+循环检测(DFS 返回具体路径)+同层 asyncio.gather 并行;input_map 隐式依赖+0/1/N 前驱输入推导;disabled 节点透传;子工作流递归;Loop(max_iterations+llm/regex/'DONE' 三种退出)+反馈注入+历史记录;WorkflowEvent 生命周期;AgentStepExecutor Protocol 注入;106 测试全绿 |
| [P11](./P11-每日推送流水线.md) | 每日推送流水线（Loop自评） | 🟢 已通过 | 2026-07-17 | 5 节点 DAG(ingest→dedupe→curate Loop→overview→fanout)+input_map 依赖;URL/SHA-256 去重;评分 top-N 精选;Loop 自评(retry→converge)+反馈注入;并发 fan-out(飞书+企微);Per-target 失败隔离(asyncio.gather return_exceptions)+CuratedDigest 聚合;DailyDigestConfig.from_mapping 调度器适配;register_daily_digest_executor 注册 P9;JSON 容错(嵌入 markdown fence 恢复);111 测试全绿 |
| [P12](./P12-API与可观测.md) | FastAPI + JWT + structlog | 🟢 已通过 | 2026-07-17 | FastAPI 应用工厂(create_app)+生命周期(lifespan)+访问日志 trace_id 中间件;JWT 登录+受保护端点(dev 密码 admin123+生产 jwt_secret 强校验);structlog 递归脱敏(7 个敏感键前缀+嵌套 dict/list);领域异常→HTTP 映射(AuthError 401/ValidationError 400/ProviderError 502);6 路由(auth/dashboard/digest/agents/workflows/schedules);SSE 流(P4 harness+P10 workflow EventSourceResponse);ServiceContext 组合根装配 P0-P11(数据库+仓储+插件+服务+调度+daily_digest 注册)+close/reload;_ProviderLoopReflector(P4→P10 LoopReflector 适配);117 测试全绿 |
| [P13](./P13-MVP收尾.md) | MVP 收尾（e2e+打包+文档） | ⏸️ 阻塞 | — | P13 BLOCKED;等待 P0.5 解锁 |
| P0.5 | MVP 默认配置绑定 | 🟢 已通过 | 2026-07-17 | .env→ProviderConfig.api_key(OPENAI/ANTHROPIC/GOOGLE model_validator 单向绑定);publisher enabled+config(飞书 webhook+secret/企微 webhook);default_curation_provider_id/model/temperature + default_digest_targets/top_n/fetch_days/adapter_ids(NoDecode CSV);bootstrap 启动幂等创建 default-curation-agent AgentDefinition(若不存在);空 api_key 不覆盖显式配置;122 测试全绿 |
| P0.6 | API 代理转发支持 | 🟢 已通过 | 2026-07-18 | config.py http_proxy 追加 AliasChoices("HTTP_PROXY","MULTISCRIBE_HTTP_PROXY")双向兼容;bootstrap._provider_for_agent()透传 proxy=settings.http_proxy or None;httpx/ChatAnthropic 接受 proxy 参数;空 http_proxy→None;test_proxy_routing.py 覆盖别名+透传+空值;126 测试全绿 |
| P0.7 | API 中转端点支持 | 🟢 已通过 | 2026-07-18 | config.py openai_api_base_url/anthropic_api_base_url 追加 AliasChoices;_bind_mvp_environment_values() 绑定 base_url→provider;ChatOpenAI(base_url=...) 已支持;HTTP_PROXY+base_url 叠加独立工作;139 测试全绿 |
| P0.8 | 自定义模型名称支持 | 🟢 已通过 | 2026-07-18 | 明确 ProviderConfig.models 是文档/UI 目录非运行时白名单;create_provider() 不对 model 名做白名单校验直接透传 ChatOpenAI(向下真实模型存在性由中转/OpenAI 端点承担);test_custom_model_name_is_forwarded_outside_provider_catalog 锁定 gpt-5.2 透传回归;131 测试全绿 |

## 后置（P14–P24）

| 包 | 名称 | 状态 | 通过日期 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| P14.1 | GitHub Trending 适配器 | 🟢 已通过 | 2026-07-19 | BaseAdapter.fetch/transform;selectolax 解析;language/stars_min/max_items 过滤;metadata 自动发现;139 测试全绿 |
| P14.2 | AI 搜索适配器 | 🟢 已通过 | 2026-07-19 | 注入 AIProvider.generate;perplexity/phind/custom 三模板;JSON 解析;graceful 降级;166 测试全绿 |
| P14.3 | Follow 适配器（OPML/API） | 🟢 已通过 | 2026-07-19 | OPML→UnifiedData;11 测试全绿 |
| P15.1 | 微信公众号发布器 | 🟢 已通过 | 2026-07-19 | BasePublisher.publish(content,options);Markdown→HTML(Markdown>=3.7);Token 单例;Semaphore(3);142 测试全绿 |
| P15.2 | 小红书发布器 | 🟢 已通过 | 2026-07-19 | 无参构造;options 读取凭据;Token 单例+app_key 哈希隔离;Markdown→小红书富文本;166 测试全绿 |
| P15.3 | 钉钉发布器 | 🟢 已通过 | 2026-07-19 | HMAC-SHA256→Base64→URLencode;Markdown+ActionCard;关键字校验;无参构造;166 测试全绿 |
| P15.4 | 发布历史记录 | 🟢 已通过 | 2026-07-19 | PublishHistory 单例;ddl/索引迁移;sanitize 脱敏;pipeline 集成;8 fixture;REST;185 测试全绿 |
| P16 | 知识库+混合检索(RRF) | 🟢 已通过 | 2026-07-19 | 8 模块(chunking/doc/embed/vec/retriever/kb_service/api/bootstrap);RRF 融合;sqlite-vec 可选降级;FTS5 bm25;降级标注 degraded;P16.1 修复可选依赖测试;235 测试无回归;ruff/mypy 全绿 |
| P16.1 | 修复可选依赖测试 | 🟢 已通过 | 2026-07-19 | 4 文件(2 测试 + 2 源码):PDF 分支 except OSError;embedding _encode_sync 短路 is_available();monkeypatch 类方法;235 passed 4 deselected |
| P17 | 记忆系统 | 🟢 已通过 | 2026-07-19 | 8 模块(repos/preference_store/extractor/retriever/service);sha256 去重;规则+LLM 双轨 tag;KB→memory 迁移;7 REST 端点;11 测试 |
| P18 | MCP 客户端 | 🟢 已通过 | 2026-07-19 | 5 MCP 工具(feed_rss/kb_search/digest_history/list_sources/list_publishers);stdio/SSE 传输;MCP_API_KEY 强制;REST 镜像;CLI mcp 子命令;mcp 1.28.1;10 测试;stdio/SSE smoke 进程存活 |
| P19 | Skill 系统 | 🟢 已通过 | 2026-07-19 | 6 模块(frontmatter/scanner/registry/service/loader);3 内置 Skill;覆盖策略;5 REST 端点;executor 注入 instructions[:1500];12 测试 |
| P20.1 | 前端扩展(Knowledge+Memory+Settings) | 🟢 已通过 | 2026-07-19 | 4 TSX + 2 service 完整重构;knowledge.ts → /api/kb/* 实时联调;memory.ts → localStorage+API 双轨;Settings → 4 Tab 含采集源/发布端;npm build 全绿;0 TS 错误;ESLint 1 warning |
| P21 | 评估框架(LLM-as-Judge) | 🟢 已通过 | 2026-07-19 | dataset/evaluator/benchmark/judge_prompts/CLI eval;2 datasets(tech-weekly/summary-quality);8 fixtures;11 测试;288 全量;rev1 修订白名单 |
| P22 | Interop 互操作层 | 🟢 已通过 | 2026-07-19 | InteropKey(sha256)/SlidingWindowLimiter/ToolRegistry;/api/ai/v1/{register,tools,execute,keys/{id}/approve};3 个 tool(list_sources/kb_search/list_publishers);10 测试;288 全量;rev1 补入 app.py |
| P23 | 完整可观测性(OTel) | 🟢 已通过 | 2026-07-19 | optional.py 缺包降级;OTel tracer(console/OTLP/no-op)+meter(Counter/Histogram);/metrics 端点;/healthz;structlog trace_id;executor/publisher 埋点;pyproject observability extra;14 测试;288 全量 |
| P24 | Loop Engineering 深化 | 🟢 已通过 | 2026-07-19 | LoopSpec(max_rounds/threshold/convergence_delta)+execute_loop_step 多轮;exit_reason 4 分类(threshold/convergence/max_rounds/stuck);feedback_loop.trigger_refinement;data/skills/loop-engineering-patterns/SKILL.md;20 测试;288 全量;rev1 修 score_diff=abs() |
| P25 | 架构债清理总览 | 📋 已规划 | 2026-07-20 | 基于 ARCHITECTURE_EVALUATION_REPORT 拆解 P0-P3 缺陷为 5 个任务包;复核每条缺陷的真实代码状态(P0-3/P0-4 部分已被阶段四覆盖) |
| P25.1 | P0 生产就绪门禁 | 🟢 已通过 | 2026-07-20 | P0-1 上下文溢出截断+should_warn_budget;P0-2 stream()超时(asyncio.wait_for 滚动 deadline);P0-3 trace_headers.py httpx hook;P0-4 EndpointRateLimiter middleware(429+Retry-After);16 新测试;304 全量;mypy/ruff 全绿 |
| P26 | Harness 与工作流稳定性 | ⚪ 未开始 | — | P1-1 ReAct 死锁检测(连续 3 次相同调用);P1-2 budget_warning 事件;P1-3 EventBus;P1-4 Loop 迭代持久化(workflow_iterations 表) |
| P27 | 安全加固与可观测性补全 | ⚪ 未开始 | — | P1-5 慢查询监控;P1-6 告警规则引擎(阈值/窗口/比率);P1-11 SQL 审计日志;P1-12 CSRF double-submit cookie |
| P28 | 数据层与插件生态 | ⚪ 未开始 | — | P1-7 ConnectionPool(读 N + 写 1);P1-8 jieba 中文分词;P1-9 插件 api_version;P1-10 subprocess 沙箱;P1-13 pytest-cov(≥75%);P1-14 pytest-benchmark |
| P29 | P2/P3 长期优化（大纲） | ⚪ 未开始 | — | P2 配置版本/暂停恢复/备份/热重载/密钥轮换/契约测试;P3 token 精度/流式工具/读副本/Jaeger UI;持续优化不设硬节点 |

**阶段一完成里程碑**：P14.1 ✅ P14.2 ✅ P14.3 ✅ P15.1 ✅ P15.2 ✅ P15.3 ✅ P15.4 ✅ → 阶段一完成。
**阶段二完成里程碑**：P16 ✅ P16.1 ✅ P17 ✅ P18 ✅ P19 ✅ → 阶段二完成。
**阶段三完成里程碑**：P20.1 ✅ → 阶段三完成。
**阶段四完成里程碑**：P21 ✅ P22 ✅ P23 ✅ P24 ✅ → 阶段四完成。**全部 14 个后置包通过；后 MVP 重构闭环。**
**阶段五进行中**：P25.1 ✅（P0 门禁已通过）；P26/P27/P28 待执行。

## 依赖图

```
P0 ──→ P1 ──→ P2 ──→ P6 ──→ P11
  │       │      ↗              ↑
  │       ├──→ P3 ──→ P4 ──→ P10 ──→ P11
  │       │      ↗       ↗      ↑
  │       ├──→ P5 ──→ P7 ──→ P11
  │       │      ↘  P8 ──→ P11
  │       └──→ P9 ──────────→ P11
  └──→ P12（依赖 P1-P11 全部）
         └──→ P13（依赖 P0-P12）

阶段二（已全部完成）：
P2 ──→ P16 知识库 ──→ P16.1 修复
P4 ──→ P17 记忆 ──→ P18 MCP（P18 依赖 P16.P17 KB + publish_history）
P4,P5 ──→ P19 Skill
P16,P17 ──→ P20.1 前端合并门禁

阶段三（已完成）：
P16,P17 ──→ P20.1 前端深化 ✅
  └─ knowledge service → /api/kb/* 实时联调
  └─ memory service → localStorage + /api/memory/* 双轨
  └─ Settings → 4 Tab（basic/providers/sources/publishers）
  └─ npm build 全绿; ESLint 1 warning; 0 TS 错误

阶段四（已完成）：
P21 评估框架 ✅
  └─ eval/{dataset,evaluator,benchmark,judge_prompts,feedback_loop}.py
  └─ CLI eval 子命令;2 datasets;8 fixtures
P22 Interop 互操作层 ✅
  └─ services/interop{,_rate_limit,_registry}.py
  └─ /api/ai/v1/{register,tools,execute,keys/{id}/approve}
  └─ 3 个 tool(list_sources/kb_search/list_publishers)
P23 OTel 全链路可观测 ✅
  └─ observability/{optional,tracer,meter}.py
  └─ /metrics 端点;/healthz;structlog trace_id 注入
  └─ executor/publisher 埋点;pyproject observability extra
P24 Loop Engineering ✅
  └─ agents/workflow/loop_node.py 多轮+LoopSpec
  └─ eval/feedback_loop.py 评估驱动精炼
  └─ data/skills/loop-engineering-patterns/SKILL.md

阶段五（架构债清理，规划中）：
基于 ARCHITECTURE_EVALUATION_REPORT.md（2026-07-20）
  └─ P25.1 P0 生产就绪门禁（上下文溢出/超时/trace 传播/限流）
  └─ P26 Harness 与工作流稳定性（死锁检测/预警/EventBus/迭代持久化）
  └─ P27 安全加固与可观测性补全（慢查询/告警引擎/SQL 审计/CSRF）
  └─ P28 数据层与插件生态（连接池/中文分词/版本检查/沙箱/覆盖率/性能基准）
  └─ P29 P2/P3 长期优化（配置版本/暂停恢复/备份/热重载/密钥轮换/契约测试/token 精度/流式工具/读副本/Jaeger UI）

**全局验证（阶段四 review 汇总）**：
```
pytest -q                288 passed, 4 deselected, 1 warning in 31.78s
mypy src                 Success: no issues found in 135 source files
ruff check .             All checks passed
ruff format --check .    235 OK;1 file dirty(白名单外既有脏文件 daily_digest.py)
```

**遗留诚实标注**：
- `ruff format` 单文件 `daily_digest.py` 不在阶段四白名单，按规范未越权格式化。
- P23 可选 OTel 包未实装（`.venv` 无 `pip` 且 `uv` 不可用），走缺包降级路径；`pip install -e ".[observability]"` 验证延期。
```

## 角色循环（固化）

```
决策者（人）：定目标/约束/优先级/最终判断
    ↓
规划（ZCode）：澄清需求 → 拆任务包（Px-*.md）→ 定验收 → review
    ↓
执行（Codex）：读包 → 改码 → 跑测试 → 产 REVIEW（按 REVIEW_TEMPLATE）
    ↓
决策者：把 REVIEW 发回规划
    ↓
规划：按六条标准判定（范围合规/验收有据/测试全绿/规范干净/无回归/风险诚实）
    ├── 通过 → 更新本看板（🟢）→ 放行下一包
    └── 退回 → 标修订项 → Codex 重做
```

## 规划 review 的六条标准（公开）

1. **范围合规**：只改了白名单内文件，未碰黑名单。
2. **验收有据**：每条验收条件都有证据（测试输出/截图/命令结果）对应。
3. **测试全绿**：`ruff`/`mypy`/`pytest` 原始输出齐全且通过；e2e（如适用）跑通。
4. **规范干净**：代码符合 `docs/conventions/*`；分层依赖正确；无硬编码密钥。
5. **无回归**：未破坏已通过包的功能（跑全量测试验证）。
6. **风险诚实**：遗留问题/取舍/BLOCKED 如实说明，未掩盖。
