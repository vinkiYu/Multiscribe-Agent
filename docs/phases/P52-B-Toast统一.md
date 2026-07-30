# 执行包：P52-B — Toast 通知统一（sonner）

> **阶段**：前端基础设施消费期（A→B→C→D 路线第 2 站）
> **目标**：消费 P51 装好未用的 `sonner`，替换全端散落的通知机制（App.tsx 手写 toast + `onNotice` callback + `setMessage` inline），统一为一个右下角 neo-brutalist 风格 toast。
> **依赖**：P51（sonner 已装 + main.tsx/App.tsx 已拆分）。
> **预估**：1 个工作日。
> **零行为变化原则**：保持原文本内容、文案措辞、触发时机完全一致，仅换呈现方式。

---

## 一、为什么需要这个包

P51 装了 `sonner` 但未使用。当前的通知机制是「手写 + 多源散落」：
- App.tsx 维护 `notice` state + 一个手写 `<div className="toast">`
- 7 个页面通过 `onNotice` prop 传递通知
- 4 个页面用 `setMessage` + inline `<p>` 显示
- Provider 配置卡用 `setSyncMessage` / `setConnectionMessage` 双 inline `<p>`
- Dialog 表单内还有更多验证提示

问题：
- **重复代码**：同样"成功/失败"模式被写了 27 次
- **不能堆叠**：手写 toast 只能同时显示 1 条
- **不一致样式**：不同页面用不同 class（`workflow-message`、`knowledge-message`、`model-sync-message` 等）
- **关闭按钮依赖用户主动点**：没有自动消失
- **window.confirm 之外的所有反馈散落**：用户操作结果靠运气看到

sonner 解决全部问题：堆叠 / 自动消失 / 进度条 / 类型化 / 主流标准。

---

## 二、现状基线（已核实）

| 项 | 位置 | 现状 |
|---|---|---|
| sonner 安装 | `frontend/package.json:22` | `"sonner": "^2.0.7"` ✓ |
| sonner 导入 | 0 处 | 0 import |
| 手写 toast div | `frontend/src/App.tsx:103` | `<div className="toast" role="status">` ✓ |
| notice state | `frontend/src/App.tsx:43` | `useState('')` ✓ |
| 旧 toast CSS | `frontend/src/styles.css:60` | 1 条 `.toast` 规则 |
| `onNotice` 引用 | 约 16 处 | App.tsx 传 + 各页面收 |
| `setMessage` 引用 | 约 11 处 | 各页面 setMessage + inline `<p>` 渲染 |
| `window.confirm` | 5 处 | **本包不动**（删/跑任务的危险操作确认）|

**用户决策**（已确认）：
1. **零行为变化**：文案文本、触发时机完全保留
2. **window.confirm 保留**：5 个危险操作确认不动

---

## 三、任务拆解（2 个子任务）

### T1：P52-B.1 — sonner Provider 挂载

**改 3 个文件**：

