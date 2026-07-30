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
| P26 | Harness 与工作流稳定性 | 🟢 已通过 | 2026-07-20 | P1-1 executor 死锁检测(SHA-256 签名+连续 3 次);P1-2 budget_warning 事件;P1-3 core/event_bus.py(RLock+异常隔离);P1-4 workflow_iterations 表+resume_loop;7 测试;325 全量 |
| P27 | 安全加固与可观测性补全 | 🟢 已通过 | 2026-07-20 | P1-5 db.py 慢查询计时+metrics;P1-6 alerts.py(threshold/window/ratio)+alert_rules.yaml;P1-11 sql_audit.py(DROP/UNION/-- 检测+writer ContextVar 防递归);P1-12 csrf.py double-submit cookie;8 测试;325 全量 |
| P28 | 数据层与插件生态 | 🟢 已通过 | 2026-07-20 | P1-7 connection_pool.py(N read+1 write WAL);P1-8 text_tokenize.py jieba+降级;P1-9 PluginMetadata.api_version+registry 拒绝不兼容;P1-10 sandbox.py subprocess JSON;P1-13 pytest-cov 88%(阈值 75%);P1-14 tests/perf 3 benchmark;白名单偏差(domain/models vs plugins/base)已诚实标注;325 全量 |
| P29 | P2/P3 长期优化（大纲） | ⚪ 未开始 | — | P2 配置版本/暂停恢复/备份/热重载/密钥轮换/契约测试;P3 token 精度/流式工具/读副本/Jaeger UI;持续优化不设硬节点 |
| P30 | 上下文窗口生产链路修复 | 🟢 已通过 | 2026-07-24 | tiktoken 主依赖(误差 0%)+CJK fallback(1.5,误差 15.8%);13 模型预置窗口+PROVIDER_CONTEXT_WINDOWS env 覆盖;curate 投影精简 dict(去 description 全文/metadata);MAX_SKILL_PROMPT_CHARS=4000;含上下文窗口闭环(AgentRunResult/结构化终止/Reflection 预算化);381 全量;验收7(精简比例<30%)在P30.1加固 |
| P30.1 | digest curate 投影精简加固 | 🟢 已通过 | 2026-07-24 | summary 500→150字符+只留id/title/summary(去url/source/category);独立核实6场景全<30%(最严苛混合17.1%);386全量(+5测试);Codex已自提交 ba6e6e3 |
| P31 | 每日资讯全链路 P0 修复 | ⚪ 未开始 | — | 基于全链路实现文档+独立核实4个P0:T1发布幂等键(sha256(date+targets+content)+publish_history查询);T2采集全失败保护(无历史→停止,有历史→继续但暴露fetched_counts);T3空候选拦截(_fanout检查items为空);T4 LLM输出硬契约(score 1-10范围/title回绑原记录/summary截断100字/score_reason保存) |
| P32 | 上下文管理模块设计债清理 | 🟢 已通过 | 2026-07-24 | T1 resolve_token_counter按provider分派(OpenAI→tiktoken/Anthropic→CJK加权Counter/google,ollama→fallback);T2 ReadArtifactTool+ContextVar(store自动绑定async task,并发隔离);T3 ContextProvider补structlog.warning(脱敏query[:80]+msg[:200]);T4删checkpoint死字段;T5 id(message)架构约束注释;AnthropicCounter中文误差10.5%;392全量(+6测试) |
| P33 | 控制台前端 | 🟢 已通过 | — | 编号已占用(前端重设计提交 e39cd5a);非调度链路 |
| P34 | 调度幂等分布式锁 | 🟢 已通过 | 2026-07-28 | Redis SET NX EX+Lua owner-token释放;锁key=`multiscribe:scheduler:lock:{task_id}:{run_date}`粒度到天;TTL 7200s;busy→task_log(skipped)不执行;Redis不可达strict=True(默认)记error拒绝/strict=False放行;三入口(cron/run_now/CLI)在execute_task内统一覆盖;NoOpSchedulerLock兜底旧调用方;**连带修复**:ConfigService.get_settings改`_env_file=None`防.env二次污染(ZCode用代码复现验证为真实bug,决策者追认为A);434全量(+42);白名单10文件ruff/format/mypy全绿;全局ruff阻塞来自历史文件(settings.py属e39cd5a/.tmp-pypt临时产物)非P34,单独排期 |
| P35 | 跨天去重+候选排序 | 🟢 已通过 | 2026-07-29 | 独立pushed_content表(PK=content_hash+digest_date,INSERT OR IGNORE幂等);hash+url四重排除(批次内seen+跨天pushed);**hash一致性优化**:_dedupe建_content_hash_by_url映射,_fanout按url回查保证与排除阶段hash一致(LLM改写title/summary不影响);fallback候选按published_date倒序;_fanout任一渠道成功才写指纹(全失败不污染排除集);窗口N=fetch_days;_dedupe改async无阻碍;442全量(+8);commit 24dd28c;无越权 |
| P36 | 采集并发化 | 🟢 已通过 | 2026-07-29 | run_all跨适配器改asyncio.gather+Semaphore(默认4,可配);预处理(enabled过滤/adapter_id解析/Mapping校验)与执行分离;return_exceptions=True保持故障隔离(run_single内except兜底+gather层BaseException记warning);_bounded持Semaphore锁调run_single;run_single/适配器内部gather/超时/写锁全未改;ControlledAdapter用running/peak追踪真实验证并发峰值=4且耗时<1s(串行需2s);max_concurrency=2时peak<=2;故障隔离失败返回0成功返回1;446全量(+4);commit 22aa830;零越权(仅2白名单文件,三个包里最干净) |
| P37 | 全局ruff/工作区清理 | 🟢 已通过 | 2026-07-29 | 实测核实:ruff check零错误,仅daily_digest.py+settings.py需format;format纯空白改动(函数签名压行+补空行),git diff证实相对P35 commit零逻辑改动;gitignore追加.tmp-pytest/.pytest-tmp/.pytest-tmp-*/;删除4个残留目录;全局ruff check.+format --check .无scope全绿(298 files);446全量无回归;commit 1db1272;工作树未提交逻辑改动被正确隔离未纳入P37 |
| P38 | overview agent身份补全 | 🟢 已通过 | 2026-07-29 | 四层架构断裂的第四层补全:_overview从curate_agent_id改为OVERVIEW_AGENT_ID(daily_digest.py:562);新增DEFAULT_OVERVIEW_AGENT_PROMPT(英文写作人设,明确no JSON/markdown/English headings);_bootstrap_default_overview_agent仿照curate幂等模式注册agent(provider/model/temperature复用default_curation_*,方案A不引入新配置);init()调用链curate→overview→schedule;验收5关键断言"JSON array" not in system_prompt真实验证人设分离;450全量(+4);commit e0804bc;本批次最小包(daily_digest.py仅1行) |
| P39 | 适配器健康度与自动降级 | 🟢 已通过 | 2026-07-29 | adapter_health表(PK=adapter_id,UPSERT原子更新);record_result成功归零/失败递增,just_disabled只在跨越阈值(默认3)瞬间True避免重复告警;run_all预处理跳过disabled(与P36并发协同);AdapterHealthAlerter复用publisher发纯文本(决策3);三层容错(health写入/告警发送/per-target)保证best-effort不破坏采集;GET/POST API手动启用(enable清零)/禁用;config加adapter_health_failure_threshold+adapter_health_alert_targets(CSV);459全量(+9);commit 3d3efea;app.py路径修正(任务包笔误api/app.py→实际src/multiscribe_agent/app.py) |
| P40 | daily_digest成本可观测 | 🟢 已通过 | 2026-07-29 | 两接缝thread TokenUsage(execute_observed返回content+usage;_ProviderLoopReflector通过usage_sink回调+浅拷贝隔离解决单例reflector并发覆盖);opt-in Protocol(ObservingAgentStepExecutor/ObservingLoopAssessment)零破坏现有契约;_DigestUsage累加器per-run隔离(input/output/total/llm_calls);三级isinstance分支向后兼容(MemoryAwareObserving→Observing→普通executor退回零值);run返回usage子对象;端到端验证3次Agent+2次reflector=40/8/48/5算术精确;465全量(+6);commit 60f0b9b |
| P41 | 推送前预览审核 | 🟢 已通过 | 2026-07-29 | preview_mode(off默认向后兼容/preview_first先发审核群);archive表加approval_status列(PRAGMA检查+ALTER迁移兼容,运行时in columns降级防迁移缺失);_fanout分支(preview_first只发preview_targets+标记pending+不写pushed_content);POST /api/digest/{date}/approve从archive无损重建CuratedDigest(字段完全一致)+三级target解析(payload>schedule>enabled publishers)排除preview_targets+写pushed_content(至少一target成功,复用P35);reject终态不群发;统一_pending_archive校验(404/409/400);471全量(+6);commit 7991349;Codex诚实标注5个后续风险(approve无幂等锁/pending被public页可见/全失败仍approved/多日报歧义/无前端UI) |
| P42 | 预览审核后续风险加固 | 🟢 已通过 | 2026-07-29 | 修复P41两个中等风险:approve接Redis幂等锁(ServiceContext暴露scheduler_lock字段+approve端点acquire按日期key=multiscribe:digest:approve:{date} TTL=300s+try/finally release只在acquired+token时+占用409区分already_locked/unavailable+strict模式复用调度锁配置);public页过滤pending/rejected(archive.list/get加published_only可选参数默认False向后兼容+**approved也视为公开可见**(Codex正确补全的语义边界)+daily_news路由传True);复用P34锁零改实现;476全量(+5);commit 05915d8 |

