# 执行包：P52-C — 设置页 UX 升级（Radix Switch + DropdownMenu）

> **阶段**：前端基础设施消费期（A→B→C→D 路线第 3 站）
> **目标**：消费 P51 装好未用的 `@radix-ui/react-switch` 和 `@radix-ui/react-dropdown-menu`，把 8 个 checkbox-as-switch 和 1 个手写多选下拉统一为 Radix 原生无障碍组件。
> **依赖**：P51（Radix Switch + DropdownMenu 已装 + shared/ 拆分 + tokens.css 已建）。
> **预估**：1 个工作日。
> **零行为变化原则**：交互语义不变（toggle 状态、模型选择集合），仅换原语。

---

## 一、为什么需要这个包

P51 装了 `@radix-ui/react-switch ^1.2.6` 和 `@radix-ui/react-dropdown-menu ^2.1.15` 但零使用。当前控制台交互问题：

- **任务启用 toggle 是原生 `<input type="checkbox">`**：视觉像开关，交互是 check — 键盘 / 屏幕阅读器不可预期
- **Provider 激活是 `<button aria-pressed>`**：自己管理 state，没有真正的 `role="switch"`
- **模型目录多选是手写 `<div className="model-dropdown">`**：没有焦点管理、Esc 关闭、键盘导航、外部点击关闭
- **发布渠道启用是 label-wrapped checkbox**：同理

Radix 原语解决：键盘 Space/Enter、aria role、焦点环、外部点击关闭、type-ahead。

---

## 二、用户已确认的 2 个决策

1. **Switch 范围**：迁移全部 8 个 checkbox-as-switch（task-switch × 1 + dialog-check × 3 + publisher-toggle × 1 + provider-activation × 2 + source-boolean × 1）。
2. **adapter-health.tsx**：独立文件，**本包不处理**（留着以后单独做或忽略）。

---

## 三、现状基线（已核实）

| 项 | 位置 | 现状 |
|---|---|---|
| `@radix-ui/react-switch` | `frontend/package.json:14` | `"^1.2.6"`，**零导入** |
| `@radix-ui/react-dropdown-menu` | `frontend/package.json:15` | `"^2.1.15"`，**零导入** |
| Switch 候选（8 处） | `frontend/src/shared/ui.tsx` | task-switch(L166) / dialog-check(L173,L174,L180) / source-boolean(L297) / publisher-toggle(L313,L333) / provider-activation(L292,L385) |
| DropdownMenu 候选（1 处） | `frontend/src/shared/ui.tsx:397` | `model-select-trigger` + `model-dropdown`（catalog 多选）|
| 14 个 `<select>` | `frontend/src/shared/ui.tsx` 多行 | 小枚举列表 — **保留原生**（移动端 UX 更好，零迁移价值）|

---

## 四、任务拆解（2 个子任务）

### T1：P52-C.1 — 封装共享组件

**新建 2 个共享文件**（沿用 P51 `shared/dialog.tsx` 命名风格）：

#### `frontend/src/shared/switch.tsx`

```tsx
import { Root, Thumb } from '@radix-ui/react-switch'
import type { ReactElement, ReactNode } from 'react'

type Props = {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label: ReactNode
  disabled?: boolean
  id?: string
}

export function Switch({ checked, onCheckedChange, label, disabled, id }: Props): ReactElement {
  return (
    <div className="switch-row">
      <Root
        id={id}
        className="neo-switch"
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
      >
        <Thumb className="neo-switch-thumb" />
      </Root>
      <label className="neo-switch-label" htmlFor={id}>{label}</label>
    </div>
  )
}
```

#### `frontend/src/shared/dropdown.tsx`

