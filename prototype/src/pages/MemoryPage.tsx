import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { BrainCircuit, CheckCircle2, Clock3, Pencil, Plus, RefreshCw, Search, Settings2, Sparkles, Trash } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { memoryApi, type JsonRecord } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'
import type { MemoryEntry, MemoryPreferences } from '../types'

interface PreferenceView {
  key: string
  label: string
  value: string
}

const preferenceLabels: Record<string, string> = {
  preferred_tags: '关注主题',
  block_sources: '不看来源',
  blocked_topics: '不看主题',
  push_time: '每日发送时间',
  importance_threshold: '重要程度阈值',
}

function formatTimestamp(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    const ms = value < 1e12 ? value * 1000 : value
    return formatIso(new Date(ms).toISOString())
  }
  return formatIso(value)
}

function formatIso(iso: string): string {
  const value = Date.parse(iso)
  if (Number.isNaN(value)) return iso
  const diff = Math.max(0, Date.now() - value)
  const minutes = Math.round(diff / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.round(minutes / 60)} 小时前`
  return `${Math.round(minutes / 1440)} 天前`
}

function categoryLabel(category: string | undefined): string {
  if (category === 'preference') return '偏好'
  if (category === 'fact') return '事实'
  if (category === 'person') return '人物'
  if (category === 'instruction') return '指令'
  return category ?? '其他'
}

function importanceTone(value: number): string {
  if (value >= 8) return 'mem-confidence-high'
  if (value >= 5) return 'mem-confidence-mid'
  return 'mem-confidence-low'
}

function preferencesToView(prefs: MemoryPreferences): PreferenceView[] {
  return [
    { key: 'preferred_tags', label: preferenceLabels.preferred_tags, value: prefs.preferred_tags.join(', ') },
    { key: 'block_sources', label: preferenceLabels.block_sources, value: prefs.block_sources.join(', ') },
    { key: 'blocked_topics', label: preferenceLabels.blocked_topics, value: prefs.blocked_topics.join(', ') },
    { key: 'push_time', label: preferenceLabels.push_time, value: prefs.push_time },
    { key: 'importance_threshold', label: preferenceLabels.importance_threshold, value: `${prefs.importance_threshold} / 10` },
  ]
}

const categories = ['all', 'preference', 'fact', 'person', 'instruction'] as const
type CategoryFilter = typeof categories[number]

export function MemoryPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const entriesRemote = useRemoteData<JsonRecord[]>(() => memoryApi.list({ limit: 200 }))
  const prefsRemote = useRemoteData<MemoryPreferences>(() => memoryApi.preferences())
  const entries = (entriesRemote.data ?? []) as unknown as MemoryEntry[]
  const prefs = prefsRemote.data
  const loading = (entriesRemote.loading || prefsRemote.loading) && !entriesRemote.data && !prefsRemote.data
  const error = entriesRemote.error?.message ?? prefsRemote.error?.message ?? null
  const hasData = Boolean(entriesRemote.data) || Boolean(prefsRemote.data)

  const [activeCategory, setActiveCategory] = useState<CategoryFilter>('all')
  const [query, setQuery] = useState('')
  const [activeId, setActiveId] = useState<string>('')

  useEffect(() => {
    if (!activeId && entries.length > 0) setActiveId(entries[0].id)
  }, [activeId, entries])

  const counts = useMemo(() => {
    const map: Record<string, number> = { all: entries.length }
    for (const entry of entries) {
      const key = entry.category ?? 'other'
      map[key] = (map[key] ?? 0) + 1
    }
    return map
  }, [entries])

  const filtered = useMemo(() => {
    return entries.filter((entry) => {
      if (activeCategory !== 'all' && entry.category !== activeCategory) return false
      if (query.trim() && !entry.content.toLowerCase().includes(query.trim().toLowerCase())) return false
      return true
    })
  }, [entries, activeCategory, query])

  const active = entries.find((entry) => entry.id === activeId) ?? filtered[0] ?? null

  const reload = async (): Promise<void> => {
    await Promise.all([entriesRemote.reload(), prefsRemote.reload()])
    onFlash('已刷新记忆数据。')
  }

  const removeEntry = async (id: string): Promise<void> => {
    try {
      await memoryApi.remove(id)
      onFlash(`已删除记忆条目 ${id}。`)
      if (activeId === id) setActiveId(filtered[0]?.id ?? '')
      await entriesRemote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '删除失败')
    }
  }

  const runExtract = async (): Promise<void> => {
    try {
      await memoryApi.extract(30)
      onFlash('已提交抽取任务，30 天内的对话会被抽取。')
      await entriesRemote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '抽取失败')
    }
  }

  const editPreferences = async (): Promise<void> => {
    if (!prefs) return
    const tags = window.prompt('关注主题（逗号分隔）', prefs.preferred_tags.join(', ')) ?? null
    if (tags === null) return
    const thresholdRaw = window.prompt('重要程度阈值 (0-10)', String(prefs.importance_threshold)) ?? null
    if (thresholdRaw === null) return
    const threshold = Number(thresholdRaw)
    if (Number.isNaN(threshold)) {
      onFlash('阈值必须是数字。')
      return
    }
    try {
      await memoryApi.savePreferences({
        preferred_tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean),
        block_sources: prefs.block_sources,
        blocked_topics: prefs.blocked_topics,
        push_time: prefs.push_time,
        importance_threshold: threshold,
      })
      onFlash('偏好已更新。')
      await prefsRemote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '更新失败')
    }
  }

  const createEntry = async (): Promise<void> => {
    const content = window.prompt('请输入要保存的记忆内容')
    if (!content) return
    try {
      await memoryApi.create({ content, importance: 5, tags: [] })
      onFlash('记忆条目已创建。')
      await entriesRemote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '创建失败')
    }
  }

  const preferenceViews = prefs ? preferencesToView(prefs) : []

  return (
    <>
      <SectionHeading
        icon={<BrainCircuit />}
        title="记忆"
        description="对接 /api/memory/*：浏览条目、调整偏好、触发抽取。"
        actions={
          <>
            <button className="btn" type="button" onClick={editPreferences} disabled={!prefs}>
              <Settings2 /> 编辑偏好
            </button>
            <button className="btn" type="button" onClick={createEntry}>
              <Plus /> 新建记忆
            </button>
            <button className="btn btn-primary" type="button" onClick={runExtract}>
              <Sparkles /> 立即抽取
            </button>
          </>
        }
      />

      <DataStatus
        loading={loading}
        error={error}
        empty={!hasData && !loading}
        emptyTitle="暂无记忆"
        emptyDescription="完成第一次对话后，偏好与事实会自动抽取到此处。"
        onRetry={reload}
      >
        {preferenceViews.length > 0 && (
          <section className="section">
            <div className="memory-preference-grid">
              {preferenceViews.map((item) => (
                <article key={item.key} className="memory-preference-card">
                  <header><Sparkles /><strong>{item.label}</strong></header>
                  <p>{item.value || '—'}</p>
                  <button className="btn btn-sm btn-ghost" type="button" onClick={editPreferences}>
                    <Pencil /> 编辑
                  </button>
                </article>
              ))}
            </div>
          </section>
        )}

        <section className="section">
          <div className="memory-tabs" role="tablist">
            {categories.map((key) => {
              const isActive = activeCategory === key
              const label = key === 'all' ? '全部' : categoryLabel(key)
              return (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  className={isActive ? 'memory-tab is-active' : 'memory-tab'}
                  onClick={() => setActiveCategory(key)}
                >
                  {label} <span>{counts[key] ?? 0}</span>
                </button>
              )
            })}
          </div>

          <div className="memory-search-row">
            <label className="memory-search">
              <Search />
              <input
                type="search"
                value={query}
                placeholder="搜索记忆条目内容"
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <button className="btn btn-sm" type="button" onClick={reload}>
              <RefreshCw /> 刷新
            </button>
          </div>

          <div className="memory-layout">
            <article className="memory-list" aria-label="记忆条目">
              {filtered.length === 0 ? (
                <div className="empty-card">
                  <div>
                    <div className="empty-icon" aria-hidden="true"><BrainCircuit /></div>
                    <h3 className="empty-title">没有匹配的条目</h3>
                    <p className="empty-description">试试切换到其他类别或清空搜索。</p>
                  </div>
                </div>
              ) : (
                <ul className="memory-list-body">
                  {filtered.map((entry) => {
                    const isActive = entry.id === activeId
                    return (
                      <li
                        key={entry.id}
                        className={isActive ? 'memory-entry is-active' : 'memory-entry'}
                        onClick={() => setActiveId(entry.id)}
                      >
                        <span className={`memory-entry-pill memory-entry-pill-${entry.category}`}>
                          {categoryLabel(entry.category)}
                        </span>
                        <div className="memory-entry-main">
                          <strong>{entry.content}</strong>
                          <small>来源：{entry.agent_id ?? '系统设置'} · {formatTimestamp(entry.created_at)}</small>
                        </div>
                        <span className={`memory-confidence ${importanceTone(entry.importance)}`}>
                          {entry.importance} / 10
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
            </article>

            <aside className="memory-detail" aria-label="条目详情">
              {!active ? (
                <div className="state-panel"><BrainCircuit /><h2>选择条目</h2><p>条目选中后，可在此查看来源与操作。</p></div>
              ) : (
                <>
                  <header className="memory-detail-header">
                    <div>
                      <h2>{categoryLabel(active.category)}</h2>
                      <p>{active.id} · {formatTimestamp(active.created_at)}</p>
                    </div>
                    <span className={`memory-confidence ${importanceTone(active.importance)}`}>
                      重要度 {active.importance} / 10
                    </span>
                  </header>

                  <section className="memory-detail-section">
                    <h3>内容</h3>
                    <p className="memory-detail-content">{active.content}</p>
                  </section>

                  <section className="memory-detail-section">
                    <h3>标签</h3>
                    {active.tags.length === 0 ? (
                      <p>未打标签。</p>
                    ) : (
                      <div className="memory-detail-tags">
                        {active.tags.map((tag) => <span key={tag} className="pill pill-neutral">{tag}</span>)}
                      </div>
                    )}
                  </section>

                  <section className="memory-detail-section">
                    <h3><Clock3 /> 元数据</h3>
                    <p>来源 agent：{active.agent_id ?? '未指定'}，创建时间 {formatTimestamp(active.created_at)}。</p>
                  </section>

                  <footer className="memory-detail-footer">
                    <button className="btn" type="button" onClick={() => onFlash(`已标记 ${active.id} 为已确认（占位）`)}>
                      <CheckCircle2 /> 标记为已确认
                    </button>
                    <button className="btn" type="button" onClick={() => void removeEntry(active.id)}>
                      <Trash /> 删除
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