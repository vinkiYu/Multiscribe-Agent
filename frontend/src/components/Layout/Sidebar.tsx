import { NavLink } from 'react-router-dom'
import { createPortal } from 'react-dom'
import { useEffect, useRef, useState } from 'react'
import type { PointerEvent } from 'react'
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
  GripVertical,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

type NavigationItem = {
  label: string
  icon: LucideIcon
  path: string
}

type DropTarget = {
  path: string
  position: 'before' | 'after'
}

const NAV_ORDER_STORAGE_KEY = 'multiscribe.sidebar-navigation-order.v1'
const NAV_ORDER_EVENT = 'multiscribe:sidebar-navigation-order'
const LONG_PRESS_DELAY = 350
const MOVE_CANCEL_DISTANCE = 8

const NAV_ITEMS: NavigationItem[] = [
  { label: '工作台', icon: LayoutDashboard, path: '/' },
  { label: '内容来源', icon: Filter, path: '/selection' },
  { label: '摘要与发布', icon: Sparkles, path: '/generation' },
  { label: 'AI 摘要规则', icon: Bot, path: '/agents' },
  { label: '知识库', icon: BookOpen, path: '/knowledge' },
  { label: '内容偏好', icon: Brain, path: '/memory' },
  { label: '运行记录', icon: History, path: '/history' },
  { label: '扩展功能', icon: Puzzle, path: '/plugins' },
  { label: '定时任务', icon: CalendarClock, path: '/tasks' },
  { label: '系统日志', icon: FileText, path: '/logs' },
  { label: '系统设置', icon: Settings, path: '/settings' },
]

function getOrderedNavigationItems(): NavigationItem[] {
  if (typeof window === 'undefined') return NAV_ITEMS

  try {
    const storedOrder = JSON.parse(localStorage.getItem(NAV_ORDER_STORAGE_KEY) ?? '[]')
    if (!Array.isArray(storedOrder)) return NAV_ITEMS

    const validPaths = new Set(NAV_ITEMS.map(item => item.path))
    const orderedPaths = storedOrder.filter(
      (path): path is string => typeof path === 'string' && validPaths.has(path),
    )
    const uniquePaths = [...new Set(orderedPaths)]
    const remainingPaths = NAV_ITEMS
      .map(item => item.path)
      .filter(path => !uniquePaths.includes(path))

    return [...uniquePaths, ...remainingPaths]
      .map(path => NAV_ITEMS.find(item => item.path === path))
      .filter((item): item is NavigationItem => Boolean(item))
  } catch {
    return NAV_ITEMS
  }
}

function reorderNavigationItems(
  items: NavigationItem[],
  sourcePath: string,
  target: DropTarget,
): NavigationItem[] {
  if (sourcePath === target.path) return items

  const sourceIndex = items.findIndex(item => item.path === sourcePath)
  const targetIndex = items.findIndex(item => item.path === target.path)
  if (sourceIndex < 0 || targetIndex < 0) return items

  const nextItems = [...items]
  const [source] = nextItems.splice(sourceIndex, 1)
  let insertionIndex = nextItems.findIndex(item => item.path === target.path)

  if (target.position === 'after') insertionIndex += 1
  nextItems.splice(insertionIndex, 0, source)
  return nextItems
}

function persistNavigationOrder(items: NavigationItem[]) {
  try {
    localStorage.setItem(NAV_ORDER_STORAGE_KEY, JSON.stringify(items.map(item => item.path)))
    window.dispatchEvent(new Event(NAV_ORDER_EVENT))
  } catch {
    // Sorting remains available for the current page when browser storage is unavailable.
  }
}

interface SidebarProps {
  onNavigate?: () => void
}

