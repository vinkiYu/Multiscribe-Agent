# P52-C 设置页 UX 升级 Review

## 交付结论

P52-C 已完成。设置页和相关配置页的 9 处 checkbox/button 开关已统一迁移为 Radix Switch，Provider 模型目录的手写多选下拉已迁移为 Radix DropdownMenu CheckboxItem。交互文案、状态更新回调、原生 `<select>`、`<details>`、确认框和表单校验均保持不变。

## 白名单改动

- `frontend/src/shared/switch.tsx`：新增可复用 Switch 封装，提供 Radix `role="switch"`、键盘切换、禁用态和可见标签。
- `frontend/src/shared/dropdown.tsx`：新增多选 DropdownMenu 封装，使用 Portal、CheckboxItem、勾选指示器，并阻止选择后菜单关闭。
- `frontend/src/shared/ui.tsx`：迁移任务开关、任务弹窗开关、数据源启用、布尔配置字段、SettingsPageV2/V3 发布器开关、Provider 激活开关和模型目录；删除 `catalogOpen` 手动状态。
- `frontend/src/styles.css`：新增统一 Switch/Dropdown 视觉和焦点样式，删除旧控件 selector。

未修改后端、API 服务、页面模块、侧边栏、设置 Tab、原生 `<select>` / `<details>` 或 `@radix-ui/react-toast`。既有 `codex/reviews/P32-REVIEW.md`、`P33-REVIEW.md`、`P50-REVIEW.md` 修改未纳入本阶段提交。

## 验收证据

- `frontend/npm run lint`：通过。
- `frontend/npm run build`：通过，TypeScript 和 Vite 构建成功；仅有既存远程字体无法在离线构建时解析及 bundle size 提示。
- `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p52c`：`602 passed, 6 deselected, 1 warning`。
- `.venv/Scripts/python.exe -m ruff check .`：通过。
- `.venv/Scripts/python.exe -m ruff format --check .`：`364 files already formatted`。
- `.venv/Scripts/python.exe -m mypy src`：`Success: no issues found in 187 source files`。
- `git diff --check`：通过。
- 静态检索确认 `type="checkbox"`、`task-switch`、`dialog-check`、`source-boolean`、`publisher-toggle`、`provider-activation`、`model-select-trigger`、`model-dropdown`、`catalogOpen` 在目标源码中均无残留；模型目录保留为 `MultiSelectDropdown`，9 处开关由 `Switch` 覆盖。

## 风险与边界

1. 本阶段未运行浏览器自动化或屏幕阅读器实测；Radix 组件的键盘/焦点语义由组件库提供，建议在下一轮 UI 验收中手动验证 Space、Enter、方向键、Escape 和外部点击行为。
2. Provider 模型列表同步后不再强制自动打开菜单，用户需点击新的触发按钮打开，这是 Radix 菜单状态管理带来的等价交互变化。
3. 构建仍会提示远程字体无法离线解析和单 bundle 体积偏大，这些与本阶段控件迁移无关。

## 提交边界

本阶段只提交上述 4 个源码文件和本 Review 文件，不推送 GitHub。
