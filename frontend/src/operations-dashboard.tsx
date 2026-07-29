import { useEffect, useState, type ReactElement } from 'react'
import { CheckCircle2, CircleAlert, Cpu, History, ListChecks } from 'lucide-react'
import { ApiError, operationsApi, type OperationsOverview, type TaskLog } from './services/api'

function formatNumber(value: number): string { return value.toLocaleString('zh-CN') }
function taskLabel(log: TaskLog): string { return log.task_name || log.task_type || '后台任务' }
function taskStatus(log: TaskLog): string { return log.status === 'success' ? '成功' : log.status === 'error' ? '失败' : log.status || '未知' }
function exitReason(reason?: string): string { return ({ threshold: '达到评分阈值', condition: '满足退出条件', convergence: '评分已收敛', max_rounds: '达到最大轮次', stuck: '检测到停滞', continue: '继续迭代' }[reason || ''] ?? reason ?? '暂无记录') }

export function OperationsDashboardPage(): ReactElement {
  const [data, setData] = useState<OperationsOverview | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  useEffect(() => { void operationsApi.getOverview().then(setData).catch((caught) => setError(caught instanceof ApiError ? caught : new ApiError('unknown', '读取运营数据失败。'))) }, [])
  if (error) return <section className="data-panel"><p>{error.message}</p></section>
  if (!data) return <section className="data-panel"><p>正在加载运营数据…</p></section>
  return <OperationsDashboard data={data} />
}

function OperationsDashboard({ data }: { data: OperationsOverview }): ReactElement {
  const publishRate = data.publish.total === 0 ? 0 : Math.round((data.publish.success / data.publish.total) * 100)
  const evaluation = data.evaluation.today_summary
  const latestEvaluation = data.evaluation.recent[0]
  return <div className="data-stack operations-dashboard">
    <div className="metric-grid">
      <article className="metric blue"><div><span>今日输入 Token</span><Cpu /></div><strong>{formatNumber(data.usage.input_tokens)}</strong><p>{formatNumber(data.usage.llm_calls)} 次模型调用</p></article>
      <article className="metric purple"><div><span>今日输出 Token</span><Cpu /></div><strong>{formatNumber(data.usage.output_tokens)}</strong><p>累计 {formatNumber(data.usage.total_tokens)} Token</p></article>
      <article className="metric pink"><div><span>发布成功率</span><CheckCircle2 /></div><strong>{publishRate}%</strong><p>{data.publish.success} 成功 · {data.publish.error} 失败</p></article>
    </div>
    <section className="data-panel"><div className="data-summary"><History /><span>最近 Loop 迭代</span></div>{data.iterations.length === 0 ? <p className="empty-inline">暂无迭代记录</p> : <div className="table-wrap"><table><thead><tr><th>运行 / 步骤</th><th>轮次</th><th>评分</th><th>状态</th><th>原因</th></tr></thead><tbody>{data.iterations.map((item) => <tr key={`${item.workflow_run_id}-${item.step_id}-${item.round}`}><td><strong>{item.workflow_run_id}</strong><small>{item.step_id}</small></td><td>{item.round}</td><td>{item.score === null ? '-' : item.score.toFixed(2)}</td><td>{item.converged ? '已收敛' : '继续迭代'}</td><td>{item.reason || '-'}</td></tr>)}</tbody></table></div>}</section>
    <section className="data-panel"><div className="data-summary"><CheckCircle2 /><span>策展质量评估</span></div><div className="metric-grid"><article className="metric blue"><div><span>今日平均评分</span><CheckCircle2 /></div><strong>{evaluation.avg_final_score === null ? '-' : evaluation.avg_final_score.toFixed(2)}</strong><p>{evaluation.total_runs} 次运行</p></article><article className="metric purple"><div><span>Loop 收敛率</span><History /></div><strong>{evaluation.converge_rate.toFixed(0)}%</strong><p>{evaluation.converged_runs} 次已收敛</p></article><article className="metric pink"><div><span>最近退出原因</span><CircleAlert /></div><strong>{exitReason(latestEvaluation?.exit_reason)}</strong><p>{latestEvaluation ? `${latestEvaluation.rounds} 轮 · ${latestEvaluation.result_count} 条结果` : '暂无评估记录'}</p></article></div>{data.evaluation.recent.length === 0 ? <p className="empty-inline">暂无策展质量评估</p> : <div className="table-wrap"><table><thead><tr><th>日期 / 运行</th><th>评分</th><th>轮次</th><th>收敛</th><th>退出原因</th></tr></thead><tbody>{data.evaluation.recent.map((item) => <tr key={item.workflow_run_id}><td><strong>{item.date}</strong><small>{item.workflow_run_id}</small></td><td>{item.final_score === null ? '-' : item.final_score.toFixed(2)}</td><td>{item.rounds}</td><td>{item.converged ? '已收敛' : '未收敛'}</td><td>{exitReason(item.exit_reason)}</td></tr>)}</tbody></table></div>}</section>
    <section className="data-panel"><div className="data-summary"><ListChecks /><span>最近任务日志</span></div>{data.task_logs.length === 0 ? <p className="empty-inline">暂无任务日志</p> : <div className="table-wrap"><table><thead><tr><th>任务</th><th>状态</th><th>时间</th><th>消息</th></tr></thead><tbody>{data.task_logs.map((log, index) => <tr key={String(log.id ?? index)}><td>{taskLabel(log)}</td><td><span className={`status-label ${log.status === 'success' ? 'ready' : 'error'}`}><CircleAlert />{taskStatus(log)}</span></td><td>{log.finished_at || log.created_at || log.started_at || '-'}</td><td>{log.message || '-'}</td></tr>)}</tbody></table></div>}</section>
  </div>
}
