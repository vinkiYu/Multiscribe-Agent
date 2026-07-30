/* Legacy page bodies are kept behavior-compatible during the module split. */
/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/no-unused-vars, no-empty, react-refresh/only-export-components */
import { useCallback, useEffect, useState, type ReactElement } from 'react'
import { Modal } from './dialog'
import { toast } from 'sonner'
import {
  Blocks,
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Eye,
  EyeOff,
  FileText,
  FolderPlus,
  Files,
  LibraryBig,
  ListChecks,
  Pencil,
  Plus,
  RadioTower,
  RefreshCw,
  Search,
  Send,
  Settings2,
  Tags,
  Trash2,
  Workflow,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import {
  ApiError,
  agentsApi,
  dailyNewsApi,
  dashboardApi,
  knowledgeApi,
  memoryApi,
  publishHistoryApi,
  schedulesApi,
  skillsApi,
  workflowsApi,
  type DailyNewsResponse,
  type DashboardStats,
  type AgentSummary,
  type KnowledgeCapabilities,
  type KnowledgeCategory,
  type KnowledgeDocument,
  type KnowledgeSearchHit,
  type MemoryEntry,
  type MemoryPreferences,
  type PublishHistoryRecord,
  type ScheduleTask,
  type SourceAdapterMetadata,
  type SourceConfigField,
  type SourceConfiguration,
  sourcesApi,
  settingsApi,
  type TaskLog,
  type WorkflowEvent,
  type WorkflowSummary,
  type WorkflowStep,
} from '../services/api'

function formatTaskName(log: TaskLog): string { return log.task_name || log.task_type?.replaceAll('_', ' ') || '后台任务' }
function formatDate(value?: string | null): string {
  if (!value) return '暂无记录'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', month: 'numeric', day: 'numeric' })
}
function formatUnix(value: number): string { return formatDate(new Date(value * 1000).toISOString()) }
function formatSchedule(cron: string): string {
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return '自定义时间'
  const [minute, hour, , , weekday] = parts
  if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) return '自定义时间'
  const time = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
  if (weekday === '*') return `每天 ${time}`
  const names: Record<string, string> = { '0': '星期日', '1': '星期一', '2': '星期二', '3': '星期三', '4': '星期四', '5': '星期五', '6': '星期六' }
  return names[weekday] ? `每周${names[weekday]} ${time}` : '自定义时间'
}
function statusClass(status?: string | null): string { return status === 'error' || status === 'failed' ? 'error' : status === 'running' ? 'running' : 'ready' }
function statusText(status?: string | null): string {
  const labels: Record<string, string> = { success: '成功', error: '失败', failed: '失败', running: '运行中', interrupted: '已中断', pending: '排队中' }
  return status ? labels[status] || status : '未知'
}

function Dashboard({ loading, stats, logs, error, onRetry }: { loading: boolean; stats: DashboardStats | null; logs: TaskLog[]; error: ApiError | null; onRetry: () => Promise<void> }): ReactElement {
  if (loading) return <LoadingState />
  if (error) return <ErrorState error={error} onRetry={onRetry} />
  if (!stats) return <ErrorState error={new ApiError('unknown', '未获得概览数据。')} onRetry={onRetry} />
  return <>
    <section className="metrics" aria-label="概览统计"><Metric label="已采集内容" value={stats.source_count} note="存储在本地数据库" icon={Files} tone="white" /><Metric label="已注册计划" value={stats.scheduled_tasks} note="由调度器按 Cron 执行" icon={ListChecks} tone="blue" /><Metric label="最近运行记录" value={logs.length} note="显示最近 8 条任务日志" icon={Workflow} tone="sun" /><Metric label="服务状态" value="正常" note="数据来自本地 API" icon={RadioTower} tone="pink" /></section>
    <section className="panel logs-panel"><PanelHeader title="最近任务" description="来自 /api/dashboard/logs 的持久化运行记录。" />{logs.length === 0 ? <EmptyInline text="还没有任务记录。配置数据源并运行计划任务后，执行过程会显示在这里。" /> : <div className="task-list">{logs.map((log) => <article key={log.id} className="task-row"><span className={`status-dot ${statusClass(log.status)}`} /><div><strong>{formatTaskName(log)}</strong><p>{log.message || statusText(log.status)}</p></div><time>{formatDate(log.finished_at ?? log.started_at ?? log.created_at)}</time></article>)}</div>}</section>
  </>
}

export interface RemoteData<T> { data: T | null; loading: boolean; error: ApiError | null; reload: () => Promise<void> }
function useRemoteData<T>(load: () => Promise<T>): RemoteData<T> {
  const [data, setData] = useState<T | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState<ApiError | null>(null)
  const reload = useCallback(async (): Promise<void> => { setLoading(true); setError(null); try { setData(await load()) } catch (caught) { setError(caught instanceof ApiError ? caught : new ApiError('unknown', '读取数据时发生未知错误。')) } finally { setLoading(false) } }, [load])
  useEffect(() => { void reload() }, [reload]); return { data, loading, error, reload }
}
function LoadingState(): ReactElement { return <section className="state-panel"><RefreshCw className="spin" /><h2>正在读取数据</h2><p>正在从本地服务加载最新记录。</p></section> }
function ErrorState({ error, onRetry }: { error: ApiError; onRetry: () => Promise<void> }): ReactElement { return <section className="state-panel error"><CircleAlert /><h2>数据暂时不可用</h2><p>{error.message}</p><button className="button blue" onClick={() => void onRetry()}><RefreshCw />重新连接</button></section> }
function DataStatus({ remote, empty }: { remote: RemoteData<unknown>; empty: boolean }): ReactElement | null { if (remote.loading) return <LoadingState />; if (remote.error) return <ErrorState error={remote.error} onRetry={remote.reload} />; return empty ? <section className="state-panel"><BookOpen /><h2>还没有可显示的数据</h2><p>完成相应配置或运行任务后，记录会显示在这里。</p></section> : null }
function EmptyInline({ text }: { text: string }): ReactElement { return <div className="empty-inline"><BookOpen /><p>{text}</p></div> }

function WorkflowsPage(): ReactElement {
  const remote = useRemoteData(loadWorkflowData)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [events, setEvents] = useState<WorkflowEvent[]>([])
  const [running, setRunning] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const status = DataStatus({ remote, empty: false })
  useEffect(() => { if (remote.data?.workflows.length && !remote.data.workflows.some((workflow) => workflow.id === selectedId)) setSelectedId(remote.data.workflows[0].id) }, [remote.data, selectedId])
  if (status) return status
  const data = remote.data!
  const selected = data.workflows.find((workflow) => workflow.id === selectedId) ?? null
  const run = async (): Promise<void> => {
    if (!selected) return
    setRunning(true); setEvents([])
    try { await workflowsApi.run(selected.id, input, (event) => setEvents((current) => [...current, event])); toast.success('工作流已结束。') } catch (caught) { toast.error(caught instanceof Error ? caught.message : '工作流执行失败。') } finally { setRunning(false) }
  }
  const remove = async (): Promise<void> => {
    if (!selected || !window.confirm(`删除“${selected.name}”？此操作不会删除其中引用的 Agent。`)) return
    try { await workflowsApi.remove(selected.id); setSelectedId(null); toast.success('工作流已删除。'); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '删除工作流失败。') }
  }
  return <div className="workflow-page"><header className="workflow-header"><div><h1>工作流</h1><p>把多个 Agent 按顺序或依赖关系串联起来。每个节点的输出会作为后续节点的输入，执行过程会实时显示。</p></div><button className="button pink" onClick={() => setCreateOpen(true)}><Plus />新建工作流</button></header><div className="workflow-layout"><aside className="workflow-list"><header><Workflow /><span>已保存工作流</span><b>{data.workflows.length}</b></header>{data.workflows.length ? data.workflows.map((workflow) => <button key={workflow.id} className={workflow.id === selected?.id ? 'active' : ''} onClick={() => { setSelectedId(workflow.id); setEvents([]) }}><strong>{workflow.name}</strong><small>{workflow.steps.length} 个节点</small></button>) : <EmptyInline text="还没有工作流。先选择 Agent 创建一个。" />}</aside>{selected ? <section className="workflow-detail"><header className="workflow-detail-header"><div><h2>{selected.name}</h2><p>{selected.description || '未填写工作流说明。'}</p></div><button className="icon-button danger-button" title="删除工作流" aria-label="删除工作流" onClick={() => void remove()}><Trash2 /></button></header><section className="workflow-canvas" aria-label="工作流节点图">{selected.steps.length ? selected.steps.map((step, index) => <div className="workflow-node-wrap" key={step.id}><article className={`workflow-node ${step.enabled === false ? 'disabled' : ''}`}><span>{index + 1}</span><div><strong>{step.name}</strong><small>{step.step_type === 'workflow' ? '嵌套工作流' : 'Agent 节点'}{step.enabled === false ? ' · 已停用' : ''}</small></div></article>{index < selected.steps.length - 1 && <ChevronRight className="workflow-arrow" />}</div>) : <EmptyInline text="这个工作流尚未添加节点。" />}</section><section className="workflow-run"><header><div><h3>运行工作流</h3><p>输入本次任务内容，系统会按节点顺序执行并返回实时事件。</p></div><button className="button blue" disabled={running || selected.steps.length === 0} onClick={() => void run()}><Workflow className={running ? 'spin' : ''} />{running ? '运行中…' : '开始运行'}</button></header><textarea value={input} placeholder="输入本次要处理的内容或任务要求" onChange={(event) => setInput(event.target.value)} disabled={running} />{events.length > 0 && <div className="workflow-events" aria-live="polite">{events.map((event, index) => <article key={`${event.type}-${index}`} className={event.type.includes('error') ? 'error' : event.type.includes('complete') ? 'complete' : ''}><strong>{workflowEventLabel(event.type)}</strong><span>{workflowEventMessage(event)}</span></article>)}</div>}</section></section> : <section className="workflow-empty"><Workflow /><h2>选择或新建工作流</h2><p>工作流将多个已注册的 Agent 连接为一次可重复执行的任务。</p></section>}</div>{createOpen && <WorkflowCreateDialog agents={data.agents} onClose={() => setCreateOpen(false)} onSaved={async (workflow) => { setCreateOpen(false); setSelectedId(workflow.id); toast.success('工作流已创建。'); await remote.reload() }} />}</div>
}

