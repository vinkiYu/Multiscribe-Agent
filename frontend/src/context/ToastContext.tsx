import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react'

type ToastKind = 'success' | 'error' | 'info'

interface ToastItem {
  id: number
  message: string
  kind: ToastKind
}

interface ToastContextType {
  showSuccess: (message: string) => void
  showError: (message: string) => void
  showInfo: (message: string) => void
  // Back-compat alias: callers using showToast('xxx') are treated as info
  showToast: (message: string) => void
}

const ToastContext = createContext<ToastContextType | null>(null)
let toastCounter = 0

const KIND_LABEL: Record<ToastKind, string> = {
  success: '成功',
  error: '错误',
  info: '提示',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const push = useCallback(
    (message: string, kind: ToastKind) => {
      const id = ++toastCounter
      setToasts(prev => [...prev, { id, message, kind }])
      // Success/info auto-dismiss after 3s; errors persist until dismissed.
      if (kind !== 'error') {
        setTimeout(() => dismiss(id), 3000)
      }
    },
    [dismiss],
  )

  const showSuccess = useCallback((m: string) => push(m, 'success'), [push])
  const showError = useCallback((m: string) => push(m, 'error'), [push])
  const showInfo = useCallback((m: string) => push(m, 'info'), [push])
  const showToast = useCallback((m: string) => push(m, 'info'), [push])

  return (
    <ToastContext.Provider
      value={{ showSuccess, showError, showInfo, showToast }}
    >
      {children}
      <div
        style={{
          position: 'fixed',
          right: 20,
          bottom: 20,
          zIndex: 200,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          maxWidth: 380,
        }}
      >
        {toasts.map(t => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            style={{
              padding: '12px 14px',
              borderRadius: 6,
              boxShadow: '0 4px 12px rgba(0,0,0,0.18)',
              fontSize: 13,
              lineHeight: 1.5,
              display: 'flex',
              alignItems: 'flex-start',
              gap: 10,
              color:
                t.kind === 'error'
                  ? '#fff'
                  : t.kind === 'success'
                    ? '#20231f'
                    : '#fff',
              background:
                t.kind === 'error'
                  ? '#c0392b'
                  : t.kind === 'success'
                    ? '#62d84e'
                    : '#20231f',
            }}
          >
            <strong style={{ flexShrink: 0, fontSize: 11, opacity: 0.85 }}>
              {KIND_LABEL[t.kind]}
            </strong>
            <span style={{ flex: 1 }}>{t.message}</span>
            {t.kind === 'error' && (
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                aria-label="关闭"
                style={{
                  background: 'transparent',
                  border: 0,
                  color: '#fff',
                  cursor: 'pointer',
                  fontSize: 16,
                  lineHeight: 1,
                  padding: 0,
                  marginLeft: 4,
                }}
              >
                ×
              </button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextType {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
