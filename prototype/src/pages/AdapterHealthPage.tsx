import { useMemo, useState, type ReactElement } from 'react'
import { CircleAlert, Pause, Play, RadioTower, RefreshCw, Search } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { adapterHealthApi } from '../services/api'
import { useLiveResource } from '../hooks/useLiveResource'
import type { JsonRecord } from '../services/api'
import type { AdapterHealth } from '../types'

interface AdapterRow {
  id: string
  type: 'rss' | 'github' | 'ai_search' | 'wechat' | 'follow_opml' | 'feishu'
  status: 'enabled' | 'disabled'
  consecutiveFailures: number
  lastStatus: 'success' | 'running' | 'error'
  lastRunAt: string
  lastError: string | null
}

const typeLabel: Record<AdapterRow['type'], string> = {
  rss: 'RSS 采集',
  github: 'GitHub Trending',
  ai_search: 'AI 搜索',
  wechat: '微信投递',
  follow_opml: 'Follow OPML',
  feishu: '飞书投递',
}

function inferType(id: string): AdapterRow['type'] {
  if (id.includes('github')) return 'github'
  if (id.includes('ai-search') || id.includes('phind') || id.includes('perplexity')) return 'ai_search'
  if (id.includes('wechat')) return 'wechat'
  if (id.includes('follow')) return 'follow_opml'
  if (id.includes('feishu')) return 'feishu'
  return 'rss'
}

