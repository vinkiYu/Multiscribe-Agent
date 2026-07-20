import { useEffect, useState, type ReactNode } from 'react'
import { Menu, X } from 'lucide-react'
import Sidebar from './Sidebar'

interface AppLayoutProps {
  children: ReactNode
}

export default function AppLayout({ children }: AppLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    if (!sidebarOpen) return

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSidebarOpen(false)
    }

    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [sidebarOpen])

  return (
    <div className="app-shell">
      {/* Desktop sidebar always visible */}
      <Sidebar />

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="mobile-overlay show"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile sidebar */}
      <div
        id="mobile-sidebar"
        className={`mobile-sidebar ${sidebarOpen ? 'open' : ''}`}
        aria-hidden={!sidebarOpen}
      >
        <Sidebar onNavigate={() => setSidebarOpen(false)} />
      </div>

      <main className="main">
        {/* Mobile floating menu button */}
        <button
          className="btn icon-btn floating-menu"
          onClick={() => setSidebarOpen(o => !o)}
          aria-expanded={sidebarOpen}
          aria-controls="mobile-sidebar"
          aria-label={sidebarOpen ? '关闭导航' : '打开导航'}
          type="button"
        >
          {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        <div className="content">{children}</div>
      </main>
    </div>
  )
}
