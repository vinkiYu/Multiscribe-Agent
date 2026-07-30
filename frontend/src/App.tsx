import { useCallback, useEffect, useState, type ReactElement } from 'react'
import { ArrowLeft, Blocks, BrainCircuit, CheckCircle2, CircleAlert, Files, LayoutDashboard, LibraryBig, ListChecks, Menu, Plus, RadioTower, RefreshCw, Send, Settings2, Workflow, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import logoUrl from '../multiscribe-logo.png'
import { ApiError, dashboardApi, type DashboardStats, type TaskLog } from './services/api'
import { AdapterHealthPage } from './adapter-health'
import { OperationsDashboardPage } from './operations-dashboard'
import { ContentPage } from './pages/content'
import { Dashboard } from './pages/dashboard'
import { KnowledgePage } from './pages/knowledge'
import { MemoryPage } from './pages/memory'
import { PublishingPage } from './pages/publishing'
import { SettingsPageV3 } from './pages/settings'
import { SkillsPage } from './pages/skills'
import { SourceConfigurationPageV2 } from './pages/sources'
import { TasksPage } from './pages/tasks'
import { WorkflowsPage } from './pages/workflows'

export type NavKey = 'dashboard' | 'operations' | 'sources' | 'workflows' | 'content' | 'publishing' | 'tasks' | 'health' | 'knowledge' | 'memory' | 'plugins' | 'settings'

interface NavigationItem { key: NavKey; label: string; icon: LucideIcon }
interface ViewCopy { title: string; description: string }

const workbenchItems: NavigationItem[] = [{ key: 'dashboard', label: '概览', icon: LayoutDashboard }, { key: 'operations', label: '运营中心', icon: ListChecks }, { key: 'sources', label: '数据源', icon: RadioTower }, { key: 'workflows', label: '工作流', icon: Workflow }, { key: 'content', label: '内容', icon: Files }, { key: 'publishing', label: '发布记录', icon: Send }, { key: 'tasks', label: '任务记录', icon: ListChecks }]

const capabilityItems: NavigationItem[] = [{ key: 'health', label: 'Adapter health', icon: CircleAlert }, { key: 'knowledge', label: '知识库', icon: LibraryBig }, { key: 'memory', label: '记忆', icon: BrainCircuit }, { key: 'plugins', label: 'Skills', icon: Blocks }, { key: 'settings', label: '设置', icon: Settings2 }]

const copy: Record<NavKey, ViewCopy> = { dashboard: { title: '今日概览', description: '查看内容从采集、精选到发布的运行状态。' }, operations: { title: '运营中心', description: '查看 Token 消耗、发布成功率和任务运行记录。' }, sources: { title: '数据源', description: '管理服务端配置的数据采集器。' }, workflows: { title: '工作流', description: '查看和运行已保存的 DAG 工作流。' }, content: { title: '内容', description: '查看资讯归档、AI 摘要和精选结果。' }, publishing: { title: '发布记录', description: '查看各渠道的投递结果。' }, tasks: { title: '任务记录', description: '查看计划任务和最近的执行日志。' }, health: { title: '适配器健康', description: '查看采集适配器的失败与降级状态。' }, knowledge: { title: '知识库', description: '管理持久化文档和检索索引。' }, memory: { title: '记忆', description: '管理跨任务复用的偏好和记忆条目。' }, plugins: { title: 'Skills', description: '查看已加载的内置和自定义 Skill。' }, settings: { title: '设置', description: '管理模型、凭据、采集器和发布器配置。' } }

function App(): ReactElement {
  const [active, setActive] = useState<NavKey>(() => {
    const saved = window.localStorage.getItem('multiscribe_active_view')
    return saved && saved in copy ? saved as NavKey : 'dashboard'
  })
  const [menuOpen, setMenuOpen] = useState(false)
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState('')
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [taskModalOpen, setTaskModalOpen] = useState(false)

  useEffect(() => {
    if (!window.localStorage.getItem('multiscribe_token')) window.location.replace('./login.html')
  }, [])

  const loadDashboard = useCallback(async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const [nextStats, nextLogs] = await Promise.all([dashboardApi.getStats(), dashboardApi.getLogs()])
      setStats(nextStats)
      setLogs(nextLogs)
    } catch (caught) {
      setStats(null)
      setLogs([])
      setError(caught instanceof ApiError ? caught : new ApiError('unknown', '读取概览数据失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadDashboard() }, [loadDashboard])
  const selectView = (key: NavKey): void => {
    window.localStorage.setItem('multiscribe_active_view', key)
    setActive(key)
    setMenuOpen(false)
  }
  const refreshActiveView = (): void => active === 'dashboard' ? void loadDashboard() : setRefreshVersion((value) => value + 1)
  const view = copy[active]
  if (!window.localStorage.getItem('multiscribe_token')) return <main className="access-redirect">正在前往登录页面...</main>

  return <div className="app-shell">
    <aside className={`sidebar ${menuOpen ? 'open' : ''}`} aria-label="控制台导航">
      <div className="brand"><img src={logoUrl} alt="Multiscribe" /><div><strong>Multi<span>scribe</span></strong><small>信息生产工作台</small></div></div>
      <Navigation title="工作台" items={workbenchItems} active={active} onSelect={selectView} />
      <Navigation title="能力与设置" items={capabilityItems} active={active} onSelect={selectView} />
      <div className="sidebar-footer"><div className="sidebar-user"><span>M</span><div><strong>本地工作区</strong><small>已连接本地服务</small></div></div><a className="sidebar-return" href="./index.html"><ArrowLeft />返回首页</a></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><button className="icon-button mobile-only" aria-label={menuOpen ? '关闭导航' : '打开导航'} onClick={() => setMenuOpen((open) => !open)}>{menuOpen ? <X /> : <Menu />}</button></header>
      <main>
        <section className="page-header"><div><h1>{view.title}</h1><p>{view.description}</p></div><div className="header-actions">{active === 'tasks' && <button className="button pink" onClick={() => setTaskModalOpen(true)}><Plus />新增任务</button>}<button className="button" onClick={refreshActiveView}><RefreshCw />刷新</button></div></section>
        {active === 'dashboard' && <Dashboard loading={loading} stats={stats} logs={logs} error={error} onRetry={loadDashboard} />}
        {active === 'operations' && <OperationsDashboardPage key={refreshVersion} />}
        {active === 'workflows' && <WorkflowsPage key={refreshVersion} />}
        {active === 'content' && <ContentPage key={refreshVersion} />}
        {active === 'publishing' && <PublishingPage key={refreshVersion} />}
        {active === 'tasks' && <TasksPage key={refreshVersion} onNotice={setNotice} createOpen={taskModalOpen} onCreateClose={() => setTaskModalOpen(false)} />}
        {active === 'health' && <AdapterHealthPage key={refreshVersion} onNotice={setNotice} />}
        {active === 'knowledge' && <KnowledgePage key={refreshVersion} />}
        {active === 'memory' && <MemoryPage key={refreshVersion} />}
        {active === 'plugins' && <SkillsPage key={refreshVersion} onNotice={setNotice} />}
        {active === 'sources' && <SourceConfigurationPageV2 key={refreshVersion} onNotice={setNotice} />}
        {active === 'settings' && <SettingsPageV3 key={refreshVersion} onNotice={setNotice} />}
      </main>
    </div>
    {notice && <div className="toast" role="status"><CheckCircle2 /><span>{notice}</span><button aria-label="关闭提示" onClick={() => setNotice('')}><X /></button></div>}
  </div>
}

function Navigation({ title, items, active, onSelect }: { title: string; items: NavigationItem[]; active: NavKey; onSelect: (key: NavKey) => void }): ReactElement {
  return <section className="nav-group"><p>{title}</p>{items.map((item) => { const Icon = item.icon; return <button key={item.key} className={active === item.key ? 'nav-item active' : 'nav-item'} aria-current={active === item.key ? 'page' : undefined} onClick={() => onSelect(item.key)}><Icon />{item.label}</button> })}</section>
}

export default App
