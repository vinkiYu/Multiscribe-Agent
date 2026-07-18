import { useState, type KeyboardEvent } from 'react'
import { Download, Plus, RotateCcw, Save, Upload, X } from 'lucide-react'
import { memoryService, type MemoryPreferences } from '../services/memory'

export default function Memory() {
  const [preferences, setPreferences] = useState<MemoryPreferences>(() =>
    memoryService.getPreferences(),
  )
  const [tagInput, setTagInput] = useState('')
  const [importValue, setImportValue] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  const save = () => {
    memoryService.savePreferences(preferences)
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

  const importPreferences = () => {
    try {
      memoryService.importPreferences(importValue)
      setPreferences(memoryService.getPreferences())
      setImportValue('')
      setNotice('偏好导入成功')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '导入失败，请检查 JSON 格式')
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>记忆与偏好</h1>
          <p>设置内容偏好。数据仅保存在当前浏览器，后端记忆服务将在 P17 接入。</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={exportPreferences} type="button">
            <Download size={16} aria-hidden="true" />导出 JSON
          </button>
          <button className="btn" onClick={reset} type="button">
            <RotateCcw size={16} aria-hidden="true" />重置
          </button>
          <button className="btn primary" onClick={save} type="button">
            <Save size={16} aria-hidden="true" />保存偏好
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
          <div className="card-head"><span>导入偏好</span></div>
          <div className="card-body">
            <p className="text-muted text-sm">粘贴先前导出的 JSON，导入将覆盖当前浏览器中的偏好。</p>
            <textarea
              aria-label="导入偏好 JSON"
              value={importValue}
              placeholder='{"preferred_tags": [], "blocked_sources": [], "push_time": "09:00", "max_items_per_digest": 5}'
              onChange={event => setImportValue(event.target.value)}
            />
            <button className="btn" onClick={importPreferences} disabled={!importValue.trim()} type="button">
              <Upload size={16} aria-hidden="true" />导入 JSON
            </button>
          </div>
        </article>
      </section>

      <section style={{ marginTop: 16 }}>
        <article className="card">
          <div className="card-head"><span>记忆历史</span><span className="badge">等待 P17</span></div>
          <div className="empty" style={{ minHeight: 160 }}>
            <strong>后端记忆 API 尚未上线</strong>
            <p>保存的本地偏好仍会在刷新页面后恢复。Agent 记忆历史将在 P17 后显示。</p>
          </div>
        </article>
      </section>
    </>
  )
}
