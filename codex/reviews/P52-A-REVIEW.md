# P52-A Review

## 交付结论

P52-A“策展质量运营页”已完成，未修改每日策展执行链路、数据库表结构或现有策展评估接口。变更范围严格限定在 P52 白名单源码文件内；未提交 GitHub 推送。

## 实现内容

- 新增 `CurationStatsRepository`，以只读跨表查询将 `curation_evaluations` 与 `daily_digest_archives` 按日期 LEFT JOIN，返回最终评分、精选数、扫描数、效率、收敛状态、退出原因和轮次。效率在扫描数缺失或为 0 时返回 `null`。
- 新增受保护接口 `GET /api/curation-stats/by-period`。日期参数采用 ISO 日期，缺省查询最近 30 天，日期逆序时返回 422；接口复用现有 `get_current_user`，并通过 dialect mixin 兼容 SQLite/Postgres 占位符。
- 前端新增 `DailyCurationStat` 类型和 `curationStatsApi.getByPeriod()`。
- 新增“策展质量”运营页：收敛率、平均迭代轮次、平均精选分 3 张指标卡；最终评分趋势、Loop 轮次分布、退出原因占比、精选/扫描对比 4 张图表；历史明细表支持按日期打开当日资讯详情。
- 新增日期详情抽屉，复用现有 Radix Dialog，通过 `dailyNewsApi.byDate()` 展示摘要、扫描/精选数量、资讯标题、来源、评分、标签和外链。
- App 导航新增“策展质量”入口，新增响应式样式和空数据、加载、错误状态。

## 验证证据

- `npm run lint`：通过。
- `npm run build`：通过，TypeScript 与 Vite 构建完成；构建期间产生的 `frontend/dist/index.html` 已清理，未纳入阶段改动。
- `.venv\Scripts\python.exe -m ruff check .`：通过。
- `.venv\Scripts\python.exe -m ruff format --check .`：通过，364 个文件已格式化。
- `.venv\Scripts\python.exe -m mypy src`：通过，187 个源文件无类型错误。
- `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p52`：`602 passed, 6 deselected, 1 warning`。
- `git diff --check`：通过。
- 仓储归一化 smoke check：通过，`5 / 20` 正确计算为 `0.25`，SQLite 布尔收敛值正确映射。
- FastAPI OpenAPI smoke check：通过，`/api/curation-stats/by-period` 已注册。

## 风险与边界

- 当前接口按评估记录返回；如果同一天存在多个 workflow run，前端会显示多条同日期记录，趋势也按运行记录绘制。后续若运营口径要求“一天只保留最终一次”，应在独立阶段明确 latest-run 聚合规则。
- 退出原因的中文映射在前端维护，未知枚举会直接显示原始值，避免新后端原因静默丢失。
- 详情抽屉复用公开的 `daily-news` 归档接口，因此只展示已发布/已批准的归档；待审核或已拒绝的内容不会出现在抽屉中。
- 本阶段完成了代码级验收和构建验证，未启动浏览器执行人工截图验收；建议在部署环境登录控制台后确认真实数据下的图表和抽屉视觉效果。

## 变更文件

- `src/multiscribe_agent/infra/repositories/curation_stats.py`
- `src/multiscribe_agent/api/routes/curation_stats.py`
- `src/multiscribe_agent/app.py`
- `frontend/src/services/api.ts`
- `frontend/src/pages/curation-quality.tsx`
- `frontend/src/shared/curation-drawer.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