```tsx
import { Root, Trigger, Portal, Content, CheckboxItem, ItemIndicator } from '@radix-ui/react-dropdown-menu'
import { ChevronDown, Check } from 'lucide-react'
import type { ReactElement, ReactNode } from 'react'

type CheckItem = {
  value: string
  label: string
  checked: boolean
}

type Props = {
  triggerLabel: ReactNode
  items: CheckItem[]
  onCheckedChange: (value: string, checked: boolean) => void
  disabled?: boolean
  ariaLabel?: string
}

export function MultiSelectDropdown({ triggerLabel, items, onCheckedChange, disabled, ariaLabel }: Props): ReactElement {
  return (
    <Root>
      <Trigger asChild>
        <button type="button" className="neo-dropdown-trigger" disabled={disabled} aria-label={ariaLabel}>
          {triggerLabel}
          <ChevronDown size={14} />
        </button>
      </Trigger>
      <Portal>
        <Content className="neo-dropdown-content" sideOffset={4} align="start">
          {items.map((item) => (
            <CheckboxItem
              key={item.value}
              className="neo-dropdown-item"
              checked={item.checked}
              onCheckedChange={(checked) => onCheckedChange(item.value, checked)}
              onSelect={(e) => e.preventDefault()}
            >
              <ItemIndicator className="neo-dropdown-indicator">
                <Check size={14} />
              </ItemIndicator>
              <span>{item.label}</span>
            </CheckboxItem>
          ))}
        </Content>
      </Portal>
    </Root>
  )
}
```

#### `frontend/src/styles.css` — 新增样式

**新增 4 类**（neo-brutalist Switch + Dropdown 视觉）：

```css
/* === neo-brutalist Switch === */
.switch-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.neo-switch {
  all: unset;
  width: 44px;
  height: 24px;
  background: var(--paper);
  border: 2px solid var(--ink);
  border-radius: 12px;
  position: relative;
  cursor: pointer;
  transition: background 120ms ease;
}
.neo-switch[data-state="checked"] {
  background: var(--mint);
}
.neo-switch[data-disabled] {
  opacity: 0.5;
  cursor: not-allowed;
}
.neo-switch-thumb {
  display: block;
  width: 16px;
  height: 16px;
  background: var(--ink);
  border-radius: 50%;
  transform: translateX(2px);
  transition: transform 140ms ease;
}
.neo-switch[data-state="checked"] .neo-switch-thumb {
  transform: translateX(22px);
}
.neo-switch-label {
  font-size: 14px;
  font-weight: 850;
  color: var(--ink);
  cursor: pointer;
}

/* === neo-brutalist DropdownMenu === */
.neo-dropdown-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border: 2px solid var(--ink);
  border-radius: 6px;
  background: var(--paper);
  color: var(--ink);
  font-weight: 850;
  font-size: 14px;
  cursor: pointer;
  box-shadow: 2px 2px 0 var(--ink);
  transition: transform 100ms ease, box-shadow 100ms ease;
}
.neo-dropdown-trigger:hover:not(:disabled) {
  transform: translate(-1px, -1px);
  box-shadow: 3px 3px 0 var(--ink);
}
.neo-dropdown-trigger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.neo-dropdown-content {
  min-width: 220px;
  max-height: 320px;
  overflow-y: auto;
  padding: 6px;
  background: var(--paper);
  border: 2px solid var(--ink);
  border-radius: 6px;
  box-shadow: 3px 3px 0 var(--ink);
  z-index: 50;
}
.neo-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  outline: none;
}
.neo-dropdown-item[data-highlighted] {
  background: var(--mint);
}
.neo-dropdown-indicator {
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--pink);
}
```

#### `frontend/src/styles.css` — 删除旧类

| 旧类 | 位置（已被 Switch/Dropdown 替代）|
|---|---|
| `.task-switch` | L166 已迁 |
| `.dialog-check` | L173/L174/L180 已迁 |
| `.source-boolean` | L297 已迁 |
| `.publisher-toggle` | L313/L333 已迁 |
| `.provider-activation` | L292/L385 已迁 |
| `.model-select-trigger` / `.model-dropdown` | L397 已迁 |

### T2：P52-C.2 — 替换 9 处调用点

**全在 `shared/ui.tsx` 内**（同 P52-B 迁移策略）。

#### Switch 替换（8 处）

