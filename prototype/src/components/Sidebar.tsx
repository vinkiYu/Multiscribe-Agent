import { type ReactElement } from 'react'
import { ArrowLeft, Blocks, BrainCircuit, CircleAlert, Files, LayoutDashboard, LibraryBig, ListChecks, RadioTower, Send, Settings2, Sparkles, Workflow } from 'lucide-react'

export type PageKey = 'dashboard' | 'operations' | 'sources' | 'workflows' | 'content' | 'publishing' | 'health' | 'knowledge' | 'memory' | 'tasks' | 'chat' | 'skills' | 'settings'

export interface NavItem {
  key: string
  label: string
  icon: typeof LayoutDashboard
  badge?: string
  target?: PageKey
}

const workbenchNav: NavItem[] = [
  { key: 'dashboard', label: '概览', icon: LayoutDashboard, target: 'dashboard' },
  { key: 'operations', label: '运营中心', icon: ListChecks, target: 'operations' },
  { key: 'sources', label: '数据源', icon: RadioTower, target: 'sources' },
  { key: 'workflows', label: '工作流', icon: Workflow, target: 'workflows' },
  { key: 'content', label: '内容', icon: Files, target: 'content' },
  { key: 'publishing', label: '发布记录', icon: Send, target: 'publishing' },
  { key: 'tasks', label: '任务记录', icon: ListChecks, target: 'tasks' },
]

const capabilityNav: NavItem[] = [
  { key: 'health', label: '适配器健康', icon: CircleAlert, target: 'health' },
  { key: 'knowledge', label: '知识库', icon: LibraryBig, target: 'knowledge' },
  { key: 'memory', label: '记忆', icon: BrainCircuit, target: 'memory' },
  { key: 'chat', label: '对话', icon: Sparkles, target: 'chat' },
  { key: 'skills', label: 'Skills', icon: Blocks, target: 'skills' },
  { key: 'settings', label: '设置', icon: Settings2, target: 'settings' },
]

const handleNavClick = (item: NavItem): void => {
  if (item.target) {
    window.dispatchEvent(new CustomEvent('multiscribe:navigate', { detail: { key: item.target } }))
  } else {
    window.dispatchEvent(new CustomEvent('multiscribe:toast', { detail: { message: `${item.label} 即将上线（占位）` } }))
  }
}

export function Sidebar({ open, onClose, activeKey }: { open: boolean; onClose: () => void; activeKey: PageKey }): ReactElement {
  return (
    <aside className={open ? 'sidebar is-open' : 'sidebar'} aria-label="控制台导航">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">M</div>
        <div className="brand-text">
          <strong>Multiscribe</strong>
          <small>信息生产工作台</small>
        </div>
      </div>
      <NavGroup label="工作台" items={workbenchNav} activeKey={activeKey} onSelect={(item) => { handleNavClick(item); onClose() }} />
      <NavGroup label="能力与设置" items={capabilityNav} activeKey={activeKey} onSelect={(item) => { handleNavClick(item); onClose() }} />
      <div className="sidebar-footer">
        <div className="sidebar-user">
          <span className="sidebar-user-avatar" aria-hidden="true">本</span>
          <div className="sidebar-user-text">
            <strong>本地工作区</strong>
            <small>已连接本地服务</small>
          </div>
        </div>
        <a className="sidebar-return" href="./index.html">
          <ArrowLeft /> 返回首页
        </a>
      </div>
    </aside>
  )
}

function NavGroup({ label, items, activeKey, onSelect }: { label: string; items: NavItem[]; activeKey: PageKey; onSelect: (item: NavItem) => void }): ReactElement {
  return (
    <section className="nav-group">
      <p className="nav-group-label">{label}</p>
      {items.map((item) => {
        const Icon = item.icon
        const isActive = item.target === activeKey
        const className = isActive ? 'nav-item is-active' : 'nav-item'
        return (
          <button
            key={item.key}
            type="button"
            className={className}
            aria-current={isActive ? 'page' : undefined}
            onClick={() => onSelect(item)}
          >
            <Icon />
            <span>{item.label}</span>
            {item.badge && <span className="nav-badge">{item.badge}</span>}
          </button>
        )
      })}
    </section>
  )
}