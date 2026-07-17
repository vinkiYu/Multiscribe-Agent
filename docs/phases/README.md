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
| P0.5 | MVP 默认配置绑定 | ⏸️ 阻塞 P13 | — | .env→ProviderConfig.api_key 未映射(P1 黑名单);publisher enabled=False(P1);DailyDigestConfig.curate_agent_id 无默认值(P11);P0.5 修复:.env→model_validator 绑定;bootstrap 创建 default-curation-agent |
| [P14](./P14-后置大纲.md) | 其余采集适配器（Follow/GitHub/AI搜索） | ⚪ 未开始 | — | 大纲已定 |

**MVP 交付里程碑**：P0–P13 全 🟢 = MVP 完成。

## 后置（P14–P24）

> 详见 [P14-后置大纲.md](./P14-后置大纲.md)。临近执行时细化为完整包。

| 包 | 名称 | 状态 | 备注 |
| :--- | :--- | :--- | :--- |
| P14 | 其余采集适配器（Follow/GitHub/AI搜索） | ⚪ 未开始 | 大纲已定 |
| P15 | 其余发布端（GitHub/RSS/公众号） | ⚪ 未开始 | 大纲已定 |
| P16 | 知识库 + 混合检索 | ⚪ 未开始 | 大纲已定 |
| P17 | 记忆系统 | ⚪ 未开始 | 大纲已定 |
| P18 | MCP 客户端 | ⚪ 未开始 | 大纲已定 |
| P19 | Skill 系统 | ⚪ 未开始 | 大纲已定 |
| P20 | 精简前端（5 页） | ⚪ 未开始 | 大纲已定 |
| P21 | 评估框架 | ⚪ 未开始 | 大纲已定 |
| P22 | Interop 互操作层 | ⚪ 未开始 | 大纲已定 |
| P23 | 完整可观测性（OTel） | ⚪ 未开始 | 大纲已定 |
| P24 | Loop Engineering 深化 | ⚪ 未开始 | 大纲已定 |

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