function workflowEventLabel(type: string): string { return ({ workflow_start: '开始执行', step_start: '节点开始', step_complete: '节点完成', step_error: '节点失败', loop_iteration: '质量检查', workflow_complete: '执行完成', workflow_error: '执行失败' }[type] ?? type) }
function workflowEventMessage(event: WorkflowEvent): string { const message = event.data.message; if (typeof message === 'string') return message; const step = event.data.step_id; if (typeof step === 'string') return `节点：${step}`; const final = event.data.final; return typeof final === 'string' ? final.slice(0, 240) : '已收到执行事件。' }

function WorkflowCreateDialog({ agents, onClose, onSaved }: { agents: AgentSummary[]; onClose: () => void; onSaved: (workflow: WorkflowSummary) => Promise<void> }): ReactElement {
  const [name, setName] = useState(''); const [description, setDescription] = useState(''); const [agentIds, setAgentIds] = useState<string[]>(agents[0] ? [agents[0].id] : []); const [saving, setSaving] = useState(false); const [error, setError] = useState('')
  const addNode = (): void => { if (agents[0]) setAgentIds((current) => [...current, agents[0].id]) }
  const updateNode = (index: number, agentId: string): void => setAgentIds((current) => current.map((value, position) => position === index ? agentId : value))
  const submit = async (): Promise<void> => { if (!name.trim()) { setError('请填写工作流名称。'); return }; if (!agentIds.length) { setError('请至少选择一个 Agent 节点。'); return }; setSaving(true); setError(''); const steps: WorkflowStep[] = agentIds.map((agentId, index) => ({ id: `step-${index + 1}`, name: agents.find((agent) => agent.id === agentId)?.name || `节点 ${index + 1}`, step_type: 'agent', agent_id: agentId, enabled: true, next_step_id: index < agentIds.length - 1 ? `step-${index + 2}` : null })); try { const workflow = await workflowsApi.save({ id: `workflow-${Date.now()}`, name: name.trim(), description: description.trim(), steps }); await onSaved(workflow) } catch (caught) { setError(caught instanceof Error ? caught.message : '创建工作流失败。') } finally { setSaving(false) } }
  return <Modal.Root open onOpenChange={(open) => { if (!open) onClose() }}><Modal.Overlay className="modal-backdrop" /><Modal.Content className="task-modal workflow-dialog" aria-labelledby="workflow-create-title"><header><div><h2 id="workflow-create-title">新建工作流</h2><p>选择已有 Agent，系统会按添加顺序连接这些处理节点。</p></div><button className="icon-button" aria-label="关闭" onClick={onClose}><X /></button></header><div className="task-modal-body"><label>工作流名称<input value={name} placeholder="例如：每日资讯精选" onChange={(event) => setName(event.target.value)} /></label><label>说明（可选）<textarea value={description} placeholder="说明这条工作流负责处理什么任务" onChange={(event) => setDescription(event.target.value)} /></label><div className="workflow-step-editor"><div><strong>处理节点</strong><button type="button" className="button compact" disabled={!agents.length} onClick={addNode}><Plus />添加节点</button></div>{agentIds.map((agentId, index) => <label key={`${index}-${agentId}`}>第 {index + 1} 步<select value={agentId} onChange={(event) => updateNode(index, event.target.value)}>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select><button type="button" className="icon-button danger-button" title="删除节点" aria-label="删除节点" disabled={agentIds.length === 1} onClick={() => setAgentIds((current) => current.filter((_, position) => position !== index))}><Trash2 /></button></label>)}{!agents.length && <p>当前没有可用 Agent，请先完成 Agent 配置后再创建工作流。</p>}</div>{error && <p className="source-form-error" role="alert">{error}</p>}</div><footer><button className="button" onClick={onClose}>取消</button><button className="button pink" disabled={saving || !agents.length} onClick={() => void submit()}><CheckCircle2 />{saving ? '创建中…' : '创建工作流'}</button></footer></Modal.Content></Modal.Root>
}

function ContentPage(): ReactElement {
  const [date, setDate] = useState<string | null>(null)
  const loadContent = useCallback(() => date ? dailyNewsApi.byDate(date) : dailyNewsApi.latest(), [date])
  const remote = useRemoteData(loadContent); const status = DataStatus({ remote, empty: remote.data?.digest === null })
  if (status) return status; const data: DailyNewsResponse = remote.data!; const digest = data.digest!
  return <div className="data-stack"><section className="data-panel"><div className="data-summary"><Files /><span>{digest.title}</span><time className="row-meta">更新于 {formatDate(digest.updated_at)}</time></div><p className="capability-note">扫描 {digest.total_scanned} 条候选内容，最终保留 {digest.items.length} 条。{digest.summary}</p></section><section className="data-panel"><div className="data-summary"><Tags /><span>日报归档</span><select className="select-control" value={date ?? digest.date} onChange={(event) => setDate(event.target.value)} aria-label="选择日报日期">{data.archives.map((archive) => <option key={archive.date} value={archive.date}>{archive.date}，{archive.item_count} 条</option>)}</select></div><div className="data-list">{digest.items.map((item) => <article className="data-row" key={item.url}><div><a className="content-link" href={item.url} target="_blank" rel="noreferrer"><strong>{item.title}</strong></a><p>{item.summary}</p><div className="tag-list">{item.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div></div><span className="row-meta">{item.source}</span><span className="score">{item.score === null ? '未评分' : `${item.score.toFixed(1)} 分`}</span></article>)}</div></section></div>
}

function PublishingPage(): ReactElement {
  const remote = useRemoteData(publishHistoryApi.list); const status = DataStatus({ remote, empty: remote.data?.length === 0 })
  if (status) return status; const records = remote.data ?? []
  return <section className="data-panel"><div className="data-summary"><Send /><span>最近 {records.length} 条投递记录</span></div><div className="data-list">{records.map((record: PublishHistoryRecord) => <article className="data-row" key={record.id}><div><strong>{record.title || '未命名发布内容'}</strong><p>{record.error_message || record.content_preview || '已记录发布结果。'}</p></div><span className={`status-label ${statusClass(record.status)}`}>{statusText(record.status)}</span><time>{record.publisher_id} · {formatDate(record.published_at)}</time></article>)}</div></section>
}

function TasksPage({ createOpen, onCreateClose }: { createOpen: boolean; onCreateClose: () => void }): ReactElement {
  const remote = useRemoteData(loadTaskData); const [runningId, setRunningId] = useState<string | null>(null); const [editingTask, setEditingTask] = useState<ScheduleTask | null>(null); const status = DataStatus({ remote, empty: Boolean(remote.data && remote.data.schedules.length + remote.data.logs.length === 0) })
  const runNow = async (task: ScheduleTask): Promise<void> => { if (!window.confirm(`立即运行“${task.name}”？这会执行该计划任务，并可能向已配置渠道发布内容。`)) return; setRunningId(task.id); try { await schedulesApi.run(task.id); toast.success(`已提交“${task.name}”，请稍后刷新查看运行记录。`); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '任务启动失败。') } finally { setRunningId(null) } }
  const toggleTask = async (task: ScheduleTask): Promise<void> => { try { await schedulesApi.create({ ...task, enabled: !task.enabled }); toast.success(task.enabled ? '任务已停用' : '任务已启用'); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '任务状态更新失败。') } }
  const deleteTask = async (task: ScheduleTask): Promise<void> => { if (!window.confirm(`删除“${task.name}”？此操作会停止后续调度。`)) return; try { await schedulesApi.remove(task.id); toast.success('任务已删除'); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '删除任务失败。') } }
  if (status) return status; const data = remote.data ?? { schedules: [], logs: [] }
  return <div className="data-stack task-management"><section className="data-panel task-table-panel"><div className="data-summary"><ListChecks /><span>调度列表</span><span className="row-meta">{data.schedules.length} 个计划</span></div>{data.schedules.length === 0 ? <EmptyInline text="尚未创建计划任务。" /> : <div className="schedule-table"><div className="schedule-head"><span>任务名称</span><span>执行时间</span><span>类型</span><span>上次运行</span><span>状态</span><span>操作</span></div>{data.schedules.map((task) => <article className="schedule-row" key={task.id}><div><strong>{task.name}</strong><small>{task.last_error ? `最近错误：${task.last_error}` : task.id}</small></div><span className="schedule-time">{formatSchedule(task.cron)}</span><span className="schedule-type">{task.task_type}</span><time>{formatDate(task.last_run)}</time><label className="task-switch"><input type="checkbox" checked={task.enabled} onChange={() => void toggleTask(task)} /><span>{task.enabled ? '已启用' : '已停用'}</span></label><div className="task-row-tools"><button className="button compact" title="立即运行" disabled={!task.enabled || runningId === task.id} onClick={() => void runNow(task)}>{runningId === task.id ? '启动中' : '运行'}</button><button className="icon-button" title="编辑任务" aria-label="编辑任务" onClick={() => setEditingTask(task)}><Pencil /></button><button className="icon-button danger-button" title="删除任务" aria-label="删除任务" onClick={() => void deleteTask(task)}><Trash2 /></button></div></article>)}</div>}</section><section className="data-panel task-table-panel"><div className="data-summary"><FileText /><span>运行记录</span><span className="row-meta">最近 {data.logs.length} 条</span></div>{data.logs.length === 0 ? <EmptyInline text="还没有运行记录。" /> : <div className="run-table"><div className="run-head"><span>任务</span><span>开始时间</span><span>状态</span><span>消息</span></div>{data.logs.map((log) => <article className="run-row" key={log.id}><strong>{formatTaskName(log)}</strong><time>{formatDate(log.started_at ?? log.created_at)}</time><span className={`status-label ${statusClass(log.status)}`}>{statusText(log.status)}</span><p>{log.message || '暂无运行消息'}</p></article>)}</div>}</section>{createOpen && <CreateTaskDialog onClose={onCreateClose} onSaved={async (task) => { await schedulesApi.create(task); onCreateClose(); toast.success('计划任务已创建'); await remote.reload() }} />}{editingTask && <EditTaskDialog task={editingTask} onClose={() => setEditingTask(null)} onSaved={async (task) => { await schedulesApi.create(task); setEditingTask(null); toast.success('任务已更新'); await remote.reload() }} />}</div>
}

