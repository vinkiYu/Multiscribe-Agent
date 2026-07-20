import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { getStats, getRecentLogs, triggerIngestion } from '../services/dashboardService'
import type { DashboardStats, TaskLog } from '../services/dashboardService'
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

export default function Dashboard() {
  const { showSuccess, showError, showInfo } = useToast()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [logs, setLogs] = useState<TaskLog[]>([])
  const [loading, setLoading] = useState(true)
  const [ingesting, setIngesting] = useState(false)
  const [checkingConnection, setCheckingConnection] = useState(false)
  const [connectionState, setConnectionState] = useState<'unknown' | 'ok' | 'error'>('unknown')
  const [lastChecked, setLastChecked] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, l] = await Promise.all([getStats(), getRecentLogs(10)])
      setStats(s)
      setLogs(l)
      setLastChecked(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
      setConnectionState('ok')
    } catch (err) {
      setConnectionState('error')
      showError('加载失败：' + friendlyError(err))
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => { load() }, [load])

  const handleSync = async () => {
    setIngesting(true)
    try {
      const result = await triggerIngestion({
        adapter_id: 'rss',
        config: { rss_url: 'http://feeds.bbci.co.uk/news/rss.xml' },
      })
      const count = result.result_count ?? result.results?.length ?? 0
      if (count > 0) {
        showSuccess(`已抓取 BBC 示例来源：${count} 条，内容已写入待处理队列`)
      } else {
        showInfo('已抓取 BBC 示例来源，暂无新内容')
      }
      await load()
    } catch (err) {
      showError('同步失败：' + friendlyError(err))
    } finally {
      setIngesting(false)
    }
  }

  const handleCheckConnection = async () => {
    setCheckingConnection(true)
    try {
      await getStats()
      setConnectionState('ok')
      setLastChecked(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
      showSuccess('后端服务连接正常')
    } catch (err) {
      setConnectionState('error')
      showError('连接检查失败：' + friendlyError(err))
    } finally {
      setCheckingConnection(false)
    }
  }

  const sourceCount = stats?.source_count ?? 0
  const taskCount = stats?.scheduled_tasks ?? 0
  const successCount = logs.filter(l => l.status === 'success').length
  const errorCount = logs.filter(l => l.status === 'error').length

  return (
    <>
      <div className="page-head">
        <div>
          <h1>工作台</h1>
          <p>查看内容采集、摘要生成和发布状态，或开始一次新的内容处理。</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={load} disabled={loading} type="button">
            {loading ? <span className="spinner" /> : '刷新状态'}
          </button>
          <button
            className="btn primary"
            onClick={handleSync}
            disabled={ingesting}
            type="button"
          >
            {ingesting ? <span className="spinner" /> : '抓取 BBC 示例来源'}
          </button>
        </div>
      </div>

      <section className="grid cols-4">
        <article className="card metric">
          <span className="metric-label">已采集内容</span>
          <strong className="metric-value">{sourceCount}</strong>
          <span className="metric-note">所有内容来源累计</span>
        </article>
        <article className="card metric">
          <span className="metric-label">定时任务</span>
          <strong className="metric-value">{taskCount}</strong>
          <span className="metric-note">已创建的自动任务</span>
        </article>
        <article className="card metric">
          <span className="metric-label">最近 10 次成功</span>
          <strong className="metric-value">{successCount}</strong>
          <span className="metric-note">基于最近 10 条运行记录</span>
        </article>
        <article className="card metric">
          <span className="metric-label">最近 10 次失败</span>
          <strong className="metric-value">{errorCount}</strong>
          <span className="metric-note">需要关注</span>
        </article>
      </section>

      <section className="grid cols-2" style={{ marginTop: 16 }}>
        <article className="card">
          <div className="card-head">
            <span>核心处理流程</span>
            <span className="badge live">
              <i className="dot live" />
              可运行
            </span>
          </div>
          <div className="card-body">
            <div className="list">
              <div className="list-item">
                <div className="list-copy">
                  <strong>1. 采集与筛选</strong>
                  <span>添加内容来源，抓取并生成摘要预览</span>
                </div>
                <Link className="btn" to="/selection">打开</Link>
              </div>
              <div className="list-item">
                <div className="list-copy">
                  <strong>2. 确认并发布</strong>
                  <span>编辑摘要后重新执行流程，目前发布按钮使用飞书机器人</span>
                </div>
                <Link className="btn" to="/generation">打开</Link>
              </div>
              <div className="list-item">
                <div className="list-copy">
                  <strong>3. 查看运行记录</strong>
                  <span>查看每次运行的输入、结果和错误</span>
                </div>
                <Link className="btn" to="/history">查看</Link>
              </div>
            </div>
          </div>
        </article>

        <article className="card">
          <div className="card-head">
            <span>系统连接</span>
            <button
              className="btn"
              onClick={handleCheckConnection}
              disabled={checkingConnection}
              type="button"
            >
              {checkingConnection ? <span className="spinner" /> : '检查连接'}
            </button>
          </div>
          <div className="card-body">
            <div className="list">
              <div className="list-item">
                <span>后端服务</span>
                <span className={'badge ' + (connectionState === 'ok' ? 'live' : '')}>
                  <i className={'dot ' + (connectionState === 'ok' ? 'live' : '')} />
                  {connectionState === 'ok'
                    ? '连接正常'
                    : connectionState === 'error'
                      ? '连接失败'
                      : '尚未检查'}
                </span>
              </div>
              <div className="list-item">
                <span>最近检测</span>
                <span className="badge">
                  {lastChecked ? lastChecked : '尚未检测'}
                </span>
              </div>
              <div className="list-item">
                <span>最近运行记录</span>
                <span className="badge">
                  {logs.length > 0 ? `${logs.length} 条` : '暂无'}
                </span>
              </div>
            </div>
          </div>
        </article>
      </section>

      <section style={{ marginTop: 16 }}>
        <article className="card">
          <div className="card-head">
            <span>最近运行</span>
            <Link className="btn" to="/logs">查看全部</Link>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {logs.length === 0 ? (
              <div className="empty">
                <strong>暂无运行记录</strong>
                <p>你还没有运行过任何任务。可先去采集与筛选页面生成第一份摘要。</p>
                <Link className="btn" to="/selection" style={{ marginTop: 12, display: 'inline-flex' }}>
                  创建第一次摘要
                </Link>
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>任务</th>
                      <th>开始时间</th>
                      <th>耗时</th>
                      <th>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.slice(0, 10).map(log => (
                      <tr key={log.id}>
                        <td>{log.task_name}</td>
                        <td className="text-mono">{fmtDate(log.start_time)}</td>
                        <td className="text-mono">
                          {log.duration ? log.duration.toFixed(1) + 's' : '—'}
                        </td>
                        <td>
                          <span className={'badge ' + (log.status === 'success' ? 'live' : '')}>
                            {STATUS_LABELS[log.status] ?? log.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </article>
      </section>
    </>
  )
}
