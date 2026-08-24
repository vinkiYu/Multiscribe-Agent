import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { CheckCircle2, CircleAlert, History, Layers, Play, Plus, RefreshCw, Workflow } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { workflowIterationsApi, workflowRunPath, workflowsApi } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'
import type { JsonRecord } from '../services/api'
import type { WorkflowStep, WorkflowSummary } from '../types'

const stepTypeLabel: Record<WorkflowStep['step_type'], string> = {
  agent: 'Agent',
  workflow: '工作流',
}

const tabItems = [
  { key: 'design', label: '设计', icon: <Workflow /> },
  { key: 'runs', label: '迭代', icon: <History /> },
  { key: 'steps', label: '节点', icon: <Layers /> },
] as const

type TabKey = (typeof tabItems)[number]['key']

function stepTone(status: string | null | undefined): 'success' | 'running' | 'error' | 'pending' {
  if (status === 'success') return 'success'
  if (status === 'running') return 'running'
  if (status === 'error' || status === 'failed') return 'error'
  return 'pending'
}

function stepLabel(tone: ReturnType<typeof stepTone>): string {
  if (tone === 'success') return '已启用'
  if (tone === 'error') return '已停用'
  if (tone === 'running') return '运行中'
  return '等待中'
}

export function WorkflowsPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const remote = useRemoteData<JsonRecord[]>(() => workflowsApi.list())
  const workflows = (remote.data ?? []) as unknown as WorkflowSummary[]
  const loading = remote.loading && !remote.data
  const error = remote.error?.message ?? null
  const hasData = Boolean(remote.data)
  const [activeId, setActiveId] = useState<string>('')
  const [tab, setTab] = useState<TabKey>('design')

  useEffect(() => {
    if (!activeId && workflows.length > 0) setActiveId(workflows[0].id)
  }, [activeId, workflows])

  const active = useMemo(() => workflows.find((item) => item.id === activeId) ?? null, [workflows, activeId])

  return (
    <>
      <SectionHeading
        icon={<Workflow />}
        title="工作流"
        description="对接 /api/workflows：浏览 WorkflowDefinition、查看 Loop 迭代历史。"
        actions={
          <>
            <button className="btn" type="button" onClick={() => void remote.reload()}>
              <RefreshCw /> 刷新
            </button>
            <button className="btn btn-primary" type="button" onClick={() => onFlash('新建工作流向导即将上线')}>
              <Plus /> 新建工作流
            </button>
          </>
        }
      />

      <DataStatus
        loading={loading}
        error={error}
        empty={!hasData && !loading}
        emptyTitle="暂无工作流"
        emptyDescription="新建第一个工作流后，节点和迭代记录会显示在这里。"
        onRetry={() => void remote.reload()}
      >
        <section className="section">
          <div className="workflows-layout">
            <aside className="split-list" aria-label="工作流列表">
              <header className="split-list-header">
                <strong>所有工作流</strong>
                <span>{workflows.length} 个</span>
              </header>
              <ul className="split-list-body">
                {workflows.map((item) => {
                  const isActive = item.id === activeId
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={isActive ? 'split-list-item is-active' : 'split-list-item'}
                        onClick={() => setActiveId(item.id)}
                      >
                        <span className="split-list-icon" aria-hidden="true"><Workflow /></span>
                        <span className="split-list-copy">
                          <strong>{item.name}</strong>
                          <small>{item.id} · {item.steps.length} 节点</small>
                        </span>
                        <span className="split-list-meta">
                          <span className="run-pill run-pill-pending">
                            已启用
                          </span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </aside>

            <article className="split-detail" aria-label="工作流详情">
              {!active ? (
                <div className="state-panel">
                  <Workflow />
                  <h2>选择左侧工作流</h2>
                  <p>条目选中后，可在此查看设计、迭代历史与节点列表。</p>
                </div>
              ) : (
                <>
                  <header className="split-detail-header">
                    <div>
                      <h2>{active.name}</h2>
                      <p>{active.description}</p>
                    </div>
                    <div className="split-detail-actions">
                      <span className="pill pill-builtin">已启用</span>
                      <button className="btn btn-primary btn-sm" type="button" onClick={() => onFlash(`已触发「${active.name}」：${workflowRunPath(active.id)}`)}>
                        <Play /> 立即运行
                      </button>
                    </div>
                  </header>

                  <nav className="tab-bar" aria-label="详情标签">
                    {tabItems.map((item) => {
                      const isActive = tab === item.key
                      return (
                        <button
                          key={item.key}
                          type="button"
                          className={isActive ? 'tab-button is-active' : 'tab-button'}
                          aria-current={isActive ? 'page' : undefined}
                          onClick={() => setTab(item.key)}
                        >
                          {item.icon}
                          <span>{item.label}</span>
                        </button>
                      )
                    })}
                  </nav>

                  <div className="split-detail-body">
                    {tab === 'design' && <DesignTab workflow={active} />}
                    {tab === 'runs' && <RunsTab workflowId={active.id} onFlash={onFlash} />}
                    {tab === 'steps' && <StepsTab steps={active.steps} />}
                  </div>
                </>
              )}
            </article>
          </div>
        </section>
      </DataStatus>
    </>
  )
}

function DesignTab({ workflow }: { workflow: WorkflowSummary }): ReactElement {
  return (
    <>
      <div className="design-meta">
        <span><strong>工作流 ID</strong><code>{workflow.id}</code></span>
        <span><strong>节点数</strong>{workflow.steps.length}</span>
      </div>
      <div className="dag">
        {workflow.steps.map((step, index) => {
          const tone = stepTone(step.enabled ? 'success' : 'error')
          return (
            <div key={step.id} className="dag-step">
              <article className={`dag-node dag-${tone}`}>
                <span className="dag-step-index">{String(index + 1).padStart(2, '0')}</span>
                <span className="dag-step-type">{stepTypeLabel[step.step_type] ?? step.step_type}</span>
                <strong>{step.name}</strong>
                <span className={`run-pill run-pill-${tone}`}>{stepLabel(tone)}</span>
              </article>
              {index < workflow.steps.length - 1 && (
                <span className="dag-connector" aria-hidden="true">
                  <svg viewBox="0 0 32 12"><path d="M0 6h28m-6-4 4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg>
                </span>
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}

function RunsTab({ workflowId, onFlash }: { workflowId: string; onFlash: (message: string) => void }): ReactElement {
  const iterationsRemote = useRemoteData<Array<Record<string, unknown>>>(() => workflowIterationsApi.list({ limit: 20 }))
  const items = iterationsRemote.data ?? []
  const loading = iterationsRemote.loading && items.length === 0

  useEffect(() => {
    if (iterationsRemote.error) onFlash(`加载迭代失败：${iterationsRemote.error.message}`)
  }, [iterationsRemote.error, onFlash])

  return (
    <div className="data-table-card">
      <table className="data-table">
        <thead>
          <tr>
            <th>工作流运行</th>
            <th>节点</th>
            <th>轮次</th>
            <th>评分</th>
            <th>状态</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={6} className="adapter-empty">正在加载迭代记录…</td></tr>
          ) : items.length === 0 ? (
            <tr><td colSpan={6} className="adapter-empty">暂无迭代记录。可通过工作流运行触发：<code>{workflowRunPath(workflowId)}</code>（SSE）</td></tr>
          ) : items.map((row, index) => {
            const id = `${String(row.workflow_run_id ?? '')}-${String(row.step_id ?? '')}-${String(row.round ?? index)}`
            const score = typeof row.score === 'number' ? row.score : null
            return (
              <tr key={id}>
                <td className="data-table-primary"><strong>{String(row.workflow_run_id ?? '—')}</strong></td>
                <td><span className="pill pill-neutral">{String(row.step_id ?? '—')}</span></td>
                <td>{String(row.round ?? '—')}</td>
                <td>{score === null ? '—' : score.toFixed(2)}</td>
                <td>
                  <span className={`run-pill run-pill-${row.converged ? 'success' : 'running'}`}>
                    {row.converged ? <><CheckCircle2 /> 已收敛</> : <><CircleAlert /> 继续迭代</>}
                  </span>
                </td>
                <td>{String(row.reason ?? '—')}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function StepsTab({ steps }: { steps: WorkflowStep[] }): ReactElement {
  return (
    <div className="data-table-card">
      <table className="data-table">
        <thead>
          <tr>
            <th>标识</th>
            <th>名称</th>
            <th>类型</th>
            <th>目标</th>
            <th>最大迭代</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((step) => (
            <tr key={step.id}>
              <td className="data-table-primary"><strong>{step.id}</strong></td>
              <td>{step.name}</td>
              <td><span className="pill pill-neutral">{stepTypeLabel[step.step_type] ?? step.step_type}</span></td>
              <td>{step.agent_id ?? step.workflow_id ?? '—'}</td>
              <td>{step.max_iterations ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}