function EditTaskDialog({ task, onClose, onSaved }: { task: ScheduleTask; onClose: () => void; onSaved: (task: ScheduleTask) => Promise<void> }): ReactElement {
  const cronParts = task.cron.trim().split(/\s+/); const initialTime = cronParts.length === 5 ? `${(cronParts[1] ?? '9').padStart(2, '0')}:${(cronParts[0] ?? '0').padStart(2, '0')}` : '09:00'; const initialWeekly = cronParts.length === 5 && cronParts[4] !== '*'
  const [name, setName] = useState(task.name); const [frequency, setFrequency] = useState<'daily' | 'weekly'>(initialWeekly ? 'weekly' : 'daily'); const [time, setTime] = useState(initialTime); const [weekday, setWeekday] = useState(cronParts[4] ?? '1'); const [taskType, setTaskType] = useState<ScheduleTask['task_type']>(task.task_type); const [topN, setTopN] = useState(String(task.config.top_n ?? 5)); const [fetchDays, setFetchDays] = useState(String(task.config.fetch_days ?? 2)); const [delivery, setDelivery] = useState(Array.isArray(task.config.targets) && task.config.targets[0] === 'wecom_bot' ? 'wecom_bot' : Array.isArray(task.config.targets) && task.config.targets.length === 0 ? 'none' : 'feishu_bot'); const [enabled, setEnabled] = useState(task.enabled); const [saving, setSaving] = useState(false)
  const submit = async (): Promise<void> => { if (!name.trim()) return; const [hour, minute] = time.split(':'); if (hour === undefined || minute === undefined) return; const cron = frequency === 'daily' ? `${Number(minute)} ${Number(hour)} * * *` : `${Number(minute)} ${Number(hour)} * * ${weekday}`; const config = taskType === 'daily_digest' ? { ...task.config, curate_agent_id: String(task.config.curate_agent_id ?? 'default-curation-agent'), adapter_ids: Array.isArray(task.config.adapter_ids) ? task.config.adapter_ids : ['rss'], top_n: Number(topN), fetch_days: Number(fetchDays), targets: delivery === 'none' ? [] : [delivery] } : task.config; setSaving(true); try { await onSaved({ ...task, name: name.trim(), task_type: taskType, cron, enabled, config }) } finally { setSaving(false) } }
  return <Modal.Root open onOpenChange={(open) => { if (!open) onClose() }}><Modal.Overlay className="modal-backdrop" /><Modal.Content className="task-modal" aria-labelledby="edit-task-title"><header><div><h2 id="edit-task-title">编辑任务</h2><p>调整任务的执行时间、内容范围和发布方式。</p></div><button className="icon-button" aria-label="关闭" onClick={onClose}><X /></button></header><div className="task-modal-body"><label>任务名称<input value={name} onChange={(event) => setName(event.target.value)} /></label><div className="schedule-input-row"><label>执行频率<select value={frequency} onChange={(event) => setFrequency(event.target.value as 'daily' | 'weekly')}><option value="daily">每天</option><option value="weekly">每周</option></select></label>{frequency === 'weekly' && <label>星期<select value={weekday} onChange={(event) => setWeekday(event.target.value)}><option value="1">星期一</option><option value="2">星期二</option><option value="3">星期三</option><option value="4">星期四</option><option value="5">星期五</option><option value="6">星期六</option><option value="0">星期日</option></select></label>}<label>执行时间<input type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label></div><label>任务类型<select value={taskType} onChange={(event) => setTaskType(event.target.value as ScheduleTask['task_type'])}><option value="daily_digest">每日资讯推送</option><option value="full_ingestion">全量采集</option><option value="adapter">适配器采集</option><option value="agent_summary">Agent 摘要</option><option value="agent_deal">Agent 处理</option></select></label>{taskType === 'daily_digest' && <div className="digest-options"><label>每天保留几条资讯<select value={topN} onChange={(event) => setTopN(event.target.value)}><option value="3">3 条</option><option value="5">5 条</option><option value="10">10 条</option><option value="15">15 条</option></select></label><label>回看最近多久的内容<select value={fetchDays} onChange={(event) => setFetchDays(event.target.value)}><option value="1">最近 1 天</option><option value="2">最近 2 天</option><option value="3">最近 3 天</option><option value="7">最近 7 天</option></select></label><label>发送到哪里<select value={delivery} onChange={(event) => setDelivery(event.target.value)}><option value="feishu_bot">飞书群机器人</option><option value="wecom_bot">企业微信群机器人</option><option value="none">暂不自动发送</option></select></label></div>}<label className="dialog-check"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />启用此任务</label></div><footer><button className="button" onClick={onClose}>取消</button><button className="button pink" disabled={saving} onClick={() => void submit()}><CheckCircle2 />{saving ? '保存中…' : '保存修改'}</button></footer></Modal.Content></Modal.Root>
  return <Modal.Root open onOpenChange={(open) => { if (!open) onClose() }}><Modal.Overlay className="modal-backdrop" /><Modal.Content className="task-modal compact-modal" aria-labelledby="edit-task-title"><header><div><h2 id="edit-task-title">编辑任务</h2><p>修改任务名称或启用状态。</p></div><button className="icon-button" aria-label="关闭" onClick={onClose}><X /></button></header><div className="task-modal-body"><label>任务名称<input value={name} onChange={(event) => setName(event.target.value)} /></label><div className="task-readonly"><span>执行时间</span><strong>{formatSchedule(task.cron)}</strong></div><div className="task-readonly"><span>任务类型</span><strong>{task.task_type}</strong></div><label className="dialog-check"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />启用此任务</label></div><footer><button className="button" onClick={onClose}>取消</button><button className="button pink" disabled={saving} onClick={() => void submit()}><CheckCircle2 />{saving ? '保存中…' : '保存修改'}</button></footer></Modal.Content></Modal.Root>
}