**阶段一完成里程碑**：P14.1 ✅ P14.2 ✅ P14.3 ✅ P15.1 ✅ P15.2 ✅ P15.3 ✅ P15.4 ✅ → 阶段一完成。
**阶段二完成里程碑**：P16 ✅ P16.1 ✅ P17 ✅ P18 ✅ P19 ✅ → 阶段二完成。
**阶段三完成里程碑**：P20.1 ✅ → 阶段三完成。
**阶段四完成里程碑**：P21 ✅ P22 ✅ P23 ✅ P24 ✅ → 阶段四完成。**全部 14 个后置包通过；后 MVP 重构闭环。**
**阶段五进行中**：P25.1 ✅ P26 ✅ P27 ✅ P28 ✅（P0+P1 全部修复）；P29 持续优化（P2/P3）。
**阶段五·架构债清理批次（用户想法核实）**：P34 ✅ P35 ✅ P36 ✅ P37 ✅ P38 ✅ P39 ✅ P40 ✅ P41 ✅ P42 ✅（调度幂等+跨天去重+采集并发+全局清理+overview分离+适配器健康+成本可观测+预览审核+风险加固九连通过，批次闭环）。后续包可用无scope全局ruff验收。

> **架构优化报告**：详见 [ARCHITECTURE_OPTIMIZATION_REPORT.md](./ARCHITECTURE_OPTIMIZATION_REPORT.md)（2026-07-29）。覆盖 P0-P42 全程，含已完成优化总结、12 项剩余技术债清单（4 P1 + 8 P2）、功能扩展建议、架构成熟度评估、阶段六路线图（运营闭环→平台化→个性化）。

