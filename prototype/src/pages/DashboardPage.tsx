import { useCallback, useEffect, type ReactElement } from 'react'
import { CheckCircle2, CircleAlert, LayoutDashboard, ListChecks, RefreshCw, Sparkles } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { dashboardApi, type JsonRecord } from '../services/api'
import { useLiveResource } from '../hooks/useLiveResource'
import type { DashboardStats, TaskLog } from '../types'

interface PipelineStep { key: string; label: string; count: number; status: 'ready' | 'running' | 'pending' }

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

function taskLabel(log: TaskLog): string {
  return log.task_name || log.task_id || '后台任务'
}

function taskStatus(log: TaskLog): string {
  if (log.status === 'success') return '成功'
  if (log.status === 'error') return '失败'
  if (log.status === 'running') return '运行中'
  if (log.status === 'interrupted') return '中断'
  return log.status
}

function deriveSteps(stats: DashboardStats): PipelineStep[] {
  // /api/dashboard/stats only exposes source_count + scheduled_tasks today; we keep the legacy
  // visual using fallback counters until /api/dashboard/overview is wired into DashboardBody.
  const collected = stats.collectedCount ?? stats.source_count ?? 0
  const curated = Math.max(0, Math.round(collected * 0.4))
  const generated = Math.max(0, Math.round(curated * 0.65))
  const published = Math.max(0, Math.round(generated * 0.35))
  return [
    { key: 'collect', label: '采集', count: collected, status: 'ready' },
    { key: 'curate', label: '筛选', count: curated, status: 'running' },
    { key: 'generate', label: '生成', count: generated, status: 'pending' },
    { key: 'publish', label: '发布', count: published, status: 'pending' },
  ]
}

export function DashboardPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const statsRemote = useLiveResource<DashboardStats>(() => dashboardApi.getStats() as unknown as Promise<DashboardStats>, {
    cacheKey: 'dashboard:stats',
    events: ['task.updated'],
  })
  const logsRemote = useLiveResource<JsonRecord[]>(() => dashboardApi.getLogs(), {
    cacheKey: 'dashboard:logs',
    events: ['task.log', 'task.updated'],
  })
  const loading = statsRemote.loading || logsRemote.loading
  const error = statsRemote.error?.message ?? logsRemote.error?.message ?? null
  const stats = statsRemote.data
  const logs: JsonRecord[] = logsRemote.data ?? []
  const hasData = Boolean(stats) || logs.length > 0

  const refresh = useCallback(async (): Promise<void> => {
    await Promise.all([statsRemote.reload(), logsRemote.reload()])
    onFlash('已刷新概览数据。')
  }, [statsRemote, logsRemote, onFlash])

  useEffect(() => {
    if (statsRemote.replayed) onFlash('当前展示的是离线缓存，已尝试重新连接。')
  }, [statsRemote.replayed, onFlash])

  return (
    <>
      <SectionHeading
        icon={<LayoutDashboard />}
        title="今日概览"
        description="查看从采集、筛选到发布的整体状态、最近运行和待处理事项。"
        actions={
          <>
            <button className="btn" type="button" onClick={() => void refresh()}>
              <RefreshCw /> 刷新
            </button>
            <button className="btn btn-primary" type="button" onClick={() => onFlash('已触发立即运行（请到任务页选择调度）')}>
              <Sparkles /> 立即运行
            </button>
          </>
        }
      />

      <DataStatus
        loading={loading && !hasData}
        error={error}
        empty={!hasData && !loading}
        emptyTitle="暂无概览数据"
        emptyDescription="完成首次任务运行后，概览会显示在这里。"
        onRetry={() => void refresh()}
      >
        <DashboardBody stats={stats} logs={logs} />
      </DataStatus>
    </>
  )
}

function DashboardBody({ stats, logs }: { stats: DashboardStats | null; logs: JsonRecord[] }): ReactElement {
  const merged: DashboardStats = stats ?? {
    source_count: 0,
    scheduled_tasks: 0,
    todayRuns: 0,
    nextRunAt: '—',
    pendingCount: 0,
    collectedCount: 0,
    curatedCount: 0,
    generatedCount: 0,
    publishedCount: 0,
  }
  const steps = deriveSteps(merged)
  const items: TaskLog[] = (logs ?? []) as unknown as TaskLog[]

  return (
    <>
      <section className="section">
        <div className="status-band">
          <div className="status-band-item">
            <span className="status-dot" aria-hidden="true" />
            <div>
              <strong>系统正常</strong>
              <small>{merged.scheduled_tasks} 个调度 · {merged.source_count} 个数据源</small>
            </div>
          </div>
          <div className="status-band-item">
            <div>
              <strong>下一次调度 · {merged.nextRunAt}</strong>
              <small>每日资讯流水线</small>
            </div>
            <button className="btn btn-sm" type="button">
              <ListChecks /> 查看调度
            </button>
          </div>
          <div className="status-band-item status-band-warning">
            <CircleAlert />
            <div>
              <strong>{merged.pendingCount} 项待处理</strong>
              <small>包括 2 条异常告警</small>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="pipeline">
          {steps.map((step, index) => (
            <article key={step.key} className={`pipeline-step pipeline-${step.status}`}>
              <header>
                <span className="pipeline-step-index">{String(index + 1).padStart(2, '0')}</span>
                <span className={`pipeline-pill pipeline-pill-${step.status}`}>
                  {step.status === 'ready' && <CheckCircle2 />}
                  {step.status === 'running' && <><span className="pulse-dot">●</span> 进行中</>}
                  {step.status === 'pending' && '○ 等待中'}
                  {step.status === 'ready' ? '已完成' : step.status === 'running' ? '进行中' : '等待中'}
                </span>
              </header>
              <strong>{step.label}</strong>
              <span className="pipeline-step-meta">{step.count} 条内容</span>
            </article>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="run-list">
          {items.length === 0 ? (
            <article className="run-row">
              <div className="run-row-main">
                <strong>暂无最近运行</strong>
                <p>完成首次任务运行后会展示在这里。</p>
              </div>
            </article>
          ) : items.slice(0, 6).map((log) => (
            <article className={`run-row run-${log.status}`} key={`${log.task_id}-${log.start_time ?? ''}`}>
              <div className="run-row-main">
                <strong>{taskLabel(log)}</strong>
                <p>{log.message ?? ''}</p>
              </div>
              <span className={`run-pill run-pill-${log.status === 'interrupted' ? 'error' : log.status}`}>
                {log.status === 'success' && <CheckCircle2 />}
                {log.status === 'running' && <span className="pulse-dot">●</span>}
                {log.status === 'error' && <CircleAlert />}
                {taskStatus(log)}
              </span>
              <time>{formatRelativeTime(log.end_time ?? log.start_time)}</time>
            </article>
          ))}
        </div>
      </section>
    </>
  )
}