function CreateTaskDialog({ onClose, onSaved }: { onClose: () => void; onSaved: (task: ScheduleTask) => Promise<void> }): ReactElement {
  const [name, setName] = useState(''); const [frequency, setFrequency] = useState<'daily' | 'weekly'>('daily'); const [time, setTime] = useState('09:00'); const [weekday, setWeekday] = useState('1'); const [taskType, setTaskType] = useState<ScheduleTask['task_type']>('daily_digest'); const [topN, setTopN] = useState('5'); const [fetchDays, setFetchDays] = useState('2'); const [delivery, setDelivery] = useState('feishu_bot'); const [enabled, setEnabled] = useState(true); const [config, setConfig] = useState(''); const [error, setError] = useState(''); const [saving, setSaving] = useState(false)
  const submit = async (): Promise<void> => { setError(''); let parsed: Record<string, unknown>; try { parsed = config.trim() ? JSON.parse(config) as Record<string, unknown> : {} } catch { setError('高级设置的内容格式不正确，请清空它后按默认设置运行。'); return } if (!name.trim()) { setError('请填写任务名称。'); return } const [hour, minute] = time.split(':'); if (hour === undefined || minute === undefined) { setError('请选择执行时间。'); return } const cron = frequency === 'daily' ? `${Number(minute)} ${Number(hour)} * * *` : `${Number(minute)} ${Number(hour)} * * ${weekday}`; const taskConfig = taskType === 'daily_digest' ? { curate_agent_id: 'default-curation-agent', adapter_ids: ['rss'], fetch_days: Number(fetchDays), top_n: Number(topN), targets: delivery === 'none' ? [] : [delivery], ...parsed } : parsed; setSaving(true); try { await onSaved({ id: `task-${Date.now()}`, name: name.trim(), task_type: taskType, cron, enabled, config: taskConfig }) } catch (caught) { setError(caught instanceof Error ? caught.message : '创建任务失败。') } finally { setSaving(false) } }
  return <Modal.Root open onOpenChange={(open) => { if (!open) onClose() }}><Modal.Overlay className="modal-backdrop" /><Modal.Content className="task-modal" aria-labelledby="create-task-title"><header><div><h2 id="create-task-title">新增任务</h2><p>选择执行频率和时间，系统会自动安排任务。</p></div><button className="icon-button" aria-label="关闭" onClick={onClose}><X /></button></header><div className="task-modal-body"><label>任务名称<input value={name} placeholder="例如：每日 AI 资讯" onChange={(event) => setName(event.target.value)} /></label><div className="schedule-input-row"><label>执行频率<select value={frequency} onChange={(event) => setFrequency(event.target.value as 'daily' | 'weekly')}><option value="daily">每天</option><option value="weekly">每周</option></select></label>{frequency === 'weekly' && <label>星期<select value={weekday} onChange={(event) => setWeekday(event.target.value)}><option value="1">星期一</option><option value="2">星期二</option><option value="3">星期三</option><option value="4">星期四</option><option value="5">星期五</option><option value="6">星期六</option><option value="0">星期日</option></select></label>}<label>执行时间<input type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label></div><label>任务类型<select value={taskType} onChange={(event) => setTaskType(event.target.value as ScheduleTask['task_type'])}><option value="daily_digest">每日资讯推送</option><option value="full_ingestion">全量采集</option><option value="adapter">适配器采集</option><option value="agent_summary">Agent 摘要</option><option value="agent_deal">Agent 处理</option></select></label>{taskType === 'daily_digest' && <div className="digest-options"><label>每天保留几条资讯<select value={topN} onChange={(event) => setTopN(event.target.value)}><option value="3">3 条</option><option value="5">5 条</option><option value="10">10 条</option><option value="15">15 条</option></select></label><label>回看最近多久的内容<select value={fetchDays} onChange={(event) => setFetchDays(event.target.value)}><option value="1">最近 1 天</option><option value="2">最近 2 天</option><option value="3">最近 3 天</option><option value="7">最近 7 天</option></select></label><label>发送到哪里<select value={delivery} onChange={(event) => setDelivery(event.target.value)}><option value="feishu_bot">飞书群机器人</option><option value="wecom_bot">企业微信群机器人</option><option value="none">暂不自动发送</option></select></label></div>}<label className="dialog-check"><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />启用此任务</label><details className="advanced-task-options"><summary>高级设置（可选）</summary><p>没有特殊需求时无需填写，系统会按默认设置运行。</p><label>额外规则<textarea value={config} placeholder="留空即可" spellCheck={false} onChange={(event) => setConfig(event.target.value)} /></label></details>{error && <p className="source-form-error" role="alert">{error}</p>}</div><footer><button className="button" onClick={onClose}>取消</button><button className="button pink" disabled={saving} onClick={() => void submit()}><CheckCircle2 />{saving ? '保存中…' : '保存配置'}</button></footer></Modal.Content></Modal.Root>
}

function KnowledgePage(): ReactElement {
  const remote = useRemoteData(loadKnowledgeData)
  const [categoryId, setCategoryId] = useState('')
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<KnowledgeSearchHit[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [textDialogOpen, setTextDialogOpen] = useState(false)
  const [categoryDialogOpen, setCategoryDialogOpen] = useState(false)
  const status = DataStatus({ remote, empty: false })
  if (status) return status
  const data = remote.data!
  const visibleDocuments = categoryId ? data.documents.filter((document) => document.category_id === categoryId) : data.documents
  const categoryNames = new Map(data.categories.map((category) => [category.id, category.name]))
  const search = async (): Promise<void> => {
    const normalized = query.trim()
    if (!normalized) { setHits(null); return }
    setSearching(true)
    try { setHits((await knowledgeApi.search(normalized, categoryId || undefined)).hits) } catch (caught) { toast.error(caught instanceof Error ? caught.message : '检索失败') } finally { setSearching(false) }
  }
  const removeDocument = async (document: KnowledgeDocument): Promise<void> => {
    if (!window.confirm(`删除“${document.name}”及其检索内容？`)) return
    try { await knowledgeApi.remove(document.id); toast.success('文档已删除'); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '删除失败') }
  }
  return <div className="knowledge-page"><header className="knowledge-header"><div><h1>知识库</h1><p>沉淀可检索的业务资料，为后续 Agent 任务按需提供上下文。</p></div><div className="header-actions"><button className="button" onClick={() => setCategoryDialogOpen(true)}><FolderPlus />新建分类</button><button className="button pink" onClick={() => setTextDialogOpen(true)}><Plus />添加知识</button></div></header><section className="knowledge-search"><Search /><input value={query} placeholder="搜索知识库中的内容" onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void search() }} /><button className="button blue" disabled={searching} onClick={() => void search()}>{searching ? '检索中…' : '检索'}</button></section><div className="knowledge-layout"><aside className="knowledge-categories"><div className="knowledge-side-title"><LibraryBig /><span>知识分类</span></div><button className={!categoryId ? 'active' : ''} onClick={() => { setCategoryId(''); setHits(null) }}><span>全部知识</span><b>{data.documents.length}</b></button>{data.categories.map((category) => <button key={category.id} className={categoryId === category.id ? 'active' : ''} onClick={() => { setCategoryId(category.id); setHits(null) }}><span>{category.name}</span><b>{category.document_count}</b></button>)}</aside><div className="knowledge-content"><section className="knowledge-capabilities"><div><strong>检索能力</strong><span>全文检索 {data.capabilities.fts ? '已启用' : '未启用'}，语义检索 {data.capabilities.vector ? '已启用' : '未启用'}</span></div><span className={`status-label ${data.capabilities.degraded ? 'error' : 'ready'}`}>{data.capabilities.degraded ? '降级模式' : '可用'}</span></section>{hits ? <section className="knowledge-results"><header><strong>检索结果</strong><span>{hits.length} 条匹配内容</span></header>{hits.length ? hits.map((hit) => <article key={hit.chunk_id}><p>{hit.content}</p><small>{categoryNames.get(data.documents.find((document) => document.id === hit.document_id)?.category_id || '') || '未分类'} · {hit.source}</small></article>) : <EmptyInline text="没有找到匹配的知识内容。" />}</section> : <section className="knowledge-documents"><header><strong>{categoryId ? categoryNames.get(categoryId) : '全部知识'}</strong><span>{visibleDocuments.length} 个文档</span></header>{visibleDocuments.length ? <div className="data-list">{visibleDocuments.map((document) => <article className="data-row knowledge-document-row" key={document.id}><div><strong>{document.name}</strong><p>{document.summary || document.file_name}</p></div><span className="row-meta">{categoryNames.get(document.category_id) || '未分类'} · {document.chunk_count} 段</span><div className="knowledge-row-actions"><time>{formatUnix(document.updated_at)}</time><button className="icon-button danger-button" title="删除文档" aria-label={`删除 ${document.name}`} onClick={() => void removeDocument(document)}><Trash2 /></button></div></article>)}</div> : <EmptyInline text="该分类还没有知识内容。" />}</section>}</div></div>{textDialogOpen && <KnowledgeTextDialog categories={data.categories} onClose={() => setTextDialogOpen(false)} onSaved={async () => { setTextDialogOpen(false); toast.success('知识已加入知识库'); await remote.reload() }} />}{categoryDialogOpen && <KnowledgeCategoryDialog onClose={() => setCategoryDialogOpen(false)} onSaved={async () => { setCategoryDialogOpen(false); toast.success('分类已创建'); await remote.reload() }} />}</div>
}