## 阶段六A（运营闭环 - P1技术债解决，进行中）

| 包 | 名称 | 状态 | 通过日期 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| P43 | 运营告警闭环与适配器健康看板 | 🟢 已通过 | 2026-07-29 | 深度核实后合并债2+债12;meter.py接线AlertEngine(record_publish记publish_failure 0.0/1.0+record_llm_call记llm_latency+新增record_error记error_count=1.0+新增record_query_timing记slow_query 0.0/1.0每次都记含快查询);db.py每次查询走record_query_timing(旧registry回退兼容);publishing.py except双记record_publish(False)+record_error;bootstrap接self.metrics.alert_engine=self.alerts+注册PublisherAlertCallback(仿AdapterHealthAlerter);config加alert_targets;前端adapter-health看板页(enable/disable);端到端测试meter→AlertEngine→callback全链路(ratio=0.5触发);482全量(+6);commit bb10233 |
| P44 | Database Protocol 抽象 | 🟢 已通过 | 2026-07-29 | Postgres迁移Phase0(纯重构零行为变化);DatabaseProtocol Protocol(execute/fetchone返回Mapping非Row,runtime_checkable);_SqliteRowMapping包装器(继承Mapping+双访问str/int key向后兼容旧序号);Database=SqliteDatabase别名(~20处import零改);6仓库_from_row类型Row→Mapping去掉import aiosqlite(仅db.py+connection_pool.py保留);jieba FTS hooks留SqliteDatabase实现内不污染Protocol;全量482→484零回归(+2 Protocol测试);commit bdeea28;iteration_store docstring残留aiosqlite措辞(代码已backend无关,非白名单未改) |
| P45 | 公开页点击追踪与偏好反哺 | 🟢 已通过 | 2026-07-29 | 债4可行子集(聊天反馈不可行bot单向webhook);click_events表(record+tag_click_counts窗口查询+malformed JSON容忍);GET /api/track-click公开无认证记录+302 redirect+**开放重定向防护(http(s) scheme校验拒绝javascript/file,Codex主动安全增强)**;PreferenceFeedbackService合并点击tags进preferred_tags(手动优先+按频率降序+去重+限长max20+全字段保留不覆盖手动配置+仅变化时save);daily_digest.run()策展前调apply_click_feedback;前端daily-news.tsx href改向tracker;反哺通过PreferenceStore间接生效(_filter_and_rank已消费preferred_tags);492全量(+8);commit 1aa932c |

