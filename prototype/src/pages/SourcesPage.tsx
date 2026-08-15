import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { RadioTower, RefreshCw, Save } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { sourcesApi, type JsonRecord } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'
import type { SourceEntry } from '../types'

interface SourceRow {
  id: string
  enabled: boolean
  itemCount: number | null
  lastSync: string
  type: SourceEntry['type']
}

function formatConfig(config: Record<string, unknown>): string {
  return JSON.stringify(config, null, 2)
}

function safeId(label: string): string {
  return label || '数据源'
}

function mapSource(item: SourceEntry): SourceRow {
  return {
    id: item.id,
    enabled: item.enabled,
    itemCount: null,
    lastSync: '尚未同步',
    type: item.type,
  }
}

interface AvailableAdapter {
  id: string
  type?: string
  name?: string
  description?: string
  config_fields?: Array<Record<string, unknown>>
}

export function SourcesPage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const remote = useRemoteData<{ sources: JsonRecord[]; available_adapters: JsonRecord[] }>(
    () => sourcesApi.list(),
  )
  const sources = (remote.data?.sources ?? []) as unknown as SourceEntry[]
  const adapters = (remote.data?.available_adapters ?? []) as unknown as AvailableAdapter[]
  const hasData = Boolean(remote.data)
  const loading = remote.loading && !remote.data

  const [activeId, setActiveId] = useState<string>('')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [dirtyMap, setDirtyMap] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (!activeId && sources.length > 0) setActiveId(sources[0].id)
  }, [activeId, sources])

  useEffect(() => {
    const draftMap: Record<string, string> = {}
    for (const item of sources) draftMap[item.id] = formatConfig(item.config)
    setDrafts(draftMap)
    setDirtyMap({})
  }, [sources])

  const active = sources.find((item) => item.id === activeId) ?? null
  const draftValue = active ? (drafts[active.id] ?? formatConfig(active.config)) : ''
  const isDirty = active ? Boolean(dirtyMap[active.id]) : false

  const rows = useMemo<SourceRow[]>(() => sources.map(mapSource), [sources])

  const reload = async (): Promise<void> => {
    await remote.reload()
    onFlash('已刷新数据源。')
  }

  const updateDraft = (id: string, value: string): void => {
    setDrafts((current) => ({ ...current, [id]: value }))
    setDirtyMap((current) => ({ ...current, [id]: true }))
  }

  const saveSource = async (): Promise<void> => {
    if (!active) return
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(draftValue)
    } catch {
      onFlash('配置不是合法 JSON，请检查格式。')
      return
    }
    try {
      const payload = { id: active.id, type: active.type, enabled: active.enabled, config: parsed } as unknown as JsonRecord
      await sourcesApi.save(active.id, payload)
      setDirtyMap((current) => ({ ...current, [active.id]: false }))
      onFlash(`已保存「${safeId(active.id)}」的配置。`)
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '保存失败')
    }
  }

  const toggleSource = async (source: SourceEntry): Promise<void> => {
    try {
      await sourcesApi.save(source.id, { ...source, enabled: !source.enabled } as unknown as JsonRecord)
      onFlash(`数据源 ${source.id} 已${!source.enabled ? '启用' : '停用'}。`)
      await remote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '切换失败')
    }
  }

  const resetDraft = (): void => {
    if (!active) return
    setDrafts((current) => ({ ...current, [active.id]: formatConfig(active.config) }))
    setDirtyMap((current) => ({ ...current, [active.id]: false }))
    onFlash('已丢弃本地修改。')
  }

  return (
    <>
      <SectionHeading
        icon={<RadioTower />}
        title="数据源"
        description="管理服务端配置的数据采集器。PUT /api/sources/{id} 同步修改。"
        actions={
          <button className="btn" type="button" onClick={reload}>
            <RefreshCw /> 刷新
          </button>
        }
      />

      <DataStatus
        loading={loading}
        error={remote.error?.message ?? null}
        empty={!hasData && !loading}
        emptyTitle="暂无数据源"
        emptyDescription="添加第一个数据源后，采集任务会自动启用。"
        onRetry={() => void remote.reload()}
      >
        <section className="section">
          <div className="split-pane">
            <aside className="split-list" aria-label="数据源列表">
              <header className="split-list-header">
                <strong>所有数据源</strong>
                <span>{rows.length} 个</span>
              </header>
              <ul className="split-list-body">
                {rows.map((row) => {
                  const isActive = row.id === activeId
                  const isDirtyItem = Boolean(dirtyMap[row.id])
                  const source = sources.find((item) => item.id === row.id)
                  return (
                    <li key={row.id}>
                      <button
                        type="button"
                        className={isActive ? 'split-list-item is-active' : 'split-list-item'}
                        onClick={() => setActiveId(row.id)}
                      >
                        <span className="split-list-icon" aria-hidden="true"><RadioTower /></span>
                        <span className="split-list-copy">
                          <strong>{safeId(row.id)}</strong>
                          <small>{row.type} · {row.lastSync}</small>
                        </span>
                        <span className="split-list-meta">
                          {isDirtyItem && <span className="dot dot-warn" aria-label="未保存" />}
                          <button
                            type="button"
                            className={row.enabled ? 'pill pill-builtin' : 'pill pill-neutral'}
                            disabled={!source}
                            onClick={(event) => { event.stopPropagation(); source && void toggleSource(source) }}
                          >
                            {row.enabled ? '已启用' : '已停用'}
                          </button>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </aside>

            <article className="split-detail" aria-label="数据源详情">
              {!active ? (
                <div className="state-panel"><RadioTower /><h2>选择左侧数据源</h2><p>条目选中后，可在此查看和编辑采集参数。</p></div>
              ) : (
                <>
                  <header className="split-detail-header">
                    <div>
                      <h2>{safeId(active.id)}</h2>
                      <p>{active.type} · {active.id}</p>
                    </div>
                    <div className="split-detail-actions">
                      <span className={active.enabled ? 'pill pill-builtin' : 'pill pill-neutral'}>
                        {active.enabled ? '已启用' : '已停用'}
                      </span>
                    </div>
                  </header>

                  <div className="split-detail-body">
                    <label className="form-field form-field-full">
                      <span>采集参数（JSON）</span>
                      <textarea
                        className="code-area"
                        value={draftValue}
                        spellCheck={false}
                        onChange={(event) => updateDraft(active.id, event.target.value)}
                      />
                      <small>修改后点击「保存」生效；敏感字段会被服务端脱敏回填。</small>
                    </label>
                  </div>

                  <footer className="split-detail-footer">
                    <span className="form-status">
                      {isDirty ? <><span className="dot dot-warn" /> 有未保存的修改</> : '所有修改已保存'}
                    </span>
                    <div className="split-detail-actions">
                      <button className="btn" type="button" disabled={!isDirty} onClick={resetDraft}>放弃修改</button>
                      <button className="btn btn-primary" type="button" disabled={!isDirty} onClick={() => void saveSource()}>
                        <Save /> 保存
                      </button>
                    </div>
                  </footer>
                </>
              )}
            </article>
          </div>
        </section>

        {adapters.length > 0 && (
          <section className="section">
            <div className="settings-section">
              <header>
                <div>
                  <h2>已注册适配器</h2>
                  <p>来自 /api/sources.available_adapters；可作为新建数据源时的 type 选项。</p>
                </div>
              </header>
              <div className="data-table-card">
                <table className="data-table">
                  <thead>
                    <tr><th>标识</th><th>类型</th><th>说明</th></tr>
                  </thead>
                  <tbody>
                    {adapters.map((adapter) => (
                      <tr key={adapter.id}>
                        <td className="data-table-primary"><strong>{adapter.id}</strong><small>{adapter.id}</small></td>
                        <td><span className="pill pill-neutral">{adapter.type ?? '—'}</span></td>
                        <td>{adapter.description ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}
      </DataStatus>
    </>
  )
}