function KnowledgeTextDialog({ categories, onClose, onSaved }: { categories: KnowledgeCategory[]; onClose: () => void; onSaved: () => Promise<void> }): ReactElement {
  const [name, setName] = useState(''); const [categoryId, setCategoryId] = useState(categories[0]?.id ?? ''); const [summary, setSummary] = useState(''); const [text, setText] = useState(''); const [saving, setSaving] = useState(false); const [error, setError] = useState('')
  const submit = async (): Promise<void> => { if (!categoryId) { setError('请先创建并选择一个知识分类。'); return } setSaving(true); setError(''); try { await knowledgeApi.ingestText({ name, category_id: categoryId, summary, text }); await onSaved() } catch (caught) { setError(caught instanceof Error ? caught.message : '保存失败') } finally { setSaving(false) } }
  return <Modal.Root open onOpenChange={(open) => { if (!open) onClose() }}><Modal.Overlay className="modal-backdrop" /><Modal.Content className="task-modal knowledge-modal" aria-labelledby="knowledge-text-title"><header><div><h2 id="knowledge-text-title">添加知识</h2><p>录入文本后，系统会自动切分并建立检索索引。</p></div><button className="icon-button" aria-label="关闭" onClick={onClose}><X /></button></header><div className="task-modal-body"><label>知识名称<input value={name} placeholder="例如：日报写作规范" onChange={(event) => setName(event.target.value)} /></label><label>所属分类<select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><label>简要说明（可选）<input value={summary} placeholder="便于日后识别这条知识的用途" onChange={(event) => setSummary(event.target.value)} /></label><label>知识内容<textarea value={text} placeholder="粘贴需要沉淀的规则、资料或说明" onChange={(event) => setText(event.target.value)} /></label>{error && <p className="source-form-error" role="alert">{error}</p>}</div><footer><button className="button" onClick={onClose}>取消</button><button className="button pink" disabled={saving} onClick={() => void submit()}><CheckCircle2 />{saving ? '保存中…' : '加入知识库'}</button></footer></Modal.Content></Modal.Root>
}

function KnowledgeCategoryDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }): ReactElement {
  const [name, setName] = useState(''); const [description, setDescription] = useState(''); const [saving, setSaving] = useState(false); const [error, setError] = useState('')
  const submit = async (): Promise<void> => { setSaving(true); setError(''); try { await knowledgeApi.createCategory({ name, description }); await onSaved() } catch (caught) { setError(caught instanceof Error ? caught.message : '创建失败') } finally { setSaving(false) } }
  return <Modal.Root open onOpenChange={(open) => { if (!open) onClose() }}><Modal.Overlay className="modal-backdrop" /><Modal.Content className="task-modal" aria-labelledby="knowledge-category-title"><header><div><h2 id="knowledge-category-title">新建知识分类</h2><p>按主题组织资料，便于检索和管理。</p></div><button className="icon-button" aria-label="关闭" onClick={onClose}><X /></button></header><div className="task-modal-body"><label>分类名称<input value={name} placeholder="例如：产品资料" onChange={(event) => setName(event.target.value)} /></label><label>分类说明（可选）<textarea value={description} placeholder="说明这个分类适合存放什么内容" onChange={(event) => setDescription(event.target.value)} /></label>{error && <p className="source-form-error" role="alert">{error}</p>}</div><footer><button className="button" onClick={onClose}>取消</button><button className="button pink" disabled={saving} onClick={() => void submit()}><CheckCircle2 />{saving ? '创建中…' : '创建分类'}</button></footer></Modal.Content></Modal.Root>
}

function MemoryPage(): ReactElement {
  const remote = useRemoteData(loadMemoryData)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<MemoryEntry[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [entryDialogOpen, setEntryDialogOpen] = useState(false)
  const [preferenceDialogOpen, setPreferenceDialogOpen] = useState(false)
  const status = DataStatus({ remote, empty: false })
  if (status) return status
  const data = remote.data!
  const entries = results ?? data.entries
  const search = async (): Promise<void> => {
    if (!query.trim()) { setResults(null); return }
    setSearching(true)
    try { setResults(await memoryApi.search(query.trim())) } catch (caught) { toast.error(caught instanceof Error ? caught.message : '搜索记忆失败。') } finally { setSearching(false) }
  }
  const remove = async (entry: MemoryEntry): Promise<void> => {
    if (!window.confirm('删除这条长期记忆？后续任务将不再参考它。')) return
    try { await memoryApi.remove(entry.id); setResults(null); toast.success('记忆已删除。'); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '删除记忆失败。') }
  }
  const extract = async (): Promise<void> => {
    setExtracting(true)
    try { const result = await memoryApi.extractFromHistory(30); toast.success(result.extracted ? `已从近期发布记录整理出 ${result.extracted} 条新记忆。` : '近期发布记录中没有新的可整理记忆。'); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '整理发布记录失败。') } finally { setExtracting(false) }
  }
  return <div className="memory-page">
    <header className="memory-header"><div><h1>记忆</h1><p>保存长期偏好和重要结论。系统会在后续资讯筛选时按需检索这些内容，不会把全部历史直接交给模型。</p></div><div className="header-actions"><button className="button" disabled={extracting} onClick={() => void extract()}><RefreshCw className={extracting ? 'spin' : ''} />{extracting ? '整理中…' : '整理发布记录'}</button><button className="button pink" onClick={() => setEntryDialogOpen(true)}><Plus />新增记忆</button></div></header>
    <section className="memory-preference-card"><header><div><BrainCircuit /><div><h2>内容偏好</h2><p>用于影响每日资讯的筛选方向和发送规则。</p></div></div><button className="button compact" onClick={() => setPreferenceDialogOpen(true)}><Pencil />编辑偏好</button></header><div className="memory-preference-grid"><PreferenceValue label="关注主题" value={data.preferences.preferred_tags.join('、') || '暂未设置'} /><PreferenceValue label="不看来源" value={data.preferences.block_sources.join('、') || '暂未设置'} /><PreferenceValue label="不看主题" value={data.preferences.blocked_topics.join('、') || '暂未设置'} /><PreferenceValue label="发送时间与筛选标准" value={`${data.preferences.push_time} · 重要程度不低于 ${data.preferences.importance_threshold}/10`} /></div></section>
    <section className="memory-library"><div className="memory-library-toolbar"><div><h2>长期记忆</h2><span>{results ? `搜索到 ${entries.length} 条匹配记忆` : `共 ${data.entries.length} 条记忆`}</span></div><div className="memory-search"><Search /><input value={query} placeholder="搜索已保存的偏好或结论" onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void search() }} /><button className="button blue" disabled={searching} onClick={() => void search()}>{searching ? '搜索中…' : '搜索'}</button></div></div>{entries.length ? <div className="memory-entry-list">{entries.map((entry) => <article className="memory-entry" key={entry.id}><div className="memory-entry-main"><p>{entry.content}</p><div className="tag-list">{entry.tags.length ? entry.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>) : <span className="memory-no-tag">未添加标签</span>}</div></div><div className="memory-entry-meta"><span className="importance-badge">重要程度 {entry.importance}/10</span><time>{formatUnix(entry.created_at)}</time><button className="icon-button danger-button" title="删除记忆" aria-label="删除记忆" onClick={() => void remove(entry)}><Trash2 /></button></div></article>)}</div> : <EmptyInline text={results ? '没有找到匹配的记忆。请更换关键词，或清空搜索后查看全部内容。' : '还没有长期记忆。可以手动新增，或从近期发布记录中整理。'} />}</section>
    {entryDialogOpen && <MemoryEntryDialog onClose={() => setEntryDialogOpen(false)} onSaved={async () => { setEntryDialogOpen(false); toast.success('记忆已保存。'); await remote.reload() }} />}
    {preferenceDialogOpen && <MemoryPreferenceDialog preferences={data.preferences} onClose={() => setPreferenceDialogOpen(false)} onSaved={async () => { setPreferenceDialogOpen(false); toast.success('内容偏好已保存。'); await remote.reload() }} />}
  </div>
}

function PreferenceValue({ label, value }: { label: string; value: string }): ReactElement { return <div><span>{label}</span><strong>{value}</strong></div> }

function MemoryEntryDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }): ReactElement {
  const [content, setContent] = useState(''); const [tags, setTags] = useState(''); const [importance, setImportance] = useState('5'); const [saving, setSaving] = useState(false); const [error, setError] = useState('')
  const submit = async (): Promise<void> => { if (!content.trim()) { setError('请填写希望长期保存的内容。'); return }; setSaving(true); setError(''); try { await memoryApi.create({ content: content.trim(), importance: Number(importance), tags: tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean) }); await onSaved() } catch (caught) { setError(caught instanceof Error ? caught.message : '保存记忆失败。') } finally { setSaving(false) } }
  return <Modal.Root open onOpenChange={(open) => { if (!open) onClose() }}><Modal.Overlay className="modal-backdrop" /><Modal.Content className="task-modal memory-dialog" aria-labelledby="memory-entry-title"><header><div><h2 id="memory-entry-title">新增记忆</h2><p>记录可跨任务复用的偏好、规则或重要结论。</p></div><button className="icon-button" aria-label="关闭" onClick={onClose}><X /></button></header><div className="task-modal-body"><label>记忆内容<textarea value={content} placeholder="例如：优先关注 Agent、RAG 和 AI 工程实践相关资讯" onChange={(event) => setContent(event.target.value)} /></label><label>关联主题（可选）<input value={tags} placeholder="例如：Agent，RAG，工程实践" onChange={(event) => setTags(event.target.value)} /></label><label>重要程度<select value={importance} onChange={(event) => setImportance(event.target.value)}>{[1,2,3,4,5,6,7,8,9,10].map((value) => <option key={value} value={value}>{value} / 10</option>)}</select></label>{error && <p className="source-form-error" role="alert">{error}</p>}</div><footer><button className="button" onClick={onClose}>取消</button><button className="button pink" disabled={saving} onClick={() => void submit()}><CheckCircle2 />{saving ? '保存中…' : '保存记忆'}</button></footer></Modal.Content></Modal.Root>
}