**阶段六A（运营闭环 - P1技术债批次）**：P43 ✅ P44 ✅ P45 ✅（告警闭环+DB Protocol抽象+点击反哺三连通过，批次闭环）。P1四债处理：债2(AlertEngine)✅完全解决；债12(前端健康看板)✅随P43解决；债1(SQLite)🔄Phase0抽象完成,完整Postgres留平台化；债4(反馈采集)🔄点击追踪可行子集完成,聊天反馈留专用阶段。测试累积372→492(+120)。

**阶段六A+（面试亮点加固）**：P46 ✅ P47 ✅ P48 ✅（Loop迭代持久化+运营仪表盘+策展Eval三连通过，方向1+3+4 Layer1全部闭环）。测试累积505→514(+9)。

## 阶段六A+ 任务清单

| 包 | 名称 | 状态 | 通过日期 | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| P46 | Loop迭代持久化接线 | 🟢 已通过 | 2026-07-29 | 服务方向1(断点续跑)+方向3(仪表盘)共享缺口;探查发现iteration_store/loop_node resume逻辑/append逻辑全部已完整实现+test_loop_persistence单测有效,仅engine.py:163-170不传参导致生产workflow_iterations表永远空;接线:WorkflowEngine.__init__加iteration_store参数+_execute_step传workflow_run_id=trace_id(uuid4复用)+iteration_store;bootstrap构造IterationStore(self.db)注入两个engine+DailyDigestPipeline;daily_digest _engine传参;GET /api/workflow-iterations读API(run+step查/最近limit查,score delta从相邻scores推导因schema无delta列);IterationStore.list_recent;验收3+5证明表有数据[1,2,3]且同run_id重跑resume从round2继续(executor只调3次非6次);层次1(数据可观测+resume基础);497全量(+5);commit 6285ead |
| P47 | 运营仪表盘(Usage持久化+Publish聚合+前端) | 🟢 已通过 | 2026-07-29 | Layer1(数据可观测+仪表盘基础,非全量crash-recovery);T1:新增daily_usage表(ON CONFLICT upsert累加)+DailyUsageRepository+scheduler写hook(usage写入失败隔离不污染task状态);T2:PublishHistory.summary()(按status GROUP BY)+GET /api/publish-history/summary;P46迭代记录已通过list_recent直接消费无需新路由);T3:GET /api/dashboard/overview合并usage+publish+iterations+task_logs四数据源于单次请求;P46的ServiceContext.iteration_store直接调用);T4:新增operations-dashboard.tsx(4视图:Token卡片+发布成功率卡片+Loop迭代表格+任务日志);App.tsx增加NavKey+导航项+文案+渲染分支;api.ts补充类型定义;npm run build通过;505全量(+8);ruff/mypy全绿;commit 4f3a1c2 |
| P48 | 策展准确性轻量Eval(Direction4) | 🟢 已通过 | 2026-07-29 | Layer1(数据可观测+轻量Eval基础,非ground-truth基准);T1:消费WorkflowEngine.stream()的loop_iteration事件+_LoopIterationAccumulator聚合rounds/converged/exit_reason/final_score/delta/avg_iter_score/usage;run()返回loop_summary+workflow_run_id;T2:curation_evaluations表(workflow_run_id UNIQUE,upsert)+CurationEvaluationRepository(summary含avg_score/converge_rate/avg_rounds/per_reason);T3:CuratorJudge框架(enabled=False默认,Layer2才引入LLM调用,避免P48增加cost+latency);T4:GET /api/curation-evaluations+summary(认证+JWT);T5:dashboard/overview追加evaluation字段;app.py注册路由(实际路径src/multiscribe_agent/app.py,任务包已修正);T6:前端运营中心追加策展质量卡片(今日评分/收敛率/退出原因+最近10条记录);514全量(+9);ruff/mypy/vite全绿;commit b8f0e5a |

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

## Stage 6B

| Phase | 名称 | 状态 | 备注 |
| :--- | :--- | :--- | :--- |
| Phase 0 | Database Protocol 抽象 | 🟢 已通过 | P44 完成，等价 Phase 0 |
| Phase 1 | 占位符抽象 + PostgresDatabase 骨架 | 🟢 已通过 | PlaceholderStyle/DOLLAR + asyncpg optional; 530全量 |
| Phase 2 | execute() RETURNING + task_log破口修复 | 🟢 已通过 | db_protocol.execute()返回int\|None + RETURNING; 530全量 |
| Phase 3 | FTS tsvector + pgvector替代 | 🟢 已通过 | FtsQueryBuilder/PgVectorStore; 530全量 |
| Phase 4 | 配置 Bootstrap 双驱动 | 🟢 已通过 | db_driver配置 + init_database工厂 + Docker Postgres; 557全量 |
| Phase 5 | 迁移工具 + 完整切换 + 集成测试 | 🟢 已通过 | 8个Port补齐 + dialect.py + migrate_sqlite_to_postgres.py + testcontainers; 562全量(+48) |
| Phase 6 | Repository SQL 方言切换 | 🟢 已通过 | ?→$N全面切换(约100处) + json_extract方言; dialect.py框架接入; 566全量 + 真实PG容器烟测 15/15 |
| P30 | 上下文窗口生产链路修复 | 🟢 已通过 | curate投影补url/source + ConservativeTokenCounter显式degraded + 566全量 + ruff/mypy clean |
| P31.1 | 每日资讯 P2 收尾（score_threshold 字段化 + publish_history 加 digest_date UNIQUE + Reflection 截断可配） | 🟢 已通过 | 业务代码4 + 测试3；定向50 + 全量572 passed；ruff/mypy clean |
| P31.2 | 每日资讯全链路 P0 修复（幂等预检 / 全失败保护 / 空候选拦截 / LLM 契约） | 🟢 已通过 | 业务代码2 + 测试1；定向38 + 全量583 passed；ruff/mypy clean；deb9ff0 |
| P32 | _ingest 冗余查询安全合并（债 5 收窄版：合并 2 次 published_date 查询，零行为变化）| 🟢 已通过 | 业务代码1 + 测试1；定向42 + 全量587 passed；3→2 查询；ruff/mypy clean；277080e |
| P49 | Loop 续跑 run_id 复用修复（方向 1 加固：确定性 run_id = task_id:run_date，让崩溃同日重跑真正续跑）| 🟢 已通过 | 业务代码4 + 测试3；定向58 + 全量592 passed；ruff/mypy clean；785d32e；注：原编号 P33 与前端 P33 冲突，改为 P49 |
| P50 | 策展 Precision/Recall 回归测试（方向 4：ground-truth 候选池 + 真实策展人 LLM + F1 回归检测）| 🟢 已通过 | 新增源3+测试3+fixture5+yaml1；定向27 + 全量602 passed；ruff/mypy clean；a76860a |
| P51 | 前端基础设施（Radix/recharts/sonner 依赖 + 设计 token 提取 + 拆分 87KB App.tsx + Bug 修复）| ✅ **已通过**（2026-07-30）| ✅ ba53ec4 | 4 子任务 + 12 条验收；App.tsx 515→107 行；10 个 pages/ + shared/{ui,format,dialog}.tsx；602 passed；ruff/mypy clean；零行为变化 |
| P52-A | 策展质量运营页（消费 recharts + Radix Dialog：3 metric + 4 chart + 1 表格 + 1 Drawer + 1 个 archives×evaluations join 端点）| ✅ **已通过**（2026-07-30）| ✅ f694704 | 4 子任务 + 13 条验收；后端新端点 `GET /api/curation-stats/by-period`（LEFT JOIN）；前端首张图表页 + 详情抽屉；602 passed；ruff/mypy clean；零回归 |
| P52-B | Toast 通知统一（sonner：main.tsx Toaster 挂载 + 替换 App.tsx 手写 toast + 迁移 onNotice/setMessage 约 27 处调用 + 删除 5 个 inline p + 删除 7 个 onNotice prop）| 🔄 进行中 | 任务包已就绪，待 Codex 执行；12 条验收；零行为变化 |
