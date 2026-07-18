import { useState, type ReactNode } from 'react'
import { Menu, X } from 'lucide-react'
import Sidebar from './Sidebar'

interface AppLayoutProps {
  children: ReactNode
}

export default function AppLayout({ children }: AppLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

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
        className={`sidebar ${sidebarOpen ? 'open' : ''}`}
        style={{
          position: 'fixed',
          left: 0,
          transform: sidebarOpen ? 'translateX(0)' : 'translateX(-100%)',
          width: 'min(280px, calc(100vw - 48px))',
          transition: 'transform 180ms ease',
          zIndex: 70,
        }}
      >
        <Sidebar />
      </div>

      <main className="main">
        {/* Mobile floating menu button */}
        <button
          className="btn icon-btn floating-menu"
          onClick={() => setSidebarOpen(o => !o)}
          aria-label="打开导航"
          type="button"
        >
          {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        <div className="content">{children}</div>
      </main>
    </div>
  )
}