export default function Sidebar({ onNavigate }: SidebarProps) {
  const { logout } = useAuth()
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)
  const [navItems, setNavItems] = useState<NavigationItem[]>(getOrderedNavigationItems)
  const [draggingPath, setDraggingPath] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null)
  const pressTimerRef = useRef<number | null>(null)
  const pointerStartRef = useRef<{ x: number; y: number } | null>(null)
  const dragSourceRef = useRef<string | null>(null)
  const suppressClickRef = useRef(false)

  const clearLongPressTimer = () => {
    if (pressTimerRef.current !== null) {
      window.clearTimeout(pressTimerRef.current)
      pressTimerRef.current = null
    }
  }

  const resetDragState = () => {
    clearLongPressTimer()
    pointerStartRef.current = null
    dragSourceRef.current = null
    setDraggingPath(null)
    setDropTarget(null)
  }

  const getDropTargetAtPoint = (x: number, y: number): DropTarget | null => {
    const element = document.elementFromPoint(x, y)
    const navItem = element?.closest<HTMLElement>('[data-nav-path]')
    const path = navItem?.dataset.navPath
    if (!navItem || !path || path === dragSourceRef.current) return null

    const rect = navItem.getBoundingClientRect()
    return {
      path,
      position: y < rect.top + rect.height / 2 ? 'before' : 'after',
    }
  }

  const handlePointerDown = (event: PointerEvent<HTMLAnchorElement>, path: string) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return

    pointerStartRef.current = { x: event.clientX, y: event.clientY }
    event.currentTarget.setPointerCapture(event.pointerId)
    pressTimerRef.current = window.setTimeout(() => {
      dragSourceRef.current = path
      setDraggingPath(path)
      navigator.vibrate?.(10)
    }, LONG_PRESS_DELAY)
  }

  const handlePointerMove = (event: PointerEvent<HTMLAnchorElement>) => {
    if (!dragSourceRef.current) {
      const pointerStart = pointerStartRef.current
      if (!pointerStart) return

      const distance = Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y)
      if (distance > MOVE_CANCEL_DISTANCE) clearLongPressTimer()
      return
    }

    event.preventDefault()
    const nextDropTarget = getDropTargetAtPoint(event.clientX, event.clientY)
    setDropTarget(current => (
      current?.path === nextDropTarget?.path && current?.position === nextDropTarget?.position
        ? current
        : nextDropTarget
    ))
  }

  const finishDrag = (event: PointerEvent<HTMLAnchorElement>) => {
    clearLongPressTimer()
    const sourcePath = dragSourceRef.current

    if (!sourcePath) {
      pointerStartRef.current = null
      return
    }

    event.preventDefault()
    const nextDropTarget = getDropTargetAtPoint(event.clientX, event.clientY) ?? dropTarget
    if (nextDropTarget) {
      const nextItems = reorderNavigationItems(navItems, sourcePath, nextDropTarget)
      if (nextItems !== navItems) {
        setNavItems(nextItems)
        persistNavigationOrder(nextItems)
      }
    }

    suppressClickRef.current = true
    window.setTimeout(() => {
      suppressClickRef.current = false
    }, 0)
    resetDragState()
  }

  useEffect(() => {
    if (!showLogoutConfirm) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setShowLogoutConfirm(false)
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [showLogoutConfirm])

  useEffect(() => {
    const syncNavigationOrder = () => setNavItems(getOrderedNavigationItems())
    const handleStorage = (event: StorageEvent) => {
      if (event.key === NAV_ORDER_STORAGE_KEY) syncNavigationOrder()
    }

    window.addEventListener('storage', handleStorage)
    window.addEventListener(NAV_ORDER_EVENT, syncNavigationOrder)
    return () => {
      window.removeEventListener('storage', handleStorage)
      window.removeEventListener(NAV_ORDER_EVENT, syncNavigationOrder)
    }
  }, [])

  useEffect(() => () => clearLongPressTimer(), [])

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

      <div className="nav-label">工作区</div>

      <nav className={'side-nav' + (draggingPath ? ' is-reordering' : '')} aria-label="产品导航">
        {navItems.map(({ label, icon: Icon, path }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            data-nav-path={path}
            title="长按并拖动可调整顺序"
            className={({ isActive }) => [
              isActive ? 'active' : '',
              draggingPath === path ? 'dragging' : '',
              dropTarget?.path === path && draggingPath !== path
                ? `drop-${dropTarget.position}`
                : '',
            ].filter(Boolean).join(' ')}
            onDragStart={event => event.preventDefault()}
            onPointerDown={event => handlePointerDown(event, path)}
            onPointerMove={handlePointerMove}
            onPointerUp={finishDrag}
            onPointerCancel={resetDragState}
            onClick={event => {
              if (suppressClickRef.current) {
                event.preventDefault()
                event.stopPropagation()
                return
              }
              onNavigate?.()
            }}
          >
            <span className="nav-icon" aria-hidden="true">
              <Icon size={18} />
            </span>
            {label}
            <span className="nav-drag-handle" aria-hidden="true">
              <GripVertical size={16} />
            </span>
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