function formatRunAt(iso: string | null): string {
  if (!iso) return '尚未运行'
  const value = Date.parse(iso)
  if (Number.isNaN(value)) return iso
  const diff = Math.max(0, Date.now() - value)
  const minutes = Math.round(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return `${Math.round(hours / 24)} 天前`
}

function mapAdapter(item: AdapterHealth): AdapterRow {
  return {
    id: item.adapter_id,
    type: inferType(item.adapter_id),
    status: item.disabled ? 'disabled' : 'enabled',
    consecutiveFailures: item.consecutive_failures,
    lastStatus: item.last_status === 'running' ? 'running' : item.last_status === 'success' ? 'success' : 'error',
    lastRunAt: formatRunAt(item.last_run_at),
    lastError: item.last_error,
  }
}

export function AdapterHealthPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const remote = useLiveResource<JsonRecord[]>(() => adapterHealthApi.list(), {
    cacheKey: 'adapter-health',
    events: ['adapter.health'],
  })
  const adapters = useMemo(() => (remote.data ?? []).map((row) => mapAdapter(row as unknown as AdapterHealth)), [remote.data])
  const loading = remote.loading && !remote.data
  const error = remote.error?.message ?? null
  const hasData = Boolean(remote.data)

  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'enabled' | 'disabled' | 'error'>('all')
  const [pendingId, setPendingId] = useState<string | null>(null)

  const filtered = adapters.filter((adapter) => {
    if (statusFilter === 'enabled' && adapter.status !== 'enabled') return false
    if (statusFilter === 'disabled' && adapter.status !== 'disabled') return false
    if (statusFilter === 'error' && !(adapter.consecutiveFailures > 0 || adapter.lastStatus === 'error')) return false
    if (query.trim() && !`${adapter.id}${typeLabel[adapter.type]}`.toLowerCase().includes(query.trim().toLowerCase())) return false
    return true
  })

  const summary = {
    total: adapters.length,
    enabled: adapters.filter((a) => a.status === 'enabled').length,
    erroring: adapters.filter((a) => a.consecutiveFailures > 0 || a.lastStatus === 'error').length,
    disabled: adapters.filter((a) => a.status === 'disabled').length,
  }

  const toggleAdapter = async (adapter: AdapterRow): Promise<void> => {
    setPendingId(adapter.id)
    try {
      if (adapter.status === 'enabled') {
        await adapterHealthApi.disable(adapter.id)
      } else {
        await adapterHealthApi.enable(adapter.id)
      }
      onFlash(adapter.status === 'enabled' ? `已停用 ${adapter.id}` : `已启用 ${adapter.id}`)
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '操作失败')
    } finally {
      setPendingId(null)
    }
  }

  return (
    <>
      <SectionHeading
        icon={<RadioTower />}
        title="适配器健康"
        description="查看采集适配器的连续失败次数、最近运行状态与运行时间，必要时手动启停。"
        actions={
          <button className="btn btn-primary" type="button" onClick={() => void remote.reload()}>
            <RefreshCw /> 刷新
          </button>
        }
      />

      <DataStatus
        loading={loading}
        error={error}
        empty={!hasData && !loading}
        emptyTitle="暂无适配器"
        emptyDescription="添加第一个数据源后，对应适配器会显示在这里。"
        onRetry={() => void remote.reload()}
      >
        <section className="section">
          <div className="adapter-summary">
            <SummaryCell label="总适配器" value={summary.total} tone="cyan" />
            <SummaryCell label="已启用" value={summary.enabled} tone="green" />
            <SummaryCell label="连续失败" value={summary.erroring} tone={summary.erroring > 0 ? 'amber' : 'muted'} />
            <SummaryCell label="已停用" value={summary.disabled} tone="muted" />
          </div>
        </section>

        {summary.erroring > 0 && (
          <section className="section">
            <div className="adapter-alert">
              <CircleAlert />
              <div>
                <strong>{summary.erroring} 个适配器出现连续失败</strong>
                <p>失败次数过多会自动停用对应适配器。可点击右侧「启用」恢复，或检查下方错误信息。</p>
              </div>
              <button className="btn btn-sm" type="button" onClick={() => onFlash('已通知所有失败适配器重试')}>
                一键重试
              </button>
            </div>
          </section>
        )}

        <section className="section">
          <div className="adapter-filter-bar">
            <label className="adapter-search">
              <Search />
              <input
                type="search"
                value={query}
                placeholder="搜索适配器 ID 或类型"
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <div className="adapter-filter-tabs" role="tablist">
              {[
                { key: 'all', label: '全部', count: summary.total },
                { key: 'enabled', label: '已启用', count: summary.enabled },
                { key: 'error', label: '异常', count: summary.erroring },
                { key: 'disabled', label: '已停用', count: summary.disabled },
              ].map((tab) => {
                const isActive = statusFilter === tab.key
                return (
                  <button
                    key={tab.key}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    className={isActive ? 'adapter-filter-tab is-active' : 'adapter-filter-tab'}
                    onClick={() => setStatusFilter(tab.key as typeof statusFilter)}
                  >
                    {tab.label} <span>{tab.count}</span>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="data-table-card">
            <table className="data-table adapter-table">
              <thead>
                <tr>
                  <th>标识</th>
                  <th>类型</th>
                  <th>状态</th>
                  <th>连续失败</th>
                  <th>最近一次</th>
                  <th>最近错误</th>
                  <th aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="adapter-empty">
                      没有匹配筛选条件的适配器。
                    </td>
                  </tr>
                ) : filtered.map((adapter) => (
                  <tr key={adapter.id}>
                    <td className="data-table-primary"><strong>{adapter.id}</strong></td>
                    <td><span className="pill pill-neutral">{typeLabel[adapter.type]}</span></td>
                    <td>
                      <span className={adapter.status === 'enabled' ? 'pill pill-builtin' : 'pill pill-neutral'}>
                        {adapter.status === 'enabled' ? '已启用' : '已停用'}
                      </span>
                    </td>
                    <td>
                      {adapter.consecutiveFailures === 0 ? (
                        <span className="adapter-fail-zero">0</span>
                      ) : (
                        <span className={`adapter-fail adapter-fail-${adapter.consecutiveFailures >= 3 ? 'high' : 'warn'}`}>{adapter.consecutiveFailures}</span>
                      )}
                    </td>
                    <td>
                      <div className="adapter-last">
                        <span className={`run-pill run-pill-${adapter.lastStatus}`}>{runLabel(adapter.lastStatus)}</span>
                        <time>{adapter.lastRunAt}</time>
                      </div>
                    </td>
                    <td><span className="adapter-error">{adapter.lastError ?? '—'}</span></td>
                    <td className="adapter-actions">
                      <button
                        type="button"
                        className={adapter.status === 'enabled' ? 'btn btn-sm' : 'btn btn-sm btn-primary'}
                        disabled={pendingId === adapter.id}
                        onClick={() => void toggleAdapter(adapter)}
                      >
                        {adapter.status === 'enabled' ? <><Pause /> 停用</> : <><Play /> 启用</>}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="capability-note">健康状态来自服务端持久化记录，停用适配器不会删除历史数据。</p>
        </section>
      </DataStatus>
    </>
  )
}

function SummaryCell({ label, value, tone }: { label: string; value: number; tone: 'green' | 'cyan' | 'amber' | 'muted' }): ReactElement {
  return (
    <article className={`metric metric-${tone}`}>
      <div><span>{label}</span></div>
      <strong>{value}</strong>
    </article>
  )
}

function runLabel(status: AdapterRow['lastStatus']): string {
  if (status === 'success') return '成功'
  if (status === 'running') return '运行中'
  return '失败'
}