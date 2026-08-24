import { useEffect, type ReactElement } from 'react'
import { CheckCircle2, CircleAlert, DollarSign, History, ListChecks, RefreshCw } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { alertsApi, operationsApi, workflowIterationsApi } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'

type MaybeNumber = number | null | undefined

interface OverviewUsage {
  date: string
  input_tokens: MaybeNumber
  output_tokens: MaybeNumber
  total_tokens: MaybeNumber
  llm_calls: MaybeNumber
  task_count: MaybeNumber
}

interface OverviewUsageByModel {
  date: string
  model_name: string
  input_tokens: number
  output_tokens: number
  total_tokens: number
  llm_calls: number
  cost_usd: number
}

interface OverviewIteration {
  workflow_run_id: string
  step_id: string
  round: number
  score: number | null
  converged: boolean
  reason: string
}

interface OverviewRecent {
  date: string
  workflow_run_id: string
  final_score: number | null
  rounds: number
  converged: boolean
  exit_reason: string
}

interface OverviewSummary {
  avg_final_score: number | null
  total_runs: number
  converge_rate: number
  converged_runs: number
}

interface OverviewShape {
  usage: OverviewUsage
  cost_usd: number
  usage_by_model: OverviewUsageByModel[]
  publish: { success: number; error: number; total: number }
  iterations: OverviewIteration[]
  evaluation: { today_summary: OverviewSummary; recent: OverviewRecent[] }
  task_logs: Array<Record<string, unknown>>
}

const fallbackOverview: OverviewShape = {
  usage: { date: '2026-08-10', input_tokens: 1_842_310, output_tokens: 612_904, total_tokens: 2_455_214, llm_calls: 184, task_count: 28 },
  cost_usd: 3.74,
  publish: { success: 138, error: 12, total: 150 },
  usage_by_model: [
    { date: '2026-08-10', model_name: 'gpt-4o-mini', input_tokens: 982_104, output_tokens: 314_002, total_tokens: 1_296_106, llm_calls: 184, cost_usd: 1.42 },
    { date: '2026-08-10', model_name: 'claude-3-5-sonnet', input_tokens: 524_318, output_tokens: 198_410, total_tokens: 722_728, llm_calls: 92, cost_usd: 1.83 },
    { date: '2026-08-10', model_name: 'qwen-plus', input_tokens: 218_904, output_tokens: 64_220, total_tokens: 283_124, llm_calls: 86, cost_usd: 0.21 },
    { date: '2026-08-10', model_name: 'deepseek-chat', input_tokens: 116_984, output_tokens: 36_272, total_tokens: 153_256, llm_calls: 38, cost_usd: 0.28 },
  ],
  iterations: [
    { workflow_run_id: 'r-9821', step_id: 'curate.score', round: 3, score: 0.84, converged: true, reason: '评分已收敛' },
    { workflow_run_id: 'r-9821', step_id: 'curate.score', round: 2, score: 0.71, converged: false, reason: '继续迭代' },
    { workflow_run_id: 'r-9820', step_id: 'curate.score', round: 1, score: 0.42, converged: false, reason: '达到评分阈值' },
    { workflow_run_id: 'r-9818', step_id: 'curate.score', round: 2, score: null, converged: false, reason: '上游 LLM 超时' },
  ],
  evaluation: {
    today_summary: { avg_final_score: 0.78, total_runs: 28, converge_rate: 75, converged_runs: 21 },
    recent: [
      { date: '2026-08-10', workflow_run_id: 'r-9821', final_score: 0.84, rounds: 3, converged: true, exit_reason: '评分已收敛' },
      { date: '2026-08-09', workflow_run_id: 'r-9802', final_score: 0.79, rounds: 4, converged: true, exit_reason: '评分已收敛' },
      { date: '2026-08-08', workflow_run_id: 'r-9786', final_score: 0.66, rounds: 5, converged: false, exit_reason: '达到最大轮次' },
      { date: '2026-08-07', workflow_run_id: 'r-9761', final_score: null, rounds: 2, converged: false, exit_reason: '上游 LLM 超时' },
    ],
  },
  task_logs: [
    { id: 'l-001', task_id: 't-001', task_name: 'Curate daily news', start_time: new Date(Date.now() - 1080_000).toISOString(), end_time: new Date(Date.now() - 1080_000).toISOString(), status: 'success', message: '精选 12 条 · 已投递飞书' },
    { id: 'l-002', task_id: 't-002', task_name: 'GitHub trending watcher', start_time: new Date(Date.now() - 1500_000).toISOString(), end_time: null, status: 'running', message: '正在抓取 Trending 仓库' },
    { id: 'l-003', task_id: 't-003', task_name: 'RSS collector', start_time: new Date(Date.now() - 2460_000).toISOString(), end_time: new Date(Date.now() - 2460_000).toISOString(), status: 'success', message: '收到 64 条 · 标准化 61 条' },
    { id: 'l-004', task_id: 't-004', task_name: 'Memory extraction', start_time: new Date(Date.now() - 3600_000).toISOString(), end_time: new Date(Date.now() - 3600_000).toISOString(), status: 'error', message: '上游 LLM 超时，已重试 2 次' },
    { id: 'l-005', task_id: 't-006', task_name: 'WeChat publisher', start_time: new Date(Date.now() - 3600_000).toISOString(), end_time: new Date(Date.now() - 3600_000).toISOString(), status: 'success', message: '已写入草稿箱 · 等待人工复核' },
  ],
}

function readNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && !Number.isNaN(value) ? value : fallback
}

function readNullableNumber(value: unknown): number | null {
  if (typeof value === 'number' && !Number.isNaN(value)) return value
  return null
}

function readString(value: unknown, fallback = '—'): string {
  return typeof value === 'string' ? value : fallback
}

function normalizeOverview(raw: Record<string, unknown> | null): OverviewShape {
  if (!raw) return fallbackOverview
  const usage = (raw.usage as Record<string, unknown> | undefined) ?? {}
  const usageByModelRaw = Array.isArray(raw.usage_by_model) ? raw.usage_by_model : []
  const iterationsRaw = Array.isArray(raw.iterations) ? raw.iterations : []
  const evaluationRaw = (raw.evaluation as Record<string, unknown> | undefined) ?? {}
  const summary = (evaluationRaw.today_summary as Record<string, unknown> | undefined) ?? {}
  const recent = Array.isArray(evaluationRaw.recent) ? evaluationRaw.recent : []
  const publish = (raw.publish as Record<string, unknown> | undefined) ?? {}

  return {
    usage: {
      date: readString(usage.date, '—'),
      input_tokens: readNumber(usage.input_tokens),
      output_tokens: readNumber(usage.output_tokens),
      total_tokens: readNumber(usage.total_tokens),
      llm_calls: readNumber(usage.llm_calls),
      task_count: readNumber(usage.task_count),
    },
    cost_usd: readNumber(raw.cost_usd),
    publish: {
      success: readNumber(publish.success),
      error: readNumber(publish.error),
      total: readNumber(publish.total, readNumber(publish.success) + readNumber(publish.error)),
    },
    usage_by_model: usageByModelRaw.map((row) => {
      const item = row as Record<string, unknown>
      return {
        date: readString(item.date),
        model_name: readString(item.model_name, 'unknown'),
        input_tokens: readNumber(item.input_tokens),
        output_tokens: readNumber(item.output_tokens),
        total_tokens: readNumber(item.total_tokens, readNumber(item.input_tokens) + readNumber(item.output_tokens)),
        llm_calls: readNumber(item.llm_calls),
        cost_usd: readNumber(item.cost_usd),
      }
    }),
    iterations: iterationsRaw.map((row) => {
      const item = row as Record<string, unknown>
      return {
        workflow_run_id: readString(item.workflow_run_id),
        step_id: readString(item.step_id),
        round: readNumber(item.round),
        score: readNullableNumber(item.score),
        converged: Boolean(item.converged),
        reason: readString(item.reason),
      }
    }),
    evaluation: {
      today_summary: {
        avg_final_score: readNullableNumber(summary.avg_final_score),
        total_runs: readNumber(summary.total_runs),
        converge_rate: readNumber(summary.converge_rate),
        converged_runs: readNumber(summary.converged_runs),
      },
      recent: recent.map((row) => {
        const item = row as Record<string, unknown>
        return {
          date: readString(item.date),
          workflow_run_id: readString(item.workflow_run_id),
          final_score: readNullableNumber(item.final_score),
          rounds: readNumber(item.rounds),
          converged: Boolean(item.converged),
          exit_reason: readString(item.exit_reason),
        }
      }),
    },
    task_logs: Array.isArray(raw.task_logs) ? raw.task_logs as Array<Record<string, unknown>> : [],
  }
}