#### `frontend/src/main.tsx`

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'sonner'                  // 新增
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
      <Toaster
        theme="light"
        position="bottom-right"
        closeButton
        richColors={false}
        duration={4000}
        toastOptions={{
          className: 'neo-toast',
        }}
      />
    </BrowserRouter>
  </StrictMode>,
)
```

#### `frontend/src/App.tsx`

```tsx
// 删除 line 43: const [notice, setNotice] = useState('')
// 删除 line 103: {notice && <div className="toast" ...>...</div>}
// 删除所有向页面传的 onNotice prop（共 7 处）
```

#### `frontend/src/styles.css`

**删** line 60 附近旧 `.toast` 规则，**替换为** sonner 覆盖样式：

```css
/* === sonner neo-brutalist overrides === */
[data-sonner-toaster] {
  z-index: 9999;
  --normal-bg: var(--paper);
  --normal-text: var(--ink);
  --normal-border: var(--ink);
}
[data-sonner-toast] {
  font-family: inherit !important;
  font-size: 14px !important;
  font-weight: 850 !important;
  padding: 12px 16px !important;
  border: 2px solid var(--ink) !important;
  border-radius: 7px !important;
  box-shadow: 3px 3px 0 var(--ink) !important;
  background: var(--paper) !important;
  color: var(--ink) !important;
}
[data-sonner-toast][data-type="success"] {
  background: var(--mint) !important;
}
[data-sonner-toast][data-type="error"] {
  background: #fce2ed !important;
  border-color: var(--danger) !important;
}
[data-sonner-toast][data-type="info"] {
  background: var(--blue-50) !important;
}
[data-sonner-toast][data-type="warning"] {
  background: var(--sun-50) !important;
}
[data-sonner-toast] [data-close-button] {
  border: 2px solid var(--ink) !important;
  background: var(--paper) !important;
  color: var(--ink) !important;
}
```

### T2：P52-B.2 — 迁移通知调用点

**shared/ui.tsx 顶部**：

```tsx
import { toast } from 'sonner'    // 新增（取代 onNotice prop）
```

**改动清单**（约 27 处，全在 `shared/ui.tsx` 内）：

#### A. `onNotice` callback → `toast.*` 直接调用

| 组件 | 操作 | 旧 | 新 |
|---|---|---|---|
| TasksPage | toggle 成功 | `onNotice('任务已停用')` | `toast.success('任务已停用')` |
| TasksPage | toggle 失败 | `onNotice('任务状态更新失败。')` | `toast.error('任务状态更新失败。')` |
| TasksPage | runNow 成功 | `` onNotice(`已提交"${task.name}"...`) `` | `` toast.success(`已提交"${task.name}"...`) `` |
| TasksPage | runNow 失败 | `onNotice('任务启动失败。')` | `toast.error('任务启动失败。')` |
| TasksPage | delete 成功 | `onNotice('任务已删除')` | `toast.success('任务已删除')` |
| TasksPage | delete 失败 | `onNotice('删除任务失败。')` | `toast.error('删除任务失败。')` |
| SourcesPage | save 成功 | `onNotice('数据源配置已保存')` | `toast.success('数据源配置已保存')` |
| SourcesPage | save 失败 | `onNotice('保存数据源配置失败')` | `toast.error('保存数据源配置失败')` |
| SettingsPage | save 成功 | `onNotice('设置已保存')` | `toast.success('设置已保存')` |
| SettingsPage | save 失败 | `onNotice('设置保存失败')` | `toast.error('设置保存失败')` |
| SkillsPage | reload 成功 | `onNotice(...)` | `toast.success(...)` |
| SkillsPage | reload 失败 | `onNotice('Skill 重载失败。')` | `toast.error('Skill 重载失败。')` |
| AdapterHealthPage | toggle 成功 | `onNotice('已启用 xxx')` | `toast.success('已启用 xxx')` |
| AdapterHealthPage | toggle 失败 | `onNotice('更新适配器状态失败')` | `toast.error('更新适配器状态失败')` |
| TasksPage (CreateTaskDialog close) | 创建成功 | `onNotice('计划任务已创建')` | `toast.success('计划任务已创建')` |
| TasksPage (EditTaskDialog close) | 更新成功 | `onNotice('任务已更新')` | `toast.success('任务已更新')` |

#### B. `setMessage('text')` + inline `<p>` → `toast.*` + 删除 `<p>` 渲染

| 组件 | 旧 | 新 |
|---|---|---|
| WorkflowsPage 工作流运行结束 | `setMessage('工作流已结束。')` + `<p className="workflow-message">` | `toast.success('工作流已结束。')` + **删除 `<p>` 渲染** |
| WorkflowsPage 工作流运行失败 | `setMessage('工作流执行失败。')` + 同上 | `toast.error('工作流执行失败。')` |
| WorkflowsPage 工作流删除成功 | `setMessage('工作流已删除。')` | `toast.success('工作流已删除。')` |
| WorkflowsPage 工作流删除失败 | `setMessage('删除工作流失败。')` | `toast.error('删除工作流失败。')` |
| WorkflowsPage 工作流创建 | `setMessage('工作流已创建。')` | `toast.success('工作流已创建。')` |
| KnowledgePage 检索失败 | `setMessage('检索失败')` + `<p className="knowledge-message">` | `toast.error('检索失败')` + 删除 `<p>` |
| KnowledgePage 文档已删除 | `setMessage('文档已删除')` | `toast.success('文档已删除')` |
| KnowledgePage 删除失败 | `setMessage('删除失败')` | `toast.error('删除失败')` |
| KnowledgePage 知识已加入 | `setMessage('知识已加入知识库')` | `toast.success('知识已加入知识库')` |
| KnowledgePage 分类已创建 | `setMessage('分类已创建')` | `toast.success('分类已创建')` |
| MemoryPage 记忆已保存 | `setMessage('记忆已保存。')` + `<p className="memory-message">` | `toast.success('记忆已保存。')` + 删除 `<p>` |
| MemoryPage 内容偏好已保存 | `setMessage('内容偏好已保存。')` | `toast.success('内容偏好已保存。')` |
| MemoryPage 搜索失败 | `setMessage('搜索记忆失败。')` | `toast.error('搜索记忆失败。')` |
| MemoryPage 记忆已删除 | `setMessage('记忆已删除。')` | `toast.success('记忆已删除。')` |
| MemoryPage 删除失败 | `setMessage('删除记忆失败。')` | `toast.error('删除记忆失败。')` |
| MemoryPage 整理成功 | `setMessage('已从近期发布记录整理出 X 条新记忆。')` | `toast.success(...)` |
| MemoryPage 整理失败 | `setMessage('整理发布记录失败。')` | `toast.error(...)` |

#### C. ProviderConfigurationCard 双 inline `<p>` → `toast.*`

```tsx
// 旧
const [syncMessage, setSyncMessage] = useState<string | null>(null)
// <p className="model-sync-message">{syncMessage}</p>
// 新
import { toast } from 'sonner'
toast.success('已找到 X 个模型')
```

#### D. 组件签名清理

```tsx
// 旧（多组件）
type Props = { onNotice: (msg: string) => void }
// 新
type Props = { /* onNotice 删除 */ }
```

**删除以下 prop**（位于 `shared/ui.tsx`）：
- `TasksPage` Props 的 `onNotice`
- `KnowledgePage` Props 的 `onNotice`
- `MemoryPage` Props 的 `onNotice`
- `SkillsPage` Props 的 `onNotice`
- `SourceConfigurationPageV2` Props 的 `onNotice`
- `SettingsPageV3` Props 的 `onNotice`
- `AdapterHealthPage` Props 的 `onNotice`

**删除以下 inline 渲染**：
- `<p className="workflow-message">...</p>`
- `<p className="knowledge-message">...</p>`
- `<p className="memory-message">...</p>`
- `<p className="model-sync-message">...</p>`
- `<p className="connection-message">...</p>`

**删除以下 state**：
- `WorkflowsPage` 的 `message` state
- `KnowledgePage` 的 `message` state
- `MemoryPage` 的 `message` state
- `ProviderConfigurationCard` 的 `syncMessage` / `connectionMessage` state

**styles.css 同步删除**：
- `.workflow-message` 规则（如有）
- `.knowledge-message` 规则（如有）
- `.memory-message` 规则（如有）
- `.model-sync-message` 规则（如有）
- `.connection-message` 规则（如有）

#### E. AdapterHealthPage 独立文件

`frontend/src/adapter-health.tsx`（独立于 pages/）也含 `onNotice` 调用 + 内联 `<p>`：

```tsx
// 在 adapter-health.tsx 中：
const [message, setMessage] = useState('')
// <p className="adapter-message">{message}</p>
// 改为：
import { toast } from 'sonner'
toast.success('已启用 xxx')
```

#### F. shared/curation-drawer.tsx 检查

P52-A 新建的 `shared/curation-drawer.tsx` 是否含 `onNotice` / `setMessage` —— 需 grep 确认；如无，无须改；如有，同步替换。

---

## 四、白名单与黑名单

### 白名单（可改/新增，共 7 个）

```
frontend/src/main.tsx                                       [T1: Toaster 挂载]
frontend/src/App.tsx                                       [T1: 删除 notice+onNotice 传递]
frontend/src/styles.css                                     [T1+T2: sonner 样式 + 删除旧 message 类]
frontend/src/shared/ui.tsx                                  [T2: 27 处迁移 + inline p 删除 + state 删除]
frontend/src/adapter-health.tsx                             [T2: 同步替换（如有 onNotice）]
frontend/src/shared/curation-drawer.tsx                     [T2: 检查 + 同步替换（如有）]
docs/phases/P52-B-Toast统一.md                              [本任务包]
```

### 黑名单（禁止改动）

- `frontend/src/services/api.ts`
- `frontend/src/shared/dialog.tsx`
- `frontend/src/shared/format.ts`
- `frontend/src/pages/*.tsx`（页面模块除 `onNotice` 接收外，内部逻辑不动；onNotice 接收如存在，从组件签名删除）
- `frontend/src/pages/curation-quality.tsx`（P52-A 已稳定，不动）
- `frontend/src/operations-dashboard.tsx`
- 后端所有文件
- `window.confirm` 调用（5 处保留）
- `@radix-ui/react-toast`（保留，留待未来清理包）

---

## 五、验收条件

| # | 验收 | 证据 |
|---|---|---|
| 1 | `main.tsx` 有 `<Toaster theme="light" />` | 文件内容 |
| 2 | `shared/ui.tsx` 有 `import { toast } from 'sonner'` | 文件内容 |
| 3 | `App.tsx` 无 `notice`/`setNotice` state | `grep -n 'notice' App.tsx` 无结果 |
| 4 | `App.tsx` 无 `.toast` div JSX | `grep '.toast' App.tsx` 无结果 |
| 5 | `shared/ui.tsx` 无 `onNotice` 引用 | `grep -n 'onNotice' shared/ui.tsx` 无结果 |
| 6 | `shared/ui.tsx` 无 `setMessage('...')` 调用 | `grep -n 'setMessage(' shared/ui.tsx` 无结果（state 定义 `useState('')` 还可能存在，需手动审视） |
| 7 | inline `<p className="*-message">` 全部删除 | `grep -n 'className="\(workflow\|knowledge\|memory\|model-sync\|connection\)-message"' shared/ui.tsx` 无结果 |
| 8 | `window.confirm` 保留原样 | `grep -n 'window.confirm' shared/ui.tsx` 有结果 |
| 9 | sonner CSS 覆盖样式存在 | `styles.css` 含 `[data-sonner-toast]` 规则 |
| 10 | `npm run build` 通过（tsc + vite）| 构建输出 |
| 11 | `npm run lint` 通过 | lint 输出 |
| 12 | 全量 pytest + ruff + mypy 通过（无回归）| 输出 |

---

## 六、测试与质量门

```bash
cd frontend
npm install   # 不需新包
npm run build
npm run lint

.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-p52b
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy src
```

视觉验收（手动）：
- 触发任意保存/删除操作 → 右下角弹出 sonner toast
- 成功 toast：薄荷绿背景 + 2px 黑边框 + 阴影
- 错误 toast：粉红背景 + 红色边框
- 自动消失（4s），有 × 关闭按钮
- 多个操作并发时：堆叠显示

---

## 七、完成定义

- [ ] 白名单 7 个文件全部修改
- [ ] 12 条验收条件全部通过
- [ ] sonner 接管所有成功/错误通知（除 window.confirm）
- [ ] 旧的 `onNotice` / `setMessage` / inline `<p>` 模式全部消失
- [ ] `codex/reviews/P52-B-REVIEW.md` 填写完毕

---

## 八、风险与取舍

1. **零行为变化原则**：文案文本不变、触发时机不变、仅换呈现方式。Codex 必须严格对照原文本复制，不得润色。
2. **进度条 toast**：本包不做（当前无异步操作需要）。后续如需要用 `toast.promise()`。
3. **dialog 关闭后 toast 时机**：Dialog `onClose` 回调中 `toast()` 是安全的——Dialog unmount 不影响已发出的 toast。
4. **`onNotice` 消亡链**：App.tsx 传 `onNotice` 的链路涉及 7 个页面组件；删 App 层后页面直接 `import { toast }`。
5. **styles.css 旧 `.toast` 规则**：替换为 sonner 覆盖样式，**避免双重样式**。
6. **sonner 默认 richColors**：`richColors={false}` 避免窄彩色边条，neo-brutalist 视觉要 2px 整圈黑边。
7. **@radix-ui/react-toast** 留着不删：本包不消费，留给未来独立清理包。
8. **CSS 类名残留清理**：`workflow-message` / `knowledge-message` / `memory-message` / `model-sync-message` / `connection-message` 等 inline 专用类，在 `<p>` 删除后**同步删除** CSS 规则。
9. **adapter-health.tsx 是独立文件**：P51 时它是独立文件，不在 `shared/ui.tsx` 里，需单独 grep。

---

## 九、文件清单

```
frontend/src/main.tsx                                       [修改: T1 Toaster 挂载]
frontend/src/App.tsx                                       [修改: T1 删除 notice + onNotice 传递]
frontend/src/styles.css                                     [修改: T1+T2 sonner 样式 + 删除旧 message 类]
frontend/src/shared/ui.tsx                                  [修改: T2 27 处迁移 + 4 个 state 删除 + 5 个 inline p 删除 + 7 个 onNotice prop 删除]
frontend/src/adapter-health.tsx                             [修改: T2 同步替换]
frontend/src/shared/curation-drawer.tsx                     [修改: T2 同步（如有）]
docs/phases/P52-B-Toast统一.md                              [新增: 本任务包]
```