import { useCallback, useEffect, useState, type ReactElement } from 'react'
import { Sidebar, type PageKey } from './components/Sidebar'
import { ErrorBoundary } from './components/ErrorBoundary'
import { AdapterHealthPage } from './pages/AdapterHealthPage'
import { ChatPage } from './pages/ChatPage'
import { ContentPage } from './pages/ContentPage'
import { DashboardPage } from './pages/DashboardPage'
import { KnowledgePage } from './pages/KnowledgePage'
import { MemoryPage } from './pages/MemoryPage'
import { OperationsPage } from './pages/OperationsPage'
import { PublishingPage } from './pages/PublishingPage'
import { SettingsPage } from './pages/SettingsPage'
import { SourcesPage } from './pages/SourcesPage'
import { TasksPage } from './pages/TasksPage'
import { WorkflowsPage } from './pages/WorkflowsPage'
import { SkillsPage } from './pages/SkillsPage'
import { authApi } from './services/api'
import { onUnauthorized } from './services/client'
import { wsBus } from './services/wsBus'

const renderers: Omit<Record<PageKey, (flash: (message: string) => void) => ReactElement>, 'skills'> = {
  dashboard: (flash) => <DashboardPage onFlash={flash} />,
  operations: (flash) => <OperationsPage onFlash={flash} />,
  sources: (flash) => <SourcesPage onFlash={flash} />,
  workflows: (flash) => <WorkflowsPage onFlash={flash} />,
  content: (flash) => <ContentPage onFlash={flash} />,
  publishing: (flash) => <PublishingPage onFlash={flash} />,
  health: (flash) => <AdapterHealthPage onFlash={flash} />,
  knowledge: (flash) => <KnowledgePage onFlash={flash} />,
  memory: (flash) => <MemoryPage onFlash={flash} />,
  tasks: (flash) => <TasksPage onFlash={flash} />,
  chat: (flash) => <ChatPage onFlash={flash} />,
  settings: (flash) => <SettingsPage onFlash={flash} />,
}

const validPageKeys: PageKey[] = ['dashboard', 'operations', 'sources', 'workflows', 'content', 'publishing', 'health', 'knowledge', 'memory', 'tasks', 'chat', 'skills', 'settings']

const TOKEN_KEY = 'multiscribe_token'
const DEFAULT_LOGIN_PASSWORD = 'admin123' // mirror of multiscribe_agent/api/security.py:verify_login_password

export default function App(): ReactElement {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [page, setPage] = useState<PageKey>('dashboard')
  const [token, setToken] = useState<string | null>(() => window.localStorage.getItem(TOKEN_KEY))
  const [authenticating, setAuthenticating] = useState<boolean>(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [password, setPassword] = useState<string>(DEFAULT_LOGIN_PASSWORD)

  useEffect(() => {
    if (token) {
      wsBus.start()
    }
    return () => wsBus.stop()
  }, [token])

  useEffect(() => {
    const off = onUnauthorized(() => {
      setToken(null)
      try { window.localStorage.removeItem(TOKEN_KEY) } catch { /* noop */ }
      setToast(null)
    })
    return off
  }, [])

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ key: PageKey }>).detail
      if (detail && validPageKeys.includes(detail.key)) {
        setPage(detail.key)
      }
    }
    window.addEventListener('multiscribe:navigate', handler)
    return () => window.removeEventListener('multiscribe:navigate', handler)
  }, [])

  const flash = useCallback((message: string) => {
    setToast(message)
    window.setTimeout(() => setToast((current) => (current === message ? null : current)), 1800)
  }, [])

  const login = useCallback(async () => {
    setAuthenticating(true)
    setAuthError(null)
    try {
      const result = await authApi.login(password || DEFAULT_LOGIN_PASSWORD)
      window.localStorage.setItem(TOKEN_KEY, result.access_token)
      setToken(result.access_token)
      setAuthError(null)
      flash('登录成功。')
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : '登录失败')
    } finally {
      setAuthenticating(false)
    }
  }, [password, flash])

  if (!token) {
    return (
      <div className="app-shell">
        <div className="workspace">
          <main className="workspace-main">
            <section className="section login-screen">
              <div className="login-card">
                <h1>Multiscribe 控制台</h1>
                <p>请输入本地管理员口令以继续。默认值与后端 <code>multiscribe_agent/api/security.py</code> 中的 <code>admin123</code> 保持一致（当未设置 <code>SYSTEM_PASSWORD</code> 时使用）。</p>
                <form
                  onSubmit={(event) => {
                    event.preventDefault()
                    void login()
                  }}
                >
                  <label className="form-field form-field-full">
                    <span>管理员口令</span>
                    <input
                      type="password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      required
                    />
                  </label>
                  <button className="btn btn-primary" type="submit" disabled={authenticating || !password}>
                    {authenticating ? '登录中…' : '登录'}
                  </button>
                  {authError && <p className="login-error">{authError}</p>}
                </form>
              </div>
            </section>
          </main>
        </div>
        <div className={toast ? 'toast is-visible' : 'toast'} role="status" aria-live="polite">
          {toast ?? ''}
        </div>
      </div>
    )
  }

  const body: ReactElement = page === 'skills'
    ? <SkillsPage onFlash={flash} />
    : renderers[page](flash)

  return (
    <div className="app-shell">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} activeKey={page} />
      <div className="workspace">
        <main className="workspace-main">
          <ErrorBoundary onError={(message) => flash(`页面异常：${message}`)}>
            {body}
          </ErrorBoundary>
        </main>
      </div>
      <div className={toast ? 'toast is-visible' : 'toast'} role="status" aria-live="polite">
        {toast ?? ''}
      </div>
    </div>
  )
}