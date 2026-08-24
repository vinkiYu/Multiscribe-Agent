import { type ReactElement, type ReactNode } from 'react'
import { BookOpen, CircleAlert, RefreshCw } from 'lucide-react'

interface DataStatusProps {
  loading: boolean
  error: string | null
  empty: boolean
  emptyTitle: string
  emptyDescription: string
  onRetry?: () => void
  children: ReactNode
}

export function DataStatus({ loading, error, empty, emptyTitle, emptyDescription, onRetry, children }: DataStatusProps): ReactElement {
  if (loading) {
    return (
      <section className="state-panel" aria-busy="true">
        <RefreshCw className="spin" />
        <h2>正在加载</h2>
        <p>从本地服务读取最新运行结果。</p>
      </section>
    )
  }
  if (error) {
    return (
      <section className="state-panel state-error" role="alert">
        <CircleAlert />
        <h2>数据暂时不可用</h2>
        <p>{error}</p>
        {onRetry && (
          <button className="btn btn-primary" type="button" onClick={onRetry}>
            <RefreshCw /> 重新连接
          </button>
        )}
      </section>
    )
  }
  if (empty) {
    return (
      <section className="state-panel">
        <BookOpen />
        <h2>{emptyTitle}</h2>
        <p>{emptyDescription}</p>
      </section>
    )
  }
  return <>{children}</>
}