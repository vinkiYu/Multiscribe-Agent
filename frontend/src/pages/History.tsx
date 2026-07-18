import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getRecentLogs } from '../services/dashboardService'
import type { TaskLog } from '../services/dashboardService'
import { useToast } from '../context/ToastContext'

const STATUS_LABELS: Record<string, string> = {
  success: '成功',
  error: '失败',
  running: '运行中',
  pending: '等待中',
}

function fmtDate(iso: string): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

export default function History() {
  const { showError } = useToast()
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setLogs(await getRecentLogs(50))
    } catch (err) {
      showError('加载失败：' + friendlyError(err))
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => { load() }, [load])

  const filtered = search
    ? logs.filter(
        l =>
          l.task_name?.toLowerCase().includes(search.toLowerCase()) ||
          l.message?.toLowerCase().includes(search.toLowerCase()),
      )
    : logs

  return (
    <>
      <div className="page-head">
        <div>
          <h1>运行记录</h1>
          <p>查看最近的任务运行记录，包括状态、耗时和详细消息。</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={load} disabled={loading} type="button">
            {loading ? <span className="spinner" /> : '刷新'}
          </button>
        </div>
      </div>

      <div className="toolbar">
        <div className="filters">
          <input
            className="input"
            placeholder="搜索任务名称或消息…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        <span className="text-muted text-sm">{filtered.length} 条</span>
      </div>

      {filtered.length === 0 ? (
        <div className="empty">
          <strong>还没有运行记录</strong>
          <p>你还没有运行过任何任务。可先去采集并生成第一份摘要。</p>
          <Link className="btn" to="/selection" style={{ marginTop: 12, display: 'inline-flex' }}>
            创建第一次摘要
          </Link>
        </div>
      ) : (
        <article className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>开始时间</th>
                  <th>耗时</th>
                  <th>状态</th>
                  <th>结果数</th>
                  <th>消息</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(log => (
                  <tr key={log.id}>
                    <td><strong>{log.task_name}</strong></td>
                    <td className="text-mono">{fmtDate(log.start_time)}</td>
                    <td className="text-mono">
                      {log.duration ? log.duration.toFixed(1) + 's' : '—'}
                    </td>
                    <td>
                      <span className={'badge ' + (log.status === 'success' ? 'live' : '')}>
                        {STATUS_LABELS[log.status] ?? log.status}
                      </span>
                    </td>
                    <td>{log.result_count ?? '—'}</td>
                    <td
                      className="text-muted"
                      style={{
                        maxWidth: 300,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={log.message ?? ''}
                    >
                      {log.message ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
