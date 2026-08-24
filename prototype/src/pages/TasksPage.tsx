import { useEffect, useState, type FormEvent, type ReactElement } from 'react'
import { CalendarClock, CheckCircle2, CircleAlert, ListChecks, Play, Plus, RefreshCw } from 'lucide-react'
import { Modal } from '../components/Modal'
import { DataStatus } from '../components/DataStatus'
import { SectionHeading } from '../components/SectionHeading'
import { tasksApi, type JsonRecord } from '../services/api'
import { useLiveResource } from '../hooks/useLiveResource'
import type { ScheduleTask } from '../types'

// task_type is restricted on the backend — keep this aligned with
// multiscribe_agent/domain/models.py:ScheduleTask.task_type
const taskTypeOptions = [
  { value: 'daily_digest', label: '每日资讯（daily_digest）' },
  { value: 'adapter', label: '适配器采集（adapter）' },
  { value: 'agent_summary', label: 'Agent 摘要（agent_summary）' },
  { value: 'agent_deal', label: 'Agent 处理（agent_deal）' },
  { value: 'full_ingestion', label: '全量入库（full_ingestion）' },
] as const

const cronOptions = [
  { value: '0 9 * * *', label: '每天 09:00' },
  { value: '0 18 * * *', label: '每天 18:30（演示）' },
  { value: '0 */4 * * *', label: '每 4 小时' },
  { value: '*/30 * * * *', label: '每 30 分钟' },
  { value: '0 9 * * 1-5', label: '工作日 09:00' },
  { value: 'custom', label: '自定义 cron' },
] as const

