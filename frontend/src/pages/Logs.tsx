import { useState, useEffect, useCallback } from 'react'
import { getRecentLogs } from '../services/dashboardService'
import type { TaskLog } from '../services/dashboardService'
import { useToast } from '../context/ToastContext'

const STATUS_LABELS: Record<string, string> = {
  success: '成功',
  error: '失败',
  running: '运行中',
  pending: '等待中',
}

const LEVEL_FILTERS: Array<{ value: string; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'success', label: '成功' },
  { value: 'error', label: '失败' },
  { value: 'running', label: '运行中' },
  { value: 'pending', label: '等待中' },
]

function fmtDate(iso: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

export default function Logs() {
  const { showError } = useToast()
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [loading, setLoading] = useState(true)
  const [level, setLevel] = useState<string>('all')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setLogs(await getRecentLogs(100))
    } catch (err) {
      showError('加载失败：' + friendlyError(err))
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => { load() }, [load])

  const filtered = level === 'all' ? logs : logs.filter(l => l.status === level)

  return (
    <>
      <div className="page-head">
        <div>
          <h1>系统日志</h1>
          <p>最近 100 次任务的运行记录，包含完成情况和耗时。点击一条记录可查看完整信息。</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={load} disabled={loading} type="button">
            {loading ? <span className="spinner" /> : '刷新'}
          </button>
        </div>
      </div>

      <div className="toolbar">
        <div className="filters">
          {LEVEL_FILTERS.map(f => (
            <button
              key={f.value}
              className={'tab ' + (level === f.value ? 'active' : '')}
              onClick={() => setLevel(f.value)}
              type="button"
            >
              {f.label}
            </button>
          ))}
        </div>
        <span className="text-muted text-sm">{filtered.length} 条</span>
      </div>

      {filtered.length === 0 ? (
        <div className="empty">
          <strong>暂无系统日志</strong>
          <p>运行一次内容处理后，记录会显示在这里。</p>
        </div>
      ) : (
        <article className="card">
          <div className="card-body" style={{ padding: 0 }}>
            {filtered.map(log => {
              const expanded = expandedId === log.id
              return (
                <div
                  key={log.id}
                  className="log-line"
                  style={{
                    gridTemplateColumns: '180px 80px 1fr',
                    cursor: log.message ? 'pointer' : 'default',
                    background: expanded ? 'var(--color-subtle)' : undefined,
                  }}
                  onClick={() =>
                    log.message && setExpandedId(expanded ? null : log.id)
                  }
                >
                  <span className="log-time">{fmtDate(log.start_time)}</span>
                  <span
                    className="log-level"
                    style={{
                      color:
                        log.status === 'error'
                          ? '#c0392b'
                          : log.status === 'success'
                            ? 'var(--color-accent)'
                            : 'inherit',
                    }}
                  >
                    {STATUS_LABELS[log.status] ?? log.status}
                  </span>
                  <span>
                    <strong>{log.task_name}</strong>
                    {log.duration ? ` ${log.duration.toFixed(1)}s` : ''}
                    {log.message ? (
                      expanded ? (
                        <>
                          {' — '}
                          <span style={{ color: 'var(--color-fg)' }}>
                            {log.message}
                          </span>
                        </>
                      ) : (
                        ` — ${log.message.slice(0, 80)}${log.message.length > 80 ? '…（点击展开）' : ''}`
                      )
                    ) : null}
                  </span>
                </div>
              )
            })}
          </div>
        </article>
      )}
    </>
  )
}

function friendlyError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err)
  if (/Failed to fetch|NetworkError|connect|ECONN/i.test(msg)) {
    return '无法连接服务，请确认 Multiscribe 已启动'
  }
  if (/401|unauthorized/i.test(msg)) {
    return '登录已过期，请重新登录'
  }
  return msg
}