| 行号 | 组件 | 旧 | 新 |
|---|---|---|---|
| 166 | TasksPage 任务行 | `<label className="task-switch"><input type="checkbox" checked={...} onChange={...}/>启用</label>` | `<Switch checked={...} onCheckedChange={...} label="启用" />` |
| 173 | EditTaskDialog | `<label className="dialog-check"><input type="checkbox" .../>启用此任务</label>` | `<Switch checked={...} onCheckedChange={...} label="启用此任务" />` |
| 174 | EditTaskDialog 紧凑变体 | 同上 | 同上 |
| 180 | CreateTaskDialog | 同上 | 同上 |
| 292 | SourceConfigurationPageV2 | `<button className="provider-activation ${...}" aria-pressed={...} onClick={() => update({ enabled: !provider.enabled })}>` | `<Switch checked={...} onCheckedChange={(c) => update({ enabled: c })} label="已激活/已停用" />` |
| 297 | SourceConfigFieldControl boolean 字段 | `<label className="source-boolean"><input type="checkbox" .../>{field.label}</label>` | `<Switch checked={...} onCheckedChange={...} label={field.label} />` |
| 313 | SettingsPageV2 publisher | `<input type="checkbox" checked={...} .../>` | `<Switch checked={...} onCheckedChange={...} label="已启用" />` |
| 333 | SettingsPageV3 publisher | `<label className="publisher-toggle"><input type="checkbox" .../>已启用/已停用</label>` | `<Switch checked={...} onCheckedChange={...} label="已启用/已停用" />` |
| 385 | ProviderConfigurationCard | `<button className="provider-activation ${...}" aria-pressed={...} onClick={...}>` | `<Switch checked={...} onCheckedChange={...} label="已激活/已停用" />` |

**注**：ProviderConfigurationCard 的 `<button>` 当前内嵌 "已激活/已停用" 文本 + `<span />` 装饰。Radix Switch 必须纯 thumb 不能嵌文本，所以拆出来。视觉效果差异极小（文本从按钮内移到按钮旁），保留可访问性提升。

#### DropdownMenu 替换（1 处）

| 行号 | 组件 | 旧 | 新 |
|---|---|---|---|
| 397 | ProviderConfigurationCard 模型目录 | `<button onClick={() => setCatalogOpen(...)}>{...}</button>` + `{catalog && catalogOpen && <div className="model-dropdown">...</div>}` | `<MultiSelectDropdown triggerLabel={...} items={catalog?.map(m => ({value: m, label: m, checked: provider.models.includes(m)})) ?? []} onCheckedChange={selectModel} disabled={!catalog} />` |

**`selectModel(model, checked)` 签名不变**——`MultiSelectDropdown` 直接接收，零适配。

**`catalogOpen` state 删除**（Radix 内部管理 open 状态）。

**`SourceConfigurationPageV2` 的 `enabled` 字段 onChange 适配**：

```tsx
// 旧
onClick={() => update({ enabled: !provider.enabled })}
// 新
onCheckedChange={(checked) => update({ enabled: checked })}
```

---

## 五、白名单与黑名单

### 白名单（可改/新增，共 4 个）

```
frontend/src/shared/switch.tsx                       [T1, 新增]
frontend/src/shared/dropdown.tsx                     [T1, 新增]
frontend/src/shared/ui.tsx                            [T2, 9 处替换 + 1 state 删除]
frontend/src/styles.css                                [T1, 新增 4 条 + 删除 6 条]
docs/phases/P52-C-设置页UX升级.md                     [本任务包]
```

### 黑名单（禁止改动）

- `frontend/src/services/api.ts`
- `frontend/src/shared/dialog.tsx`（P51 模板稳定）
- `frontend/src/shared/format.ts`
- `frontend/src/shared/curation-drawer.tsx`
- `frontend/src/pages/*.tsx`（页面模块不动 — 只改 shared/ui.tsx 内的页面组件）
- `frontend/src/operations-dashboard.tsx`
- `frontend/src/adapter-health.tsx`（用户决策不处理）
- 后端所有文件
- 14 个 `<select>` 原生下拉（小枚举，保留）
- `<details>` / `<summary>` 渐进披露（line 180, 392，保留）
- Settings tabs（line 333，保留 `<button>` 切换 — 已经是 Radix-equivalent 模式）
- 侧边栏列表（workflows/knowledge/sources，保留 `<button>` 切换）
- `@radix-ui/react-toast`（仍留着）

---

## 六、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | `shared/switch.tsx` 导出 `Switch` 组件 | 文件内容 |
| 2 | `shared/dropdown.tsx` 导出 `MultiSelectDropdown` 组件 | 文件内容 |
| 3 | `shared/ui.tsx` 有 `import { Switch } from '../shared/switch'` | 文件内容 |
| 4 | `shared/ui.tsx` 有 `import { MultiSelectDropdown } from '../shared/dropdown'` | 文件内容 |
| 5 | `shared/ui.tsx` 中 checkbox-as-switch 全部迁移（task-switch/dialog-check/source-boolean/publisher-toggle/provider-activation）| `grep` 旧类名无结果 |
| 6 | `shared/ui.tsx` 中手写 model dropdown 全部迁移 | `grep 'className="model-dropdown"' shared/ui.tsx` 无结果 |
| 7 | `catalogOpen` state 已删除 | `grep 'catalogOpen' shared/ui.tsx` 无结果 |
| 8 | styles.css 含 `.neo-switch` / `.neo-dropdown-content` / `.neo-dropdown-trigger` | 文件内容 |
| 9 | styles.css 旧类（`.task-switch` / `.dialog-check` / `.publisher-toggle` / `.provider-activation` / `.source-boolean`）已删 | grep 确认 |
| 10 | Switch 键盘可操作（Space 切换、Tab 聚焦）| 手动验证 |
| 11 | DropdownMenu 键盘可操作（↑↓ 导航、Enter 勾选、Esc 关闭、外部点击关闭）| 手动验证 |
| 12 | `npm run build` 通过（tsc + vite）| 构建输出 |
| 13 | `npm run lint` 通过 | lint 输出 |
| 14 | 全量 pytest + ruff + mypy 通过（无回归）| 输出 |

---

## 七、测试与质量门

```bash
cd frontend
npm install   # 不需新包
npm run build
npm run lint

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p52c
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy src
```

视觉验收（手动）：
- TasksPage 任务行 toggle：圆点 track，黑色 thumb，启用时薄荷绿
- Provider 卡片"已激活"：同样 Switch 视觉
- SettingsPageV3 发布渠道 toggle：同样 Switch
- 模型目录多选：点 trigger → 下拉弹出 → 多个 CheckboxItem → 键盘 ↑↓ 移动 → Enter 切换 → Esc 关闭 → 外部点击关闭
- 所有 Switch/Dropdown 视觉：2px 黑边 + 硬阴影（与 neo-brutalist 一致）

---

## 八、完成定义

- [ ] 白名单 4 个文件全部创建/修改
- [ ] 14 条验收条件全部通过
- [ ] 9 个交互原语全部 Radix 化（8 Switch + 1 Dropdown）
- [ ] 键盘 / 屏幕阅读器可访问性提升可验证
- [ ] `codex/reviews/P52-C-REVIEW.md` 填写完毕

---

## 九、风险与取舍

1. **Switch label 位置变化**：原 `<label>` wrap checkbox 的模式改为 `<div className="switch-row"><Switch/><label htmlFor/></div>`。视觉上 label 从内嵌到外置，但语义更清晰。
2. **provider-activation 按钮 → Switch**：原按钮内有 `<span />` 装饰 + 文本。新 Switch 不允许内嵌文本，所以装饰 span 删除，文本外置。视觉从"按钮内文字"变成"switch + 旁边文字"。
3. **`<select>` 全部保留**：14 个小枚举下拉用 Radix DropdownMenu 反而是退步（移动端体验差、键盘不如原生）。只迁 Provider 模型目录（高价值多选 + 已有自定义实现）。
4. **`catalogOpen` state 删除**：Radix 内部管 open，state 冗余删除。
5. **dropdown item 的 `onSelect` preventDefault**：勾选 item 时阻止 menu 关闭（多选语义必须保留菜单打开）。
6. **`<details>` 保留**：渐进披露语义正确，没必要换 Accordion。
7. **`<select>` 视觉**：原生 select 在 chrome/safari 是浏览器默认样式，可能与 neo-brutalist 不一致。但 14 个里大部分是用户输入（频率、星期），不是装饰下拉，保持原生更稳。本包不动它们。
8. **ProviderConfigurationCard 的 `setCatalogOpen` state**：删除后整个卡片更干净（state 减少 1 个）。

---

## 十、文件清单

```
frontend/src/shared/switch.tsx                       [新增: T1 Switch 封装]
frontend/src/shared/dropdown.tsx                     [新增: T1 MultiSelectDropdown 封装]
frontend/src/shared/ui.tsx                            [修改: T2 9 处替换 + 1 state 删除]
frontend/src/styles.css                                [修改: T1 4 条新增 + 6 条删除]
docs/phases/P52-C-设置页UX升级.md                     [新增: 本任务包]
```