function formatRelativeTime(iso: string | null): string {
  if (!iso) return '尚未运行'
  const value = Date.parse(iso)
  if (Number.isNaN(value)) return iso
  const diff = Math.max(0, Date.now() - value)
  const minutes = Math.round(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`
  return `${Math.round(minutes / 1440)} 天前`
}

function describeCron(cron: string): string {
  const hit = cronOptions.find((opt) => opt.value === cron)
  return hit ? hit.label : cron
}

function taskTypeLabel(value: string): string {
  return taskTypeOptions.find((opt) => opt.value === value)?.label ?? value
}

function statusTone(status: string | null | undefined): 'success' | 'running' | 'error' | 'pending' {
  if (status === 'success') return 'success'
  if (status === 'running') return 'running'
  if (status === 'error' || status === 'interrupted' || status === 'skipped') return 'error'
  return 'pending'
}

function statusLabel(status: string | null | undefined): string {
  switch (status) {
    case 'success': return '成功'
    case 'running': return '运行中'
    case 'error': return '失败'
    case 'interrupted': return '中断'
    case 'skipped': return '跳过'
    case null:
    case undefined:
    case '': return '等待中'
    default: return status
  }
}

interface MappedTask {
  id: string
  name: string
  taskType: string
  cron: string
  enabled: boolean
  config: Record<string, unknown>
  lastRun: string | null
  lastStatus: string | null
  lastError: string | null
  cronLabel: string
  lastRunRelative: string
}

function mapTask(task: ScheduleTask): MappedTask {
  return {
    id: task.id,
    name: task.name,
    taskType: task.task_type,
    cron: task.cron,
    enabled: task.enabled,
    config: task.config,
    lastRun: task.last_run ?? null,
    lastStatus: task.last_status ?? null,
    lastError: task.last_error ?? null,
    cronLabel: describeCron(task.cron),
    lastRunRelative: formatRelativeTime(task.last_run ?? null),
  }
}

export function TasksPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const remote = useLiveResource<JsonRecord[]>(() => tasksApi.list(), {
    cacheKey: 'schedules',
    events: ['task.updated', 'task.log'],
  })
  const tasks: MappedTask[] = ((remote.data ?? []) as unknown as ScheduleTask[]).map(mapTask)
  const loading = remote.loading && !remote.data
  const error = remote.error?.message ?? null
  const hasData = Boolean(remote.data)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (remote.replayed) onFlash('当前展示的是离线缓存，已尝试重新连接。')
  }, [remote.replayed, onFlash])

  const runNow = async (id: string): Promise<void> => {
    try {
      await tasksApi.run(id)
      onFlash(`已触发任务 ${id} 立即执行。`)
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '运行失败')
    }
  }

  const submitTask = async (input: NewTaskInput): Promise<void> => {
    try {
      const cron = input.cron === 'custom' ? input.customCron.trim() : input.cron
      if (!cron) {
        onFlash('请填写合法的 cron 表达式。')
        return
      }
      await tasksApi.create({
        id: `sched-${Date.now().toString(36)}`,
        name: input.name,
        task_type: input.taskType,
        cron,
        enabled: true,
        config: {
          tags: input.tags ? input.tags.split(',').map((tag) => tag.trim()).filter(Boolean) : [],
        },
      })
      setOpen(false)
      onFlash(`任务「${input.name}」已创建（${describeCron(cron)}）。`)
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '创建失败')
    }
  }

  return (
    <>
      <SectionHeading
        icon={<ListChecks />}
        title="任务调度"
        description="查看基于 cron 的定时任务、最近一次运行结果与可触发的立即执行。"
        actions={
          <>
            <button className="btn" type="button" onClick={() => void remote.reload()}>
              <RefreshCw /> 刷新
            </button>
            <button className="btn btn-primary" type="button" onClick={() => setOpen(true)}>
              <Plus /> 新建任务
            </button>
          </>
        }
      />

      <DataStatus
        loading={loading}
        error={error}
        empty={!hasData && !loading}
        emptyTitle="暂无任务"
        emptyDescription="配置调度后，任务会按计划自动运行。"
        onRetry={() => void remote.reload()}
      >
        <section className="section">
          <div className="data-table-card">
            <table className="data-table task-table">
              <thead>
                <tr>
                  <th>任务</th>
                  <th>类型</th>
                  <th>Cron</th>
                  <th>启用</th>
                  <th>最近状态</th>
                  <th>最近运行</th>
                  <th aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <tr key={task.id}>
                    <td className="data-table-primary">
                      <strong>{task.name}</strong>
                      <small>{task.id}</small>
                      {task.lastError && <small className="task-error">最近错误：{task.lastError}</small>}
                    </td>
                    <td><span className="pill pill-neutral">{taskTypeLabel(task.taskType)}</span></td>
                    <td>
                      <span className="task-cadence"><CalendarClock /> {task.cronLabel}</span>
                    </td>
                    <td>
                      <span className={task.enabled ? 'pill pill-builtin' : 'pill pill-neutral'}>
                        {task.enabled ? '已启用' : '已停用'}
                      </span>
                    </td>
                    <td><TaskStatusPill status={task.lastStatus} /></td>
                    <td>{task.lastRunRelative}</td>
                    <td className="task-row-actions">
                      <button
                        type="button"
                        className="btn btn-sm task-toggle"
                        onClick={() => void runNow(task.id)}
                      >
                        <Play /> 立即运行
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </DataStatus>

      <CreateTaskModal open={open} onClose={() => setOpen(false)} onSubmit={submitTask} />
    </>
  )
}

function TaskStatusPill({ status }: { status: string | null }): ReactElement {
  const tone = statusTone(status)
  if (tone === 'success') return <span className="run-pill run-pill-success"><CheckCircle2 /> 成功</span>
  if (tone === 'running') return <span className="run-pill run-pill-running"><span className="pulse-dot">●</span> 运行中</span>
  if (tone === 'error') return <span className="run-pill run-pill-error"><CircleAlert /> {statusLabel(status)}</span>
  return <span className="pill pill-neutral">○ 等待中</span>
}

interface NewTaskInput {
  name: string
  taskType: string
  cron: string
  customCron: string
  tags: string
}

function CreateTaskModal({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; onSubmit: (input: NewTaskInput) => Promise<void> | void }): ReactElement {
  const [name, setName] = useState('')
  const [taskType, setTaskType] = useState<string>(taskTypeOptions[0].value)
  const [cron, setCron] = useState<string>(cronOptions[0].value)
  const [customCron, setCustomCron] = useState('')
  const [tags, setTags] = useState('')

  const reset = (): void => {
    setName('')
    setTaskType(taskTypeOptions[0].value)
    setCron(cronOptions[0].value)
    setCustomCron('')
    setTags('')
  }

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    if (!name.trim()) return
    void onSubmit({ name: name.trim(), taskType, cron, customCron, tags: tags.trim() })
    reset()
  }

  return (
    <Modal
      open={open}
      onClose={() => { onClose(); reset() }}
      title="新建任务"
      description="任务会按 cron 表达式自动触发，并在失败时通过告警通知。"
      footer={
        <>
          <button className="btn" type="button" onClick={() => { onClose(); reset() }}>取消</button>
          <button className="btn btn-primary" type="submit" form="create-task-form">
            <Plus /> 创建任务
          </button>
        </>
      }
    >
      <form id="create-task-form" className="form-grid" onSubmit={submit}>
        <label className="form-field">
          <span>任务名称</span>
          <input
            type="text"
            placeholder="例如：每日资讯流水线"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoFocus
            required
          />
        </label>
        <label className="form-field">
          <span>任务类型</span>
          <select value={taskType} onChange={(event) => setTaskType(event.target.value)}>
            {taskTypeOptions.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>Cron 表达式</span>
          <select value={cron} onChange={(event) => setCron(event.target.value)}>
            {cronOptions.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </label>
        {cron === 'custom' && (
          <label className="form-field form-field-full">
            <span>自定义 Cron</span>
            <input
              type="text"
              placeholder="例如：0 9 * * 1-5"
              value={customCron}
              onChange={(event) => setCustomCron(event.target.value)}
              required
            />
            <small>使用标准 5 段 cron：分 时 日 月 周。</small>
          </label>
        )}
        <label className="form-field form-field-full">
          <span>标签</span>
          <input
            type="text"
            placeholder="多个标签请用逗号分隔"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
          />
          <small>会写入 ScheduleTask.config.tags，用于在后续版本中作为分组依据。</small>
        </label>
      </form>
    </Modal>
  )
}