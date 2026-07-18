import { useState, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import {
  listSchedules,
  saveSchedule,
  deleteSchedule,
  runScheduleNow,
} from '../services/scheduleService'
import type { ScheduleTask } from '../services/scheduleService'
import { useToast } from '../context/ToastContext'

const TASK_TYPE_LABELS: Record<string, string> = {
  daily_digest: '每日摘要',
  ingestion: '内容采集',
}

const PRESETS: Array<{ label: string; cron: string }> = [
  { label: '每天 08:00', cron: '0 8 * * *' },
  { label: '每天 08:30', cron: '30 8 * * *' },
  { label: '每个工作日 09:00', cron: '0 9 * * 1-5' },
  { label: '每周一 08:30', cron: '30 8 * * 1' },
  { label: '每隔 6 小时', cron: '0 */6 * * *' },
]

const EMPTY_TASK: Omit<ScheduleTask, 'id'> = {
  name: '新任务',
  task_type: 'daily_digest',
  cron: '0 8 * * *',
  enabled: true,
  config: {},
}

export default function TaskManagement() {
  const { showSuccess, showError, showInfo } = useToast()
  const [tasks, setTasks] = useState<ScheduleTask[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<ScheduleTask | null>(null)
  const [running, setRunning] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)
  const [recentStatus, setRecentStatus] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setTasks(await listSchedules())
    } catch (err) {
      showError('加载失败：' + friendlyError(err))
    } finally {
      setLoading(false)
    }
  }, [showError])

  useEffect(() => { load() }, [load])

  const openAdd = () => {
    setEditing({ id: 'task_' + Date.now(), ...EMPTY_TASK })
    setShowModal(true)
  }

  const openEdit = (t: ScheduleTask) => {
    setEditing({ ...t })
    setShowModal(true)
  }

  const closeModal = () => {
    setShowModal(false)
    setEditing(null)
  }

  const handleSave = async () => {
    if (!editing?.id || !editing?.name) return
    setSaving(true)
    try {
      await saveSchedule(editing)
      showSuccess('任务已保存')
      closeModal()
      await load()
    } catch (err) {
      showError('保存失败：' + friendlyError(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (t: ScheduleTask) => {
    const ok = window.confirm(
      `删除任务「${t.name}」？相关定时运行将停止。历史运行记录会保留。此操作无法撤销。`,
    )
    if (!ok) return
    try {
      await deleteSchedule(t.id)
      await load()
      showSuccess('任务已删除')
    } catch (err) {
      showError('删除失败：' + friendlyError(err))
    }
  }

  const handleRun = async (t: ScheduleTask) => {
    setRunning(prev => new Set(prev).add(t.id))
    setRecentStatus(prev => ({ ...prev, [t.id]: '正在运行' }))
    try {
      await runScheduleNow(t.id)
      setRecentStatus(prev => ({ ...prev, [t.id]: '已触发，稍后查看运行记录' }))
      showInfo(`任务「${t.name}」已触发，结果将写入运行记录`)
    } catch (err) {
      setRecentStatus(prev => ({ ...prev, [t.id]: '触发失败' }))
      showError('触发失败：' + friendlyError(err))
    } finally {
      setRunning(prev => {
        const next = new Set(prev)
        next.delete(t.id)
        return next
      })
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>自动任务</h1>
          <p>设置按计划自动运行的任务，例如每天定时生成摘要。</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={load} disabled={loading} type="button">
            {loading ? <span className="spinner" /> : '刷新'}
          </button>
          <button className="btn primary" onClick={openAdd} type="button">
            新增任务
          </button>
        </div>
      </div>

      {tasks.length === 0 ? (
        <div className="empty">
          <strong>暂无自动任务</strong>
          <p>你可以创建一个每日定时任务，让系统在指定时间自动运行摘要流程。</p>
        </div>
      ) : (
        <article className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>执行计划</th>
                  <th>类型</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map(t => (
                  <tr key={t.id}>
                    <td><strong>{t.name}</strong></td>
                    <td className="text-mono">{t.cron}</td>
                    <td>{TASK_TYPE_LABELS[t.task_type] ?? t.task_type}</td>
                    <td>
                      <span className={'badge ' + (t.enabled ? 'live' : '')}>
                        {t.enabled ? '启用' : '已停用'}
                      </span>
                      {recentStatus[t.id] && (
                        <div className="text-muted text-xs" style={{ marginTop: 4 }}>
                          {recentStatus[t.id]}
                        </div>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          className="btn"
                          style={{ minHeight: 32, fontSize: 11 }}
                          onClick={() => handleRun(t)}
                          disabled={running.has(t.id)}
                          type="button"
                        >
                          {running.has(t.id) ? <span className="spinner" /> : '立即运行'}
                        </button>
                        <button
                          className="btn"
                          style={{ minHeight: 32, fontSize: 11 }}
                          onClick={() => openEdit(t)}
                          type="button"
                        >
                          编辑
                        </button>
                        <button
                          className="btn ghost"
                          style={{ minHeight: 32, fontSize: 11 }}
                          onClick={() => handleDelete(t)}
                          type="button"
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      )}

      {showModal && editing && createPortal(
        <div
          className="modal-backdrop"
          onClick={e => {
            if (e.target === e.currentTarget) closeModal()
          }}
        >
          <div className="modal">
            <div className="modal-head">
              <strong>{editing.id.startsWith('task_') ? '新增任务' : '编辑任务'}</strong>
              <button className="btn icon-btn" onClick={closeModal} type="button">×</button>
            </div>
            <div className="modal-body">
              <div className="field">
                <label>任务名称</label>
                <input
                  className="input"
                  value={editing.name ?? ''}
                  onChange={e =>
                    setEditing(p => (p ? { ...p, name: e.target.value } : p))
                  }
                />
              </div>
              <div className="field">
                <label>任务类型</label>
                <select
                  className="input"
                  value={editing.task_type ?? ''}
                  onChange={e =>
                    setEditing(p => (p ? { ...p, task_type: e.target.value } : p))
                  }
                >
                  <option value="daily_digest">每日摘要</option>
                  <option value="ingestion">内容采集</option>
                </select>
              </div>
              <div className="field">
                <label>执行计划（常用预设）</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {PRESETS.map(p => (
                    <button
                      key={p.cron}
                      type="button"
                      className={'tab ' + (editing.cron === p.cron ? 'active' : '')}
                      onClick={() =>
                        setEditing(prev => (prev ? { ...prev, cron: p.cron } : prev))
                      }
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="field">
                <label>自定义 Cron 表达式（高级）</label>
                <input
                  className="input text-mono"
                  value={editing.cron ?? ''}
                  onChange={e =>
                    setEditing(p => (p ? { ...p, cron: e.target.value } : p))
                  }
                  placeholder="0 8 * * *"
                />
                <span className="text-muted text-xs">
                  格式：分 时 日 月 周。例如「0 8 * * *」表示每天 08:00。
                </span>
              </div>
              <div className="check-row">
                <input
                  type="checkbox"
                  checked={editing.enabled ?? false}
                  onChange={e =>
                    setEditing(p => (p ? { ...p, enabled: e.target.checked } : p))
                  }
                />
                <label>启用此任务</label>
              </div>
            </div>
            <div className="modal-foot">
              <button className="btn" onClick={closeModal} type="button">取消</button>
              <button
                className="btn primary"
                onClick={handleSave}
                disabled={saving}
                type="button"
              >
                {saving ? <span className="spinner" /> : '保存'}
              </button>
            </div>
          </div>
        </div>,
        document.body,
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
