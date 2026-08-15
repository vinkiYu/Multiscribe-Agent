import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { Check, CircleAlert, ExternalLink, Files, Filter, ListChecks, RefreshCw, Search, Send, Tag, X } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { contentApi } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'
import type { ContentItem, ContentStatus } from '../types'

const sectionOptions = ['全部', '产品与功能更新', '前沿研究', '行业展望', '开源 TOP 项目']
const statusOptions = ['全部', '待筛选', '已入选', '已忽略', '已发布']

function statusToLabel(status: string | null | undefined): string {
  if (status === 'pending' || status === null || status === undefined) return '待筛选'
  if (status === 'curated') return '已入选'
  if (status === 'ignored') return '已忽略'
  if (status === 'published') return '已发布'
  return status
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—'
  const stamp = Date.parse(value)
  if (Number.isNaN(stamp)) return value
  const diff = Math.max(0, Date.now() - stamp)
  const minutes = Math.round(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`
  return `${Math.round(minutes / 1440)} 天前`
}

interface SourceDataRow extends ContentItem {
  excerpt: string
  reason: string
  curator: string
  summary: string
  body: string
  tags: string[]
  status: ContentStatus
  section: string
  score: number | null
}

function hydrate(row: Record<string, unknown>): SourceDataRow {
  return {
    id: String(row.id ?? ''),
    title: String(row.title ?? '（无标题）'),
    url: String(row.url ?? ''),
    description: String(row.description ?? ''),
    published_date: String(row.published_date ?? ''),
    ingestion_date: (row.ingestion_date as string | null) ?? null,
    source: String(row.source ?? '未知来源'),
    category: String(row.category ?? '其他'),
    author: (row.author as string | null) ?? null,
    status: (row.status as ContentStatus | null) ?? 'pending',
    metadata: (row.metadata as Record<string, unknown>) ?? {},
    excerpt: String(row.description ?? ''),
    reason: '来自 /api/source-data/search 检索结果；后端尚未给出 AI 评分与筛选理由。',
    curator: row.author ? String(row.author) : '自动采集',
    summary: String(row.description ?? ''),
    body: String(row.description ?? ''),
    tags: (row.category ? [String(row.category)] : []),
    section: String(row.category ?? '其他'),
    score: null,
  }
}

export function ContentPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const [query, setQuery] = useState('')
  const searchRemote = useRemoteData<Array<Record<string, unknown>>>(() => contentApi.search('', 50), { enabled: false })
  const [items, setItems] = useState<SourceDataRow[]>([])
  const [activeId, setActiveId] = useState<string>('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [section, setSection] = useState<string>('全部')
  const [status, setStatus] = useState<string>('全部')
  const [pendingRun, setPendingRun] = useState(false)

  useEffect(() => {
    if (!activeId && items.length > 0) setActiveId(items[0].id)
  }, [activeId, items])

  useEffect(() => {
    if (searchRemote.data) {
      const hydrated = searchRemote.data.map(hydrate)
      setItems(hydrated)
    }
  }, [searchRemote.data])

  useEffect(() => {
    if (searchRemote.error) onFlash(`加载内容失败：${searchRemote.error.message}`)
  }, [searchRemote.error, onFlash])

  const filtered = useMemo(() => items.filter((item) => {
    if (section !== '全部' && item.section !== section) return false
    if (status !== '全部' && statusToLabel(item.status) !== status) return false
    if (query.trim() && !`${item.title}${item.summary}`.toLowerCase().includes(query.trim().toLowerCase())) return false
    return true
  }), [items, section, status, query])

  const active = items.find((item) => item.id === activeId) ?? null

  const runSearch = async (): Promise<void> => {
    if (!query.trim()) {
      await searchRemote.reload()
      return
    }
    try {
      const result = await contentApi.search(query.trim(), 50)
      const hydrated = result.map(hydrate)
      setItems(hydrated)
      onFlash(`检索到 ${hydrated.length} 条内容。`)
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '检索失败')
    }
  }

  const runBulk = async (action: 'curate' | 'ignore' | 'publish'): Promise<void> => {
    if (selected.size === 0) return
    try {
      await contentApi[action](Array.from(selected))
      onFlash(action === 'curate' ? `已入选 ${selected.size} 条内容。` : action === 'ignore' ? `已忽略 ${selected.size} 条内容。` : `已发布 ${selected.size} 条内容。`)
      setSelected(new Set())
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '操作失败')
    }
  }

  const updateStatus = async (id: string, next: 'curated' | 'ignored' | 'published', label: string): Promise<void> => {
    try {
      await contentApi[next === 'curated' ? 'curate' : next === 'ignored' ? 'ignore' : 'publish']([id])
      onFlash(`${label}。`)
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '操作失败')
    }
  }

  const triggerIngest = async (): Promise<void> => {
    setPendingRun(true)
    try {
      // Provide a generic fallback ingestion request — backend will use the first available adapter
      const result = await fetch('/api/dashboard/ingest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(window.localStorage.getItem('multiscribe_token') ? { Authorization: `Bearer ${window.localStorage.getItem('multiscribe_token')}` } : {}),
        },
        body: JSON.stringify({ adapter_configs: [] }),
      })
      if (!result.ok) throw new Error(`HTTP ${result.status}`)
      const payload = await result.json() as { result_count?: number; results?: unknown }
      const count = payload.result_count ?? (Array.isArray(payload.results) ? payload.results.length : 0)
      onFlash(`已触发采集：${count} 条新内容。`)
      await searchRemote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '采集失败')
    } finally {
      setPendingRun(false)
    }
  }

  const toggleSelect = (id: string): void => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = (): void => {
    setSelected((current) => {
      if (current.size === filtered.length) return new Set()
      return new Set(filtered.map((item) => item.id))
    })
  }

  return (
    <>
      <SectionHeading
        icon={<Files />}
        title="内容"
        description="对接 /api/source-data/search + /api/dashboard/ingest：检索与全量采集后筛选。"
        actions={
          <>
            <button className="btn" type="button" onClick={runSearch}>
              <RefreshCw /> 重新检索
            </button>
            <button className="btn btn-primary" type="button" onClick={triggerIngest} disabled={pendingRun}>
              <Send /> {pendingRun ? '采集中…' : '立即采集'}
            </button>
          </>
        }
      />

      <DataStatus
        loading={searchRemote.loading && items.length === 0}
        error={searchRemote.error?.message ?? null}
        empty={items.length === 0 && !searchRemote.loading}
        emptyTitle="暂无内容"
        emptyDescription="输入关键词检索，或点击「立即采集」让后端跑一次所有启用的适配器。"
        onRetry={runSearch}
      >
        <section className="section">
          <div className="content-filter-bar">
            <label className="content-search">
              <Search />
              <input
                type="search"
                value={query}
                placeholder="输入关键词检索内容"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') void runSearch() }}
              />
              {query && <button type="button" className="content-search-clear" aria-label="清除" onClick={() => setQuery('')}><X /></button>}
            </label>
            <FilterSelect label="分类" value={section} options={sectionOptions} onChange={setSection} />
            <FilterSelect label="状态" value={status} options={statusOptions} onChange={setStatus} />
            <span className="content-result-count">{filtered.length} 条</span>
          </div>

          {selected.size > 0 && (
            <div className="selection-bar">
              <span>已选择 <strong>{selected.size}</strong> 条</span>
              <div className="selection-actions">
                <button className="btn btn-sm" type="button" onClick={() => void runBulk('curate')}><Check /> 批量入选</button>
                <button className="btn btn-sm" type="button" onClick={() => void runBulk('ignore')}><CircleAlert /> 批量忽略</button>
                <button className="btn btn-sm btn-primary" type="button" onClick={() => void runBulk('publish')}><Send /> 批量发布</button>
                <button className="btn btn-sm btn-ghost" type="button" onClick={() => setSelected(new Set())}>取消</button>
              </div>
            </div>
          )}

          <div className="content-layout">
            <article className="content-list-panel">
              <header className="content-list-header">
                <label className="content-checkbox">
                  <input
                    type="checkbox"
                    checked={filtered.length > 0 && selected.size === filtered.length}
                    ref={(node) => { if (node) node.indeterminate = selected.size > 0 && selected.size < filtered.length }}
                    onChange={toggleSelectAll}
                  />
                  <span>条目</span>
                </label>
                <span>分类</span>
                <span>来源</span>
                <span>时间</span>
                <span>状态</span>
              </header>
              <ul className="content-list">
                {filtered.length === 0 ? (
                  <li className="content-list-empty">
                    <Filter />
                    <p>没有匹配筛选条件的结果。</p>
                  </li>
                ) : filtered.map((item) => {
                  const isActive = item.id === activeId
                  const isSelected = selected.has(item.id)
                  return (
                    <li
                      key={item.id}
                      className={[isActive ? 'is-active' : '', isSelected ? 'is-selected' : ''].filter(Boolean).join(' ')}
                      onClick={() => setActiveId(item.id)}
                    >
                      <label className="content-checkbox" onClick={(event) => event.stopPropagation()}>
                        <input type="checkbox" checked={isSelected} onChange={() => toggleSelect(item.id)} />
                      </label>
                      <div className="content-list-main">
                        <strong>{item.title}</strong>
                        <p>{item.summary}</p>
                      </div>
                      <span className="content-list-meta">{item.section}</span>
                      <span className="content-list-meta">{item.source}</span>
                      <time>{formatTimestamp(item.published_date)}</time>
                      <span className={`status-label status-${item.status}`}>{statusToLabel(item.status)}</span>
                    </li>
                  )
                })}
              </ul>
            </article>

            <aside className="content-detail-panel" aria-label="详情">
              {!active ? (
                <div className="state-panel"><Files /><h2>选择左侧条目</h2><p>条目选中后，可在此查看原文并对状态进行操作。</p></div>
              ) : (
                <>
                  <header className="content-detail-header">
                    <div>
                      <h2>{active.title}</h2>
                      <p>{active.source} · {active.section} · {formatTimestamp(active.published_date)}</p>
                    </div>
                    <span className="score-pill score-mid">
                      {active.score === null ? '未评分' : `AI 评分 ${active.score.toFixed(2)}`}
                    </span>
                  </header>

                  <section className="content-detail-section">
                    <h3>摘要</h3>
                    <p>{active.summary || '暂无摘要。'}</p>
                  </section>

                  <section className="content-detail-section">
                    <h3>原文</h3>
                    <p className="content-detail-body">{active.body}</p>
                    {active.url && (
                      <a className="content-detail-link" href={active.url} target="_blank" rel="noreferrer">
                        打开原文 <ExternalLink />
                      </a>
                    )}
                  </section>

                  <section className="content-detail-section">
                    <h3><Tag /> 标签</h3>
                    <div className="content-detail-tags">
                      {active.tags.length === 0 ? <span className="pill pill-neutral">未打标签</span> : active.tags.map((tag) => <span className="pill pill-neutral" key={tag}>{tag}</span>)}
                    </div>
                  </section>

                  <section className="content-detail-section">
                    <h3><ListChecks /> 来源</h3>
                    <p>采集人：{active.curator}</p>
                    <p>采集时间：{formatTimestamp(active.ingestion_date)}</p>
                  </section>

                  <footer className="content-detail-footer">
                    <button className="btn" type="button" onClick={() => void updateStatus(active.id, 'curated', '已入选该内容')} disabled={active.status === 'curated' || active.status === 'published'}>
                      <Check /> 入选
                    </button>
                    <button className="btn" type="button" onClick={() => void updateStatus(active.id, 'ignored', '已忽略该内容')} disabled={active.status === 'ignored'}>
                      <X /> 忽略
                    </button>
                    <button className="btn btn-primary" type="button" onClick={() => void updateStatus(active.id, 'published', '已发布该内容')} disabled={active.status === 'published'}>
                      <Send /> 发布
                    </button>
                  </footer>
                </>
              )}
            </aside>
          </div>
        </section>
      </DataStatus>
    </>
  )
}

function FilterSelect({ label, value, options, onChange, disabled }: { label: string; value: string; options: string[]; onChange: (next: string) => void; disabled?: boolean }): ReactElement {
  return (
    <label className="content-filter" style={disabled ? { opacity: 0.55 } : undefined}>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled}>
        {options.map((item) => <option key={item} value={item}>{item}</option>)}
      </select>
    </label>
  )
}