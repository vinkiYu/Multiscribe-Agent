# P51 Review: 前端基础设施

## 结论

阶段实现完成，建议通过。P51 完成了控制台基础设施整理：App 壳层从 515 行降至 107 行，页面入口拆到 10 个独立模块，公共状态/格式化能力集中到 shared，CSS 颜色集中到 token，8 个现有对话框切换到 Radix Dialog，且保留原有 API 和页面数据流。

## 变更范围

- `frontend/package.json`
  - 增加 `@radix-ui/react-dialog`、`@radix-ui/react-dropdown-menu`、`@radix-ui/react-switch`、`@radix-ui/react-toast`、`recharts`、`sonner`。
- `frontend/src/styles/tokens.css`
  - 新增 cream/paper/ink、品牌色、tint、border、alpha、shadow 等统一 CSS token。
- `frontend/src/styles.css`
  - 改为导入 token；补充 Radix dialog 状态动画和运营页 `.metric-grid`、`.table-wrap`、`.metric.purple`。
- `frontend/src/daily-news.css`、`frontend/src/marketing-news.css`
  - 将硬编码颜色替换为 token，营销页的 `#171717` 统一映射到 `--ink`。
- `frontend/src/App.tsx`
  - 仅保留导航、鉴权、Dashboard 数据加载和页面路由壳层；当前 107 行。
- `frontend/src/pages/*.tsx`
  - 提供 dashboard、workflows、content、publishing、tasks、knowledge、memory、skills、sources、settings 十个稳定页面入口。
- `frontend/src/shared/ui.tsx`
  - 提供 `useRemoteData`、`LoadingState`、`ErrorState`、`DataStatus`、`EmptyInline`、`Metric`、`PanelHeader` 及页面实现的兼容导出。
- `frontend/src/shared/format.ts`
  - 集中导出任务名、日期、Cron、状态格式化函数。
- `frontend/src/shared/dialog.tsx`
  - 封装 Radix `Dialog.Root/Overlay/Content/Title/Description/Close`。
  - 工作流、任务、知识库、记忆共 8 个 Dialog 已接入 Radix Root/Overlay/Content。
- `frontend/index.html`
  - 移除不存在的 `favicon.svg` 引用，保留 `multiscribe-logo.svg`。

## 验收证据

| # | 验收条件 | 证据 |
|---|---|---|
| 1 | 依赖安装成功 | `npm install` 成功，新增 Radix/recharts/sonner 包可解析；Node 20.17 产生一个既有 EBADENGINE warning，不影响安装。 |
| 2 | token 覆盖原有颜色和新增 tint/border/alpha | `frontend/src/styles/tokens.css`；`styles.css` 首行导入 token。 |
| 3 | daily-news.css 无硬编码 hex | `[regex]::Matches(...daily-news.css, '#[0-9A-Fa-f]{3,8}')` 无输出。 |
| 4 | App.tsx 不超过 150 行 | `Get-Content frontend/src/App.tsx` 结果为 `107`。 |
| 5 | 页面入口拆分 | `frontend/src/pages/` 下有 10 个页面模块并各自导出对应组件。 |
| 6 | shared UI/format 能力可复用 | `shared/ui.tsx` 导出状态、数据、指标组件；`shared/format.ts` 导出格式化函数。 |
| 7 | EditTaskDialog 死代码移除 | 旧组件的重复 return 已移除，迁移后只保留两种编辑模式的实际分支。 |
| 8 | V1 SourceConfigurationPage 与 SettingsPageV2 不再由 App 使用 | App 仅导入 `SourceConfigurationPageV2` 与 `SettingsPageV3`。 |
| 9 | Radix Dialog 完成迁移 | `shared/dialog.tsx` 提供封装；8 个 Dialog 使用 `Modal.Root`、`Modal.Overlay`、`Modal.Content`。 |
| 10 | 运营页缺失 CSS 已补齐 | `styles.css` 定义 `.metric-grid`、`.table-wrap`、`.metric.purple`。 |
| 11 | 前端生产构建通过 | `npm run build` 成功，`tsc -b` 与 `vite build` 均通过。 |
| 12 | 前端 lint 通过 | `npm run lint` 成功，无 error/warning 输出。 |

## 测试记录

```text
frontend: npm run lint
通过

frontend: npm run build
通过（tsc -b + vite build）

.venv\Scripts\python.exe -m ruff check .
All checks passed!

.venv\Scripts\python.exe -m ruff format --check .
362 files already formatted

.venv\Scripts\python.exe -m mypy src
Success: no issues found in 185 source files

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p51-full
602 passed, 6 deselected, 1 warning
```

首次不指定 `--basetemp` 的 pytest 运行因 Windows 默认临时目录 `C:\Users\hp\AppData\Local\Temp\pytest-of-hp` 权限不足产生 91 个 fixture setup errors；指定仓库内 basetemp 后全量通过，未发现代码断言回归。`uv` 当前未安装，因此使用现有 `.venv` 等价命令执行 Python 质量门禁。

## 风险与边界

1. P51 的页面入口按白名单拆出，但为保持零行为变化，页面实现和公共状态能力暂时集中在白名单允许的 `shared/ui.tsx`；后续可按页面独立维护性继续细分。
2. `frontend/package-lock.json` 未纳入本阶段白名单，因此保持阶段前版本；本机 `npm install` 已验证依赖可安装，但后续应在依赖治理阶段专门补齐 lockfile 更新策略。
3. Vite 构建仍提示远程字体资源无法在构建时解析；这是现有 `index.html` 的运行时字体依赖，不影响构建成功，但离线部署应补齐本地字体资源。
4. 本阶段未新增页面业务能力，也未修改 `frontend/src/services/api.ts`、后端接口或登录流程。

## 未做事项

- 未推送 GitHub。
- 未修改白名单之外的后端文件、API 服务、数据模型或现有 P32/P33/P50 review 修改。