function MemoryPreferenceDialog({ preferences, onClose, onSaved }: { preferences: MemoryPreferences; onClose: () => void; onSaved: () => Promise<void> }): ReactElement {
  const [tags, setTags] = useState(preferences.preferred_tags.join('，')); const [sources, setSources] = useState(preferences.block_sources.join('，')); const [topics, setTopics] = useState(preferences.blocked_topics.join('，')); const [pushTime, setPushTime] = useState(preferences.push_time); const [threshold, setThreshold] = useState(String(preferences.importance_threshold)); const [saving, setSaving] = useState(false); const [error, setError] = useState('')
  const list = (value: string): string[] => value.split(/[,，]/).map((item) => item.trim()).filter(Boolean)
  const submit = async (): Promise<void> => { setSaving(true); setError(''); try { await memoryApi.savePreferences({ preferred_tags: list(tags), block_sources: list(sources), blocked_topics: list(topics), push_time: pushTime, importance_threshold: Number(threshold) }); await onSaved() } catch (caught) { setError(caught instanceof Error ? caught.message : '保存内容偏好失败。') } finally { setSaving(false) } }
  return <Modal.Root open onOpenChange={(open) => { if (!open) onClose() }}><Modal.Overlay className="modal-backdrop" /><Modal.Content className="task-modal memory-dialog" aria-labelledby="memory-preference-title"><header><div><h2 id="memory-preference-title">编辑内容偏好</h2><p>这些设置会影响后续每日资讯的检索与筛选。</p></div><button className="icon-button" aria-label="关闭" onClick={onClose}><X /></button></header><div className="task-modal-body"><label>关注主题<input value={tags} placeholder="多个主题请用逗号分隔" onChange={(event) => setTags(event.target.value)} /></label><label>不看来源<input value={sources} placeholder="例如：某个不再关注的网站" onChange={(event) => setSources(event.target.value)} /></label><label>不看主题<input value={topics} placeholder="例如：融资新闻、招聘信息" onChange={(event) => setTopics(event.target.value)} /></label><div className="memory-preference-inputs"><label>每日发送时间<input type="time" value={pushTime} onChange={(event) => setPushTime(event.target.value)} /></label><label>保留的重要程度<select value={threshold} onChange={(event) => setThreshold(event.target.value)}>{[0,1,2,3,4,5,6,7,8,9,10].map((value) => <option key={value} value={value}>{value} / 10</option>)}</select></label></div>{error && <p className="source-form-error" role="alert">{error}</p>}</div><footer><button className="button" onClick={onClose}>取消</button><button className="button pink" disabled={saving} onClick={() => void submit()}><CheckCircle2 />{saving ? '保存中…' : '保存偏好'}</button></footer></Modal.Content></Modal.Root>
}

function SkillsPage(): ReactElement {
  const remote = useRemoteData(skillsApi.list); const [reloading, setReloading] = useState(false); const status = DataStatus({ remote, empty: remote.data?.length === 0 })
  const reloadSkills = async (): Promise<void> => { setReloading(true); try { const result = await skillsApi.reload(); toast.success(`已重新扫描 Skill，当前加载 ${result.loaded} 个。`); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : 'Skill 重载失败。') } finally { setReloading(false) } }
  if (status) return status; const skills = remote.data ?? []
  return <section className="data-panel"><div className="data-summary"><Blocks /><span>已加载 {skills.length} 个 Skill</span><button className="button compact" disabled={reloading} onClick={() => void reloadSkills()}><RefreshCw />{reloading ? '扫描中' : '重新扫描'}</button></div><div className="data-list">{skills.map((skill) => <article className="data-row" key={skill.id}><div><strong>{skill.name}</strong><p>{skill.description}</p></div><span className={`status-label ${skill.is_builtin ? 'ready' : ''}`}>{skill.is_builtin ? '内置' : '自定义'}</span><code>{skill.id}</code></article>)}</div></section>
}

function SourceConfigurationPage(): ReactElement { return <section className="state-panel"><RadioTower /><h2>数据源由服务端配置</h2><p>当前后端提供采集执行接口，但尚未提供数据源配置的读取和保存接口。请通过 .env、计划任务配置或工作流定义配置 RSS、GitHub Trending、Follow OPML 和 AI 搜索适配器；采集结果会在“内容”和“任务记录”中显示。</p></section> }

function SourceConfigurationPageV2(): ReactElement {
  const remote = useRemoteData(sourcesApi.list)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [enabled, setEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const selected = remote.data?.sources.find((source) => source.id === selectedId) ?? remote.data?.sources[0]
  useEffect(() => { if (selected) { setDraft(selected.config); setEnabled(selected.enabled) } }, [selected])
  const status = DataStatus({ remote, empty: false })
  if (status) return status
  const metadata = selected ? sourceMetadataFor(selected, remote.data?.available_adapters ?? []) : undefined
  const updateField = (key: string, value: unknown): void => setDraft((current) => ({ ...current, [key]: value }))
  const save = async (): Promise<void> => { if (!selected) return; setSaving(true); try { await sourcesApi.save(selected.id, { type: selected.type, enabled, config: sourceConfigForSave(draft, metadata?.config_fields ?? []) }); toast.success('数据源配置已保存'); await remote.reload() } catch (caught) { toast.error(caught instanceof Error ? caught.message : '保存数据源配置失败') } finally { setSaving(false) } }
  return <div className="source-page"><header className="source-page-header"><div><h1>数据源</h1><p>管理资讯的采集入口。每个数据源独立启用和保存，修改后会在下一次任务执行时生效。</p></div><span>{remote.data?.sources.length ?? 0} 个已配置来源</span></header><div className="source-workspace"><aside className="source-sidebar"><header><RadioTower /><span>采集来源</span></header>{remote.data?.sources.length ? remote.data.sources.map((source) => { const sourceMetadata = sourceMetadataFor(source, remote.data?.available_adapters ?? []); return <button key={source.id} className={source.id === selected?.id ? 'active' : ''} onClick={() => setSelectedId(source.id)}><span className={`status-dot ${source.enabled ? 'ready' : 'error'}`} /><span><strong>{sourceMetadata?.name ?? source.id}</strong><small>{source.enabled ? '已启用' : '已停用'} · {sourceMetadata?.description ?? source.type}</small></span><ChevronRight /></button> }) : <EmptyInline text="暂未配置数据源。" />}</aside>{selected ? <section className={`source-config-card ${enabled ? '' : 'is-disabled'}`}><header className="source-card-header"><div><RadioTower /><div><h2>{metadata?.name ?? selected.id}</h2><p>{metadata?.description ?? '配置此数据源的采集范围与内容规则。'}</p></div></div><button type="button" className={`provider-activation ${enabled ? 'ready' : ''}`} aria-pressed={enabled} onClick={() => setEnabled((current) => !current)}><span />{enabled ? '已启用' : '已停用'}</button></header><div className="source-config-body"><section><h3>采集设置</h3><div className="source-field-grid">{metadata?.config_fields.length ? metadata.config_fields.map((field) => <SourceConfigFieldControl key={field.key} field={field} value={draft[field.key]} onChange={(value) => updateField(field.key, value)} />) : <EmptyInline text="此数据源暂时没有可在控制台调整的选项。" />}</div></section><aside className="source-config-note"><h3>当前状态</h3><div><span>数据源状态</span><strong>{enabled ? '已启用' : '已停用'}</strong></div><div><span>配置保存位置</span><strong>本地 SQLite</strong></div><p>保存后不会立即采集。系统会在下次手动运行或计划任务触发时使用新配置。</p></aside></div><footer className="source-savebar"><span>配置会保存到本地工作区</span><button className="button pink" disabled={saving} onClick={() => void save()}><CheckCircle2 />{saving ? '保存中…' : '保存配置'}</button></footer></section> : <section className="source-empty"><RadioTower /><h2>选择一个数据源</h2><p>在左侧选择来源后，可以调整它的采集范围和启用状态。</p></section>}</div></div>
}

function SourceConfigFieldControl({ field, value, onChange }: { field: SourceConfigField; value: unknown; onChange: (value: unknown) => void }): ReactElement {
  const label = sourceFieldLabel(field.key, field.label); const help = sourceFieldHelp(field.key, field.help_text)
  if (field.type === 'boolean') return <label className="source-boolean"><input type="checkbox" checked={Boolean(value ?? field.default)} onChange={(event) => onChange(event.target.checked)} /><span><strong>{label}</strong><small>{help}</small></span></label>
  const textValue = Array.isArray(value) ? value.join('\n') : typeof value === 'string' || typeof value === 'number' ? String(value) : field.default === null || field.default === undefined ? '' : String(field.default)
  const update = (raw: string): void => onChange(field.key === 'rss_urls' ? raw.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean) : field.type === 'number' ? (raw === '' ? '' : Number(raw)) : raw)
  return <label className={`source-form-field ${field.type === 'textarea' ? 'wide' : ''}`}><span>{label}{field.required && <b>必填</b>}</span>{field.type === 'select' ? <select value={textValue} onChange={(event) => update(event.target.value)}>{field.options?.map((option) => <option key={option} value={option}>{sourceOptionLabel(option)}</option>)}</select> : field.type === 'textarea' || field.key === 'rss_urls' ? <textarea value={textValue} placeholder={field.key === 'rss_urls' ? '一行一个 RSS 地址' : field.placeholder} onChange={(event) => update(event.target.value)} /> : <input type={field.type === 'number' ? 'number' : field.type === 'url' ? 'url' : 'text'} value={textValue} placeholder={field.placeholder} onChange={(event) => update(event.target.value)} />}{help && <small>{help}</small>}</label>
}

function sourceConfigForSave(config: Record<string, unknown>, fields: SourceConfigField[]): Record<string, unknown> { const fieldKeys = new Set(fields.map((field) => field.key)); const result = { ...config }; for (const field of fields) { const value = result[field.key]; if (field.key === 'rss_urls' && typeof value === 'string') result[field.key] = value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean); if (field.type === 'number' && typeof value === 'string' && value) result[field.key] = Number(value) } for (const key of Object.keys(result)) { if (!fieldKeys.has(key) && result[key] === undefined) delete result[key] } return result }
function sourceFieldLabel(key: string, fallback: string): string { return ({ rss_url: 'RSS 地址', rss_urls: '订阅地址', source_name: '来源名称', category: '内容分类', language: '编程语言', spoken_language: '页面语言', stars_min: '最低 Star 数', max_items: '单次采集数量', opml_path: 'OPML 文件位置', source_tag: '来源标签', fetch_articles: '抓取订阅文章', max_feeds: '最多读取订阅数', max_items_per_feed: '每个订阅保留数量', provider: '搜索服务', query: '搜索主题', recency_days: '检索最近天数', custom_prompt: '自定义搜索要求' }[key] ?? fallback) }
function sourceFieldHelp(key: string, fallback: string): string { return ({ rss_urls: '可填写多个地址，每行一个。', language: '例如 python、typescript；留空则不限语言。', spoken_language: '例如 zh、en；留空则使用默认语言。', stars_min: '忽略 Star 数低于该数值的项目。', max_items: '限制一次最多带回多少条候选内容。', opml_path: '填写本机 Follow 导出的 OPML 文件完整路径。', fetch_articles: '开启后会读取订阅中的近期文章，关闭时只导入订阅地址。', max_feeds: '限制一次读取的订阅数量，避免采集时间过长。', max_items_per_feed: '限制每个订阅源带回的文章数量。', provider: '选择 AI 搜索服务的提示词兼容方式。', query: '例如：AI Agent、RAG 或你关注的技术主题。', recency_days: '只检索最近几天发布的内容。', custom_prompt: '可使用 {query}、{max_items}、{recency_days} 作为变量。' }[key] ?? fallback) }
function sourceOptionLabel(value: string): string { return ({ perplexity: 'Perplexity', phind: 'Phind', custom: '自定义服务' }[value] ?? value) }
function sourceMetadataFor(source: SourceConfiguration, adapters: SourceAdapterMetadata[]): SourceAdapterMetadata | undefined { const aliases: Record<string, string> = { GitHubTrendingAdapter: 'github_trending', FollowApiAdapter: 'follow_opml', AISearchAdapter: 'ai_search', RSSAdapter: 'rss' }; const expectedId = aliases[source.type] ?? source.type; return adapters.find((item) => item.id === expectedId || item.id === source.id || item.type === source.type) }

function SettingsPageV2(): ReactElement {
  const remote = useRemoteData(settingsApi.get); const [settings, setSettings] = useState<any>(null); const [saving, setSaving] = useState(false)
  useEffect(() => { if (remote.data) setSettings(remote.data) }, [remote.data]); const status = DataStatus({ remote, empty: false }); if (status) return status; if (!settings) return <LoadingState />
  const save = async (): Promise<void> => { setSaving(true); try { await settingsApi.save(settings); toast.success('设置已保存') } catch (caught) { toast.error(caught instanceof Error ? caught.message : '设置保存失败') } finally { setSaving(false) } }
  return <div className="data-stack"><section className="data-panel"><div className="data-summary"><Settings2 /><span>模型与代理</span></div><div className="settings-form"><label>代理端点<input value={settings.http_proxy} onChange={(e) => setSettings({ ...settings, http_proxy: e.target.value })} /></label>{settings.ai_providers.map((provider: any, index: number) => <div className="settings-provider" key={provider.id}><strong>{provider.name}</strong><label>API Key<input type="password" value={provider.api_key} onChange={(e) => { const next = [...settings.ai_providers]; next[index] = { ...provider, api_key: e.target.value }; setSettings({ ...settings, ai_providers: next }) }} /></label><label>模型窗口 JSON<textarea value={JSON.stringify(provider.context_window_tokens, null, 2)} onChange={(e) => { try { const next = [...settings.ai_providers]; next[index] = { ...provider, context_window_tokens: JSON.parse(e.target.value) }; setSettings({ ...settings, ai_providers: next }) } catch { /* invalid JSON */ } }} /></label></div>)}</div></section><section className="data-panel"><div className="data-summary"><Send /><span>发布 Webhook 与可选依赖</span></div><div className="settings-form">{settings.publishers.map((publisher: any, index: number) => <div className="settings-provider" key={publisher.id}><label><input type="checkbox" checked={publisher.enabled} onChange={(e) => { const next = [...settings.publishers]; next[index] = { ...publisher, enabled: e.target.checked }; setSettings({ ...settings, publishers: next }) }} /> {publisher.id}</label><textarea value={JSON.stringify(publisher.config, null, 2)} onChange={(e) => { try { const next = [...settings.publishers]; next[index] = { ...publisher, config: JSON.parse(e.target.value) }; setSettings({ ...settings, publishers: next }) } catch { /* invalid JSON */ } }} /></div>)}<p className="capability-note">{Object.entries(settings.optional_dependencies).map(([key, value]) => `${key}: ${value ? '可用' : '未安装'}`).join(' · ')}</p><div className="source-editor-actions"><button className="button pink" disabled={saving} onClick={() => void save()}><CheckCircle2 />{saving ? '保存中…' : '保存设置'}</button></div></div></section></div>
}

function SettingsPageV3(): ReactElement {
  const remote = useRemoteData(settingsApi.get); const [settings, setSettings] = useState<any>(null); const [tab, setTab] = useState<'models' | 'publish' | 'system'>('models'); const [saving, setSaving] = useState(false)
  useEffect(() => { if (remote.data) setSettings(remote.data) }, [remote.data]); const status = DataStatus({ remote, empty: false }); if (status) return status; if (!settings) return <LoadingState />
  const save = async (): Promise<void> => { setSaving(true); try { await settingsApi.save(settings); toast.success('设置已保存') } catch (caught) { toast.error(caught instanceof Error ? caught.message : '设置保存失败') } finally { setSaving(false) } }
  const providerOrder = ['openai', 'anthropic', 'google', 'ollama']
  const orderedProviders = settings.ai_providers
    .map((provider: any, index: number) => ({ provider, index }))
    .sort((left: any, right: any) => {
      const leftOrder = providerOrder.indexOf(left.provider.type)
      const rightOrder = providerOrder.indexOf(right.provider.type)
      return (leftOrder < 0 ? providerOrder.length : leftOrder) - (rightOrder < 0 ? providerOrder.length : rightOrder)
    })
  const updateProvider = (index: number, provider: any): void => {
    const next = [...settings.ai_providers]
    next[index] = provider
    setSettings({ ...settings, ai_providers: next })
  }
  return <div className="settings-page"><nav className="settings-tabs" aria-label="设置分类"><button className={tab === 'models' ? 'active' : ''} onClick={() => setTab('models')}>AI 模型</button><button className={tab === 'publish' ? 'active' : ''} onClick={() => setTab('publish')}>发布与存储</button><button className={tab === 'system' ? 'active' : ''} onClick={() => setTab('system')}>系统</button></nav>{tab === 'models' && <section className="settings-section"><header><h2>AI 模型配置</h2><p>配置模型连接、API 密钥和模型窗口。</p></header><label className="settings-proxy">代理端点<input value={settings.http_proxy} placeholder="可选，例如 http://127.0.0.1:7890" onChange={(e) => setSettings({ ...settings, http_proxy: e.target.value })} /></label><div className="provider-grid">{orderedProviders.map(({ provider, index }: any) => <ProviderConfigurationCard key={provider.id} provider={provider} onChange={(next) => updateProvider(index, next)} />)}</div></section>}{tab === 'publish' && <section className="settings-section"><header><h2>发布渠道</h2><p>管理日报自动投递到的机器人渠道。</p></header><div className="provider-stack">{settings.publishers.map((publisher: any, index: number) => <article className="provider-card" key={publisher.id}><div className="provider-card-header"><label className="publisher-toggle"><input type="checkbox" checked={publisher.enabled} onChange={(e) => { const next = [...settings.publishers]; next[index] = { ...publisher, enabled: e.target.checked }; setSettings({ ...settings, publishers: next }) }} /><strong>{publisher.id}</strong></label><span className={`status-label ${publisher.enabled ? 'ready' : ''}`}>{publisher.enabled ? '已启用' : '已停用'}</span></div><label>连接配置<textarea value={JSON.stringify(publisher.config, null, 2)} onChange={(e) => { try { const next = [...settings.publishers]; next[index] = { ...publisher, config: JSON.parse(e.target.value) }; setSettings({ ...settings, publishers: next }) } catch { } }} /></label></article>)}</div></section>}{tab === 'system' && <section className="settings-section"><header><h2>系统能力</h2><p>当前运行环境检测到的可选组件。</p></header><div className="capability-grid">{Object.entries(settings.optional_dependencies).map(([key, value]) => <div key={key}><strong>{key}</strong><span className={`status-label ${value ? 'ready' : 'error'}`}>{value ? '可用' : '未安装'}</span></div>)}</div></section>}<div className="settings-savebar"><button className="button pink" disabled={saving} onClick={() => void save()}><CheckCircle2 />{saving ? '保存中…' : '保存设置'}</button></div></div>
}

function ProviderConfigurationCard({ provider, onChange }: { provider: any; onChange: (provider: any) => void }): ReactElement {
  const [apiKeyVisible, setApiKeyVisible] = useState(false)
  const [catalog, setCatalog] = useState<string[] | null>(null)
  const [catalogOpen, setCatalogOpen] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [testing, setTesting] = useState(false)
  const update = (changes: Record<string, unknown>): void => onChange({ ...provider, ...changes })
  const selectModel = (model: string, selected: boolean): void => {
    if (selected && !provider.models.includes(model)) {
      update({
        models: [...provider.models, model],
        context_window_tokens: { ...provider.context_window_tokens, [model]: provider.context_window_tokens[model] ?? 128000 },
        default_output_tokens: { ...provider.default_output_tokens, [model]: provider.default_output_tokens[model] ?? 4096 },
      })
    }
    if (!selected && provider.models.includes(model)) removeModel(model)
  }
  const syncModels = async (): Promise<void> => {
    setSyncing(true)
    try {
      const result = await settingsApi.syncModels(provider)
      setCatalog(result.models)
      setCatalogOpen(true)
      toast.success(result.note ?? `已找到 ${result.models.length} 个模型`)
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : '同步模型列表失败')
    } finally {
      setSyncing(false)
    }
  }
  const testConnection = async (): Promise<void> => {
    setTesting(true)
    try {
      const result = await settingsApi.testConnection(provider)
      toast.success(`连接正常，可读取 ${result.model_count} 个模型`)
    } catch (caught) {
      toast.error(caught instanceof Error ? caught.message : '连接测试失败')
    } finally {
      setTesting(false)
    }
  }
  const removeModel = (model: string): void => {
    const { [model]: _window, ...contextWindows } = provider.context_window_tokens
    const { [model]: _output, ...outputTokens } = provider.default_output_tokens
    update({ models: provider.models.filter((item: string) => item !== model), context_window_tokens: contextWindows, default_output_tokens: outputTokens })
  }
  return <article className={`provider-card provider-config-card ${provider.enabled ? '' : 'is-disabled'}`}>
    <header className="provider-card-header">
      <div><strong>{provider.name}</strong><small>{provider.type} 兼容接口</small></div>
      <div className="provider-actions"><button type="button" className="test-connection-button" disabled={testing} onClick={() => void testConnection()}><RadioTower className={testing ? 'spinning' : ''} />{testing ? '测试中…' : '测试连接'}</button><button type="button" className={`provider-activation ${provider.enabled ? 'ready' : ''}`} aria-pressed={provider.enabled} onClick={() => update({ enabled: !provider.enabled })}><span />{provider.enabled ? '已激活' : '已停用'}</button></div>
    </header>
    <div className="provider-config-body">
      <section className="provider-connection">
        <h3>连接设置</h3>
        <label>API 地址<input value={provider.base_url} placeholder="使用默认地址" onChange={(event) => update({ base_url: event.target.value })} /></label>
        <label>API 密钥<div className="secret-input"><input type={apiKeyVisible ? 'text' : 'password'} value={provider.api_key} onChange={(event) => update({ api_key: event.target.value })} /><button type="button" className="icon-button" aria-label={apiKeyVisible ? '隐藏 API 密钥' : '显示 API 密钥'} title={apiKeyVisible ? '隐藏 API 密钥' : '显示 API 密钥'} onClick={() => setApiKeyVisible((visible) => !visible)}>{apiKeyVisible ? <EyeOff /> : <Eye />}</button></div></label>
        <details className="provider-window-settings"><summary>更多模型设置</summary><p>为不同模型设置可接收的资料量，以及每次回复的最大长度。一般保持默认即可。</p><label>可接收的资料量<textarea value={JSON.stringify(provider.context_window_tokens, null, 2)} onChange={(event) => { try { update({ context_window_tokens: JSON.parse(event.target.value) }) } catch { } }} /></label><label>单次回复最大长度<textarea value={JSON.stringify(provider.default_output_tokens, null, 2)} onChange={(event) => { try { update({ default_output_tokens: JSON.parse(event.target.value) }) } catch { } }} /></label></details>
      </section>
      <section className="provider-models">
        <div className="provider-model-header"><h3>模型管理</h3><button type="button" className="sync-models-button" disabled={syncing} onClick={() => void syncModels()}><RefreshCw className={syncing ? 'spinning' : ''} />{syncing ? '同步中…' : '同步列表'}</button></div>
        <section className="added-models"><h3>已添加模型</h3><div className="model-tag-list">{provider.models.map((model: string) => <span className="model-tag" key={model}>{model}<button type="button" aria-label={`移除模型 ${model}`} title="移除模型" onClick={() => removeModel(model)}><X /></button></span>)}{provider.models.length === 0 && <p>尚未添加模型</p>}</div></section>
        <section className="provider-catalog"><h3>模型列表</h3><div className="model-select"> <button type="button" className="model-select-trigger" disabled={!catalog} aria-expanded={catalogOpen} onClick={() => setCatalogOpen((open) => !open)}>{catalog ? `已同步 ${catalog.length} 个模型` : '请先同步列表'}<ChevronDown className={catalogOpen ? 'open' : ''} /></button>{catalog && catalogOpen && <div className="model-dropdown" role="group" aria-label="同步得到的模型列表">{catalog.map((model) => <label key={model}><input type="checkbox" checked={provider.models.includes(model)} onChange={(event) => selectModel(model, event.target.checked)} /><span>{model}</span></label>)}</div>}</div></section>
      </section>
    </div>
  </article>
}

function Metric({ label, value, note, icon: Icon, tone }: { label: string; value: string | number; note: string; icon: LucideIcon; tone: string }): ReactElement { return <article className={`metric ${tone}`}><div><span>{label}</span><Icon /></div><strong>{value}</strong><p>{note}</p></article> }
function PanelHeader({ title, description }: { title: string; description: string }): ReactElement { return <header className="panel-header"><h2>{title}</h2><p>{description}</p></header> }
async function loadTaskData(): Promise<{ schedules: ScheduleTask[]; logs: TaskLog[] }> { const [schedules, logs] = await Promise.all([schedulesApi.list(), dashboardApi.getLogs()]); return { schedules, logs } }
async function loadWorkflowData(): Promise<{ workflows: WorkflowSummary[]; agents: AgentSummary[] }> { const [workflows, agents] = await Promise.all([workflowsApi.list(), agentsApi.list()]); return { workflows, agents } }
async function loadKnowledgeData(): Promise<{ capabilities: KnowledgeCapabilities; categories: KnowledgeCategory[]; documents: KnowledgeDocument[] }> { const [capabilities, categories, documents] = await Promise.all([knowledgeApi.capabilities(), knowledgeApi.categories(), knowledgeApi.documents()]); return { capabilities, categories, documents } }
async function loadMemoryData(): Promise<{ entries: MemoryEntry[]; preferences: MemoryPreferences }> { const [entries, preferences] = await Promise.all([memoryApi.entries(), memoryApi.preferences()]); return { entries, preferences } }

export {
  Dashboard,
  WorkflowsPage,
  ContentPage,
  PublishingPage,
  TasksPage,
  KnowledgePage,
  MemoryPage,
  SkillsPage,
  SourceConfigurationPage,
  SourceConfigurationPageV2,
  SettingsPageV2,
  SettingsPageV3,
  useRemoteData,
  LoadingState,
  ErrorState,
  DataStatus,
  EmptyInline,
  formatTaskName,
  formatDate,
  formatUnix,
  formatSchedule,
  statusClass,
  statusText,
  Metric,
  PanelHeader,
  loadTaskData,
  loadWorkflowData,
  loadKnowledgeData,
  loadMemoryData,
}