export function OperationsPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const overviewRemote = useRemoteData<Record<string, unknown>>(() => operationsApi.getOverview())
  const alertsRemote = useRemoteData<Array<Record<string, unknown>>>(() => alertsApi.list({ limit: 20 }))
  const iterationsRemote = useRemoteData<Array<Record<string, unknown>>>(() => workflowIterationsApi.list({ limit: 20 }))

  const overview = normalizeOverview(overviewRemote.data)
  const loading = overviewRemote.loading && !overviewRemote.data
  const error = overviewRemote.error?.message ?? null
  const hasData = Boolean(overviewRemote.data)
  const modelCount = overview.usage_by_model.length
  const successRate = overview.publish.total === 0 ? 0 : Math.round((overview.publish.success / overview.publish.total) * 100)
  const iterations = iterationsRemote.data?.length ? iterationsRemote.data.map((row) => {
    const item = row as Record<string, unknown>
    return {
      workflow_run_id: readString(item.workflow_run_id),
      step_id: readString(item.step_id),
      round: readNumber(item.round),
      score: readNullableNumber(item.score),
      converged: Boolean(item.converged),
      reason: readString(item.reason),
    }
  }) : overview.iterations

  useEffect(() => {
    if (overviewRemote.error) onFlash(`运营数据加载失败：${overviewRemote.error.message}`)
  }, [overviewRemote.error, onFlash])

  return (
    <>
      <SectionHeading
        icon={<ListChecks />}
        title="运营中心"
        description="对接 /api/dashboard/overview、/api/alerts、/api/workflow-iterations。"
        actions={
          <button className="btn btn-primary" type="button" onClick={() => { void overviewRemote.reload(); onFlash('正在刷新运营数据…') }}>
            <RefreshCw /> 刷新
          </button>
        }
      />

      <DataStatus
        loading={loading}
        error={error}
        empty={!hasData && !loading}
        emptyTitle="暂无运营数据"
        emptyDescription="完成首次任务运行后，Token、成本与运行记录会显示在这里。"
        onRetry={() => void overviewRemote.reload()}
      >
        <section className="section">
          <div className="metric-grid">
            <MetricCard label="今日输入 Token" value={formatNumber(overview.usage.input_tokens)} note={`${formatNumber(overview.usage.llm_calls)} 次模型调用`} icon={<DollarSign />} tone="blue" />
            <MetricCard label="今日输出 Token" value={formatNumber(overview.usage.output_tokens)} note={`累计 ${formatNumber(overview.usage.total_tokens)} Token`} icon={<DollarSign />} tone="violet" />
            <MetricCard label="今日 LLM 成本" value={formatCost(overview.cost_usd)} note={`${modelCount} 个模型参与`} icon={<DollarSign />} tone="sun" />
            <MetricCard label="发布成功率" value={`${successRate}%`} note={`${overview.publish.success} 成功 · ${overview.publish.error} 失败`} icon={<CheckCircle2 />} tone="pink" />
          </div>
        </section>

        <section className="section operations-panel">
          <SectionHeading
            title="按模型成本和 Token"
            description="当日每个模型的输入/输出 Token、调用次数与折算成本。"
          />
          <div className="data-table-card">
            {overview.usage_by_model.length === 0 ? (
              <div className="empty-state">暂无模型 Token 记录</div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>模型</th>
                    <th>输入 Tokens</th>
                    <th>输出 Tokens</th>
                    <th>调用次数</th>
                    <th>成本</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.usage_by_model.map((item) => (
                    <tr key={`${item.date}-${item.model_name}`}>
                      <td className="data-table-primary">
                        <strong>{item.model_name}</strong>
                        <small>{item.date}</small>
                      </td>
                      <td>{formatNumber(item.input_tokens)}</td>
                      <td>{formatNumber(item.output_tokens)}</td>
                      <td>{formatNumber(item.llm_calls)}</td>
                      <td>{formatCost(item.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="section operations-panel">
          <SectionHeading
            title="最近 Loop 迭代"
            description="来自 /api/workflow-iterations：每次 Loop 步骤的轮次、评分与收敛原因。"
          />
          <div className="data-table-card">
            {iterations.length === 0 ? (
              <div className="empty-state">暂无迭代记录</div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>工作流运行</th>
                    <th>步骤</th>
                    <th>轮次</th>
                    <th>评分</th>
                    <th>状态</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {iterations.map((item) => (
                    <tr key={`${item.workflow_run_id}-${item.step_id}-${item.round}`}>
                      <td className="data-table-primary">
                        <strong>{item.workflow_run_id}</strong>
                      </td>
                      <td><span className="pill pill-neutral">{item.step_id}</span></td>
                      <td>{item.round}</td>
                      <td>{item.score === null ? '—' : item.score.toFixed(2)}</td>
                      <td>
                        <span className={`run-pill run-pill-${item.converged ? 'success' : 'running'}`}>
                          {item.converged ? '已收敛' : '继续迭代'}
                        </span>
                      </td>
                      <td>{item.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <section className="section">
          <SectionHeading
            icon={<CheckCircle2 />}
            title="策展质量评估"
            description="今日评分汇总 + 最近 4 次运行的退出原因。"
          />
          <div className="metric-grid metric-grid-compact">
            <MetricCard label="今日平均评分" value={overview.evaluation.today_summary.avg_final_score === null ? '-' : overview.evaluation.today_summary.avg_final_score.toFixed(2)} note={`${overview.evaluation.today_summary.total_runs} 次运行`} icon={<CheckCircle2 />} tone="blue" />
            <MetricCard label="Loop 收敛率" value={`${overview.evaluation.today_summary.converge_rate.toFixed(0)}%`} note={`${overview.evaluation.today_summary.converged_runs} 次已收敛`} icon={<History />} tone="violet" />
            <MetricCard label="告警" value={String(alertsRemote.data?.length ?? 0)} note="近 20 条告警" icon={<CircleAlert />} tone="pink" />
          </div>

          <DataPanel
            icon={<History />}
            title=""
            rows={overview.evaluation.recent.map((item) => ({
              key: item.workflow_run_id,
              primary: item.date,
              secondary: item.workflow_run_id,
              cells: [
                { label: '评分', value: item.final_score === null ? '-' : item.final_score.toFixed(2) },
                { label: '轮次', value: String(item.rounds) },
                { label: '收敛', value: item.converged ? '已收敛' : '未收敛', pill: item.converged ? 'success' : 'error' },
                { label: '退出原因', value: item.exit_reason },
              ],
            }))}
            emptyText="暂无策展质量评估"
          />
        </section>

        <DataPanel
          icon={<ListChecks />}
          title="最近任务日志"
          rows={overview.task_logs.map((log) => {
            const taskName = readString(log.task_name, '后台任务')
            const message = readString(log.message, '')
            const status = readString(log.status, 'pending')
            const start = typeof log.start_time === 'string' ? log.start_time : null
            return {
              key: readString(log.id, taskName + start),
              primary: taskName,
              secondary: message,
              cells: [
                { label: '状态', value: status === 'success' ? '成功' : status === 'running' ? '运行中' : status === 'error' ? '失败' : status, pill: status === 'running' ? 'running' : status === 'success' ? 'success' : status === 'error' ? 'error' : 'pending' },
                { label: '时间', value: formatRelativeTime(start) },
              ],
            }
          })}
          emptyText="暂无任务日志"
        />
      </DataStatus>
    </>
  )
}

function formatNumber(value: MaybeNumber): string {
  return typeof value === 'number' ? value.toLocaleString('zh-CN') : '0'
}

function formatCost(value: number): string {
  return `$${value.toFixed(2)}`
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return '—'
  const value = Date.parse(iso)
  if (Number.isNaN(value)) return iso
  const diff = Math.max(0, Date.now() - value)
  const minutes = Math.round(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`
  return `${Math.round(minutes / 1440)} 天前`
}

function MetricCard({ label, value, note, icon, tone }: { label: string; value: string; note: string; icon: ReactElement; tone: 'blue' | 'violet' | 'sun' | 'pink' }): ReactElement {
  return (
    <article className={`metric metric-${tone}`}>
      <div className="metric-icon" aria-hidden="true">{icon}</div>
      <div>
        <strong>{value}</strong>
        <small>{label}</small>
        <p>{note}</p>
      </div>
    </article>
  )
}

interface DataPanelRow {
  key: string
  primary: string
  secondary: string
  cells: Array<{ label: string; value: string; pill?: 'success' | 'running' | 'error' | 'pending' }>
}

function DataPanel({ icon, title, rows, emptyText }: { icon: ReactElement; title: string; rows: DataPanelRow[]; emptyText: string }): ReactElement {
  return (
    <section className="section">
      {title && (
        <SectionHeading icon={icon} title={title} />
      )}
      <div className="data-table-card">
        {rows.length === 0 ? (
          <div className="empty-state">{emptyText}</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>条目</th>
                {rows[0]?.cells.map((cell, index) => <th key={index}>{cell.label}</th>) ?? null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key}>
                  <td className="data-table-primary">
                    <strong>{row.primary}</strong>
                    {row.secondary && <small>{row.secondary}</small>}
                  </td>
                  {row.cells.map((cell, index) => (
                    <td key={index}>
                      {cell.pill ? <span className={`run-pill run-pill-${cell.pill}`}>{cell.value}</span> : cell.value}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}