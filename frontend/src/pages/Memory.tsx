import { useEffect, useState, type KeyboardEvent } from 'react'
import { Download, Plus, RotateCcw, Save, Upload, X } from 'lucide-react'
import {
  memoryService,
  type MemoryPreferences,
  type MemoryEntry,
} from '../services/memory'

export default function Memory() {
  const [preferences, setPreferences] = useState<MemoryPreferences>(() =>
    memoryService.getPreferences(),
  )
  const [tagInput, setTagInput] = useState('')
  const [importValue, setImportValue] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [history, setHistory] = useState<MemoryEntry[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)

  // Load history and check backend availability on mount
  useEffect(() => {
    const checkBackend = async () => {
      const online = await memoryService.isBackendAvailable()
      setBackendOnline(online)
      if (online) {
        const entries = await memoryService.getHistory(30)
        setHistory(entries)
      }
      setHistoryLoading(false)
    }
    void checkBackend()
  }, [])

  const handleSave = async () => {
    memoryService.savePreferences(preferences)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)

    if (backendOnline) {
      const synced = await memoryService.syncPreferencesToBackend(preferences)
      setNotice(
        synced
          ? '偏好已保存到浏览器，并已同步至后端'
          : '偏好已保存到浏览器，但后端同步失败，当前仍可正常使用本地配置',
      )
      return
    }
    setNotice('偏好已保存到此浏览器')
  }

  const reset = () => {
    memoryService.resetPreferences()
    setPreferences(memoryService.getPreferences())
    setNotice('偏好已重置为默认值')
  }

  const addTag = () => {
    const tag = tagInput.trim()
    if (!tag || preferences.preferred_tags.includes(tag)) return
    setPreferences(current => ({ ...current, preferred_tags: [...current.preferred_tags, tag] }))
    setTagInput('')
  }

  const onTagKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return
    event.preventDefault()
    addTag()
  }

  const removeTag = (tag: string) => {
    setPreferences(current => ({
      ...current,
      preferred_tags: current.preferred_tags.filter(item => item !== tag),
    }))
  }

  const exportPreferences = () => {
    const blob = new Blob([memoryService.exportPreferences()], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'multiscribe-memory-preferences.json'
    link.click()
    URL.revokeObjectURL(url)
  }

  const importPreferences = async () => {
    try {
      memoryService.importPreferences(importValue)
      const imported = memoryService.getPreferences()
      setPreferences(imported)
      setImportValue('')
      if (backendOnline) {
        const synced = await memoryService.syncPreferencesToBackend(imported)
        setNotice(
          synced
            ? '偏好导入成功，并已同步至后端'
            : '偏好导入成功，但后端同步失败，当前仍保留本地配置',
        )
      } else {
        setNotice('偏好导入成功，已保存在此浏览器')
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '导入失败，请检查 JSON 格式')
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>内容偏好</h1>
          <p>设置希望优先关注的主题和每份摘要的条数。设置会保存在当前浏览器{backendOnline ? '，并同步到系统' : ''}。</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={exportPreferences} type="button">
            <Download size={16} aria-hidden="true" />导出 JSON
          </button>
          <button className="btn" onClick={reset} type="button">
            <RotateCcw size={16} aria-hidden="true" />重置
          </button>
          <button className="btn primary" onClick={handleSave} type="button">
            <Save size={16} aria-hidden="true" />
            {saved ? '已保存' : '保存偏好'}
          </button>
        </div>
      </div>

      {notice && (
        <div className="toolbar" role="status">
          <span>{notice}</span>
          <button
            className="btn icon-btn"
            onClick={() => setNotice(null)}
            type="button"
            aria-label="关闭提示"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      )}

      <section className="grid cols-2">
        <article className="card">
          <div className="card-head"><span>内容偏好</span></div>
          <div className="card-body">
            <div className="field">
              <label htmlFor="push-time">每日推送时间</label>
              <input
                id="push-time"
                className="input"
                type="time"
                value={preferences.push_time}
                onChange={event =>
                  setPreferences(current => ({ ...current, push_time: event.target.value }))
                }
              />
            </div>
            <div className="field" style={{ marginTop: 16 }}>
              <label htmlFor="max-items">每次精选条数</label>
              <input
                id="max-items"
                className="input"
                type="number"
                min="1"
                max="20"
                value={preferences.max_items_per_digest}
                onChange={event =>
                  setPreferences(current => ({
                    ...current,
                    max_items_per_digest: Number(event.target.value) || 1,
                  }))
                }
              />
            </div>
            <div className="field" style={{ marginTop: 16 }}>
              <label htmlFor="preference-tag">偏好标签</label>
              <div className="actions">
                <input
                  id="preference-tag"
                  className="input"
                  value={tagInput}
                  placeholder="例如：AI、大模型、技术周报"
                  onChange={event => setTagInput(event.target.value)}
                  onKeyDown={onTagKeyDown}
                />
                <button className="btn" onClick={addTag} type="button">
                  <Plus size={16} aria-hidden="true" />添加标签
                </button>
              </div>
              <div className="actions" aria-label="已选偏好标签">
                {preferences.preferred_tags.length === 0 ? (
                  <span className="text-muted text-sm">尚未添加标签</span>
                ) : (
                  preferences.preferred_tags.map(tag => (
                    <button className="badge" key={tag} onClick={() => removeTag(tag)} type="button">
                      {tag}<X size={13} aria-hidden="true" />
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        </article>

        <article className="card">
          <div className="card-head"><span>导入设置</span></div>
          <div className="card-body">
            <p className="text-muted text-sm">粘贴之前导出的设置内容（JSON 格式）。导入后会替换当前浏览器中的设置。</p>
            <textarea
              aria-label="导入设置内容"
              value={importValue}
              placeholder='{"preferred_tags": [], "blocked_sources": [], "push_time": "09:00", "max_items_per_digest": 5}'
              onChange={event => setImportValue(event.target.value)}
              rows={4}
              style={{ fontFamily: 'monospace', fontSize: '0.85rem', resize: 'vertical' }}
            />
            <button
              className="btn"
              onClick={() => void importPreferences()}
              disabled={!importValue.trim()}
              type="button"
            >
              <Upload size={16} aria-hidden="true" />导入设置
            </button>
          </div>
        </article>
      </section>

      <section style={{ marginTop: 16 }}>
        <article className="card">
          <div className="card-head">
            <span>偏好记录</span>
            {backendOnline === true && (
              <span className="badge">{history.length} 条</span>
            )}
            {backendOnline === false && (
              <span className="badge">本机保存</span>
            )}
            {backendOnline === null && (
              <span className="badge">检查中</span>
            )}
          </div>
          {historyLoading ? (
            <div className="empty" style={{ minHeight: 160 }}>
              <strong>正在加载偏好记录…</strong>
            </div>
          ) : backendOnline === false ? (
            <div className="empty" style={{ minHeight: 160 }}>
              <strong>偏好记录暂不可用</strong>
              <p>你已保存的内容偏好会在刷新后保留。更多自动记录会在功能启用后显示。</p>
            </div>
          ) : history.length === 0 ? (
            <div className="empty" style={{ minHeight: 160 }}>
              <strong>尚无偏好记录</strong>
              <p>AI 在运行时产生的关键偏好和选择会显示在这里。</p>
            </div>
          ) : (
            <div className="card-body" style={{ padding: 0 }}>
              {history.slice(0, 20).map(entry => (
                <div
                  key={entry.id}
                  style={{
                    padding: '12px 16px',
                    borderBottom: '1px solid var(--color-border)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 4,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="badge">{entry.category}</span>
                    {entry.tags.map(tag => (
                      <span key={tag} className="badge" style={{ opacity: 0.7 }}>{tag}</span>
                    ))}
                    <span className="text-sm text-muted" style={{ marginLeft: 'auto' }}>
                      {new Date(entry.created_at).toLocaleDateString('zh-CN')}
                    </span>
                  </div>
                  <p className="text-sm" style={{ margin: 0 }}>
                    {entry.content.length > 200 ? entry.content.slice(0, 200) + '…' : entry.content}
                  </p>
                </div>
              ))}
            </div>
          )}
        </article>
      </section>
    </>
  )
}
