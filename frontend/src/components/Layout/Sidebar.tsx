import { NavLink } from 'react-router-dom'
import { createPortal } from 'react-dom'
import { useEffect, useState } from 'react'
import {
  LayoutDashboard,
  Filter,
  Sparkles,
  Bot,
  BookOpen,
  Brain,
  History,
  Puzzle,
  CalendarClock,
  FileText,
  Settings,
  X,
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

const NAV_ITEMS = [
  { label: '记忆与偏好', icon: Brain, path: '/memory' },
  { label: '工作台', icon: LayoutDashboard, path: '/' },
  { label: '采集与筛选', icon: Filter, path: '/selection' },
  { label: '摘要预览', icon: Sparkles, path: '/generation' },
  { label: 'Agent 与生成规则', icon: Bot, path: '/agents' },
  { label: '知识库', icon: BookOpen, path: '/knowledge' },
  { label: '运行记录', icon: History, path: '/history' },
  { label: '插件', icon: Puzzle, path: '/plugins' },
  { label: '自动任务', icon: CalendarClock, path: '/tasks' },
  { label: '技术日志', icon: FileText, path: '/logs' },
  { label: '系统设置', icon: Settings, path: '/settings' },
]

export default function Sidebar() {
  const { logout } = useAuth()
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  useEffect(() => {
    if (!showLogoutConfirm) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowLogoutConfirm(false)
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [showLogoutConfirm])

  const confirmLogout = () => {
    setShowLogoutConfirm(false)
    logout()
  }

  return (
    <aside className="sidebar" data-shell-nav>
      <a className="brand" href="#/">
        <img className="brand-logo" src="/logo.png" alt="Multiscribe Logo" />
        Multiscribe
      </a>

      <div className="nav-label">Workspace</div>

      <nav className="side-nav" aria-label="产品导航">
        {NAV_ITEMS.map(({ label, icon: Icon, path }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            className={({ isActive }) => (isActive ? 'active' : '')}
          >
            <span className="nav-icon" aria-hidden="true">
              <Icon size={18} />
            </span>
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="user-line">
          <span data-user>本地管理员</span>
          <span className="badge live">在线</span>
        </div>
        <a className="btn primary" href="/">
          返回官网
        </a>
        <button className="btn ghost" onClick={() => setShowLogoutConfirm(true)} type="button">
          退出登录
        </button>
      </div>

      {showLogoutConfirm && createPortal(
        <div
          className="modal-backdrop"
          role="presentation"
          onClick={event => {
            if (event.target === event.currentTarget) setShowLogoutConfirm(false)
          }}
        >
          <div
            className="modal logout-confirm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="logout-dialog-title"
            aria-describedby="logout-dialog-description"
          >
            <div className="modal-head">
              <strong id="logout-dialog-title">确认退出登录？</strong>
              <button
                className="btn icon-btn"
                onClick={() => setShowLogoutConfirm(false)}
                aria-label="关闭"
                title="关闭"
                type="button"
              >
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              <p id="logout-dialog-description">退出后需要重新输入访问密码。</p>
            </div>
            <div className="modal-foot">
              <button
                className="btn"
                onClick={() => setShowLogoutConfirm(false)}
                autoFocus
                type="button"
              >
                取消
              </button>
              <button className="btn primary" onClick={confirmLogout} type="button">
                确认退出
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </aside>
  )
}
