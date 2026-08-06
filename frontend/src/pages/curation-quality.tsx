import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { BarChart3, CheckCircle2, CircleAlert, Repeat2, Sparkles } from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ApiError, curationStatsApi, operationsApi, type CurationEvaluationsSummary, type DailyCurationStat } from '../services/api'
import { CurationDrawer } from '../shared/curation-drawer'

const REASON_COLORS = ['var(--blue)', 'var(--purple)', 'var(--pink)', 'var(--sun)', 'var(--cyan)']
const EXIT_REASON_LABELS: Record<string, string> = { threshold: '达到评分阈值', convergence: '已收敛', max_rounds: '达到轮次上限', budget_exhausted: '预算耗尽' }

export function CurationQualityPage(): ReactElement {
  const [stats, setStats] = useState<DailyCurationStat[]>([])
  const [summary, setSummary] = useState<CurationEvaluationsSummary | null>(null)
  const [baseline, setBaseline] = useState<number | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [drawerDate, setDrawerDate] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    void Promise.all([curationStatsApi.getByPeriod(), operationsApi.getOverview(), curationStatsApi.getBaseline()])
      .then(([nextStats, overview, nextBaseline]) => { if (active) { setStats(nextStats); setSummary(overview.evaluation.today_summary); setBaseline(nextBaseline.avg_f1) } })
      .catch((caught: unknown) => { if (active) setError(caught instanceof ApiError ? caught : new ApiError('unknown', '读取策展质量数据失败')) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const roundsHistogram = useMemo(() => {
    const counts = new Map<number, number>()
    stats.forEach((stat) => counts.set(stat.rounds, (counts.get(stat.rounds) ?? 0) + 1))
    return [...counts.entries()].sort(([left], [right]) => left - right).map(([rounds, count]) => ({ rounds: `第 ${rounds} 轮`, count }))
  }, [stats])
  const reasonData = useMemo(() => {
    const counts = new Map<string, number>()
    stats.forEach((stat) => counts.set(stat.exit_reason, (counts.get(stat.exit_reason) ?? 0) + 1))
    return [...counts.entries()].map(([name, value]) => ({ name: EXIT_REASON_LABELS[name] ?? name, value }))
  }, [stats])

  if (loading) return <div className="curation-quality-state"><Sparkles /><strong>正在加载策展质量...</strong></div>
  if (error) return <div className="curation-quality-state is-error"><CircleAlert /><strong>{error.message}</strong><button className="button" onClick={() => window.location.reload()}>重新加载</button></div>

  const averageScore = summary?.avg_final_score
  const ciBaseline = baseline ?? stats.find((stat) => stat.ci_baseline !== undefined)?.ci_baseline ?? null
  return <div className="curation-quality-page">
    <header className="curation-quality-header"><div><span className="eyebrow"><Sparkles />运营指标</span><h2>策展质量</h2><p>观察每日资讯精选的评分、收敛表现和产出效率。</p></div><span className="curation-period">最近 30 天</span></header>
    <div className="ci-baseline-banner" role="status"><strong>CI 回归基线</strong><span>{ciBaseline === null ? '尚未生成' : `Precision/Recall F1 ${(ciBaseline * 100).toFixed(1)}%`}</span><small>用于比较离线策展评测与线上最终评分，不替代趋势图。</small></div>
    <section className="metric-grid curation-metric-grid">
      <Metric label="收敛率" value={`${(summary?.converge_rate ?? 0).toFixed(1)}%`} note={`${summary?.converged_runs ?? 0} / ${summary?.total_runs ?? 0} 次运行`} icon={CheckCircle2} tone="blue" />
      <Metric label="平均迭代轮次" value={(summary?.avg_rounds ?? 0).toFixed(1)} note="每次策展循环的平均轮次" icon={Repeat2} tone="purple" />
      <Metric label="平均精选分" value={averageScore === null || averageScore === undefined ? '—' : averageScore.toFixed(1)} note="基于已记录的最终评分" icon={BarChart3} tone="pink" />
    </section>
    <section className="chart-grid">
      <ChartCard title="最终评分趋势" description="按策展运行记录观察质量变化" className="chart-card-wide"><ResponsiveContainer width="100%" height={220}><AreaChart data={stats}><defs><linearGradient id="curationScoreGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--blue)" stopOpacity={0.35} /><stop offset="100%" stopColor="var(--blue)" stopOpacity={0.03} /></linearGradient></defs><CartesianGrid stroke="var(--hairline)" strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={shortDate} /><YAxis domain={[0, 10]} /><Tooltip /><Area type="monotone" dataKey="final_score" connectNulls stroke="var(--blue)" fill="url(#curationScoreGradient)" /></AreaChart></ResponsiveContainer></ChartCard>
      <ChartCard title="Loop 轮次分布" description="不同轮次完成的运行数量"><ResponsiveContainer width="100%" height={220}><BarChart data={roundsHistogram}><CartesianGrid stroke="var(--hairline)" strokeDasharray="3 3" /><XAxis dataKey="rounds" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" fill="var(--purple)" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></ChartCard>
      <ChartCard title="退出原因占比" description="查看循环主要在哪个条件下退出"><ResponsiveContainer width="100%" height={220}><PieChart><Pie data={reasonData} dataKey="value" nameKey="name" innerRadius={52} outerRadius={82} paddingAngle={3}>{reasonData.map((entry, index) => <Cell key={entry.name} fill={REASON_COLORS[index % REASON_COLORS.length]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer></ChartCard>
      <ChartCard title="精选与扫描" description="产出数量和候选规模的变化"><ResponsiveContainer width="100%" height={220}><LineChart data={stats}><CartesianGrid stroke="var(--hairline)" strokeDasharray="3 3" /><XAxis dataKey="date" tickFormatter={shortDate} /><YAxis allowDecimals={false} /><Tooltip /><Line type="monotone" dataKey="result_count" name="精选数" connectNulls stroke="var(--pink)" strokeWidth={2} /><Line type="monotone" dataKey="total_scanned" name="扫描数" connectNulls stroke="var(--muted)" strokeDasharray="4 4" /></LineChart></ResponsiveContainer></ChartCard>
    </section>
    <section className="curation-history-panel"><header><div><h3>历史策展明细</h3><p>点击日期查看当日公开归档中的精选资讯。</p></div><span>{stats.length} 条记录</span></header><div className="table-wrap"><table className="curation-history-table"><thead><tr><th>日期</th><th>最终分</th><th>精选数</th><th>扫描数</th><th>效率</th><th>收敛</th><th>退出原因</th><th /></tr></thead><tbody>{stats.length === 0 ? <tr><td colSpan={8} className="table-empty">暂无策展评估记录</td></tr> : stats.map((stat, index) => <tr key={`${stat.date}-${index}`}><td>{stat.date}</td><td>{stat.final_score === null ? '—' : stat.final_score.toFixed(1)}</td><td>{stat.result_count ?? '—'}</td><td>{stat.total_scanned ?? '—'}</td><td>{stat.efficiency === null ? '—' : `${(stat.efficiency * 100).toFixed(1)}%`}</td><td><span className={`status-label ${stat.converged ? 'ready' : 'error'}`}>{stat.converged ? '是' : '否'}</span></td><td>{EXIT_REASON_LABELS[stat.exit_reason] ?? stat.exit_reason}</td><td><button className="table-action" onClick={() => setDrawerDate(stat.date)}>查看</button></td></tr>)}</tbody></table></div></section>
    <CurationDrawer date={drawerDate} open={drawerDate !== null} onClose={() => setDrawerDate(null)} />
  </div>
}

function Metric({ label, value, note, icon: Icon, tone }: { label: string; value: string; note: string; icon: typeof CheckCircle2; tone: string }): ReactElement { return <article className={`metric ${tone}`}><div><span>{label}</span><Icon /></div><strong>{value}</strong><p>{note}</p></article> }
function ChartCard({ title, description, className = '', children }: { title: string; description: string; className?: string; children: ReactElement }): ReactElement { return <article className={`chart-card ${className}`}><header><div><h3>{title}</h3><p>{description}</p></div></header><div className="chart-container">{children}</div></article> }
function shortDate(value: string): string { return value.slice(5) }
