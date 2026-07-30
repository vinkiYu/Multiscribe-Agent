import { useEffect, useState, type ReactElement } from 'react'
import { ExternalLink, LoaderCircle, X } from 'lucide-react'
import { dailyNewsApi, type DailyDigest } from '../services/api'
import { ApiError } from '../services/api'
import { Modal } from './dialog'

interface CurationDrawerProps {
  date: string | null
  open: boolean
  onClose: () => void
}

export function CurationDrawer({ date, open, onClose }: CurationDrawerProps): ReactElement {
  const [digest, setDigest] = useState<DailyDigest | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || !date) return
    setLoading(true)
    setError('')
    setDigest(null)
    void dailyNewsApi.byDate(date)
      .then((response) => setDigest(response.digest))
      .catch((caught: unknown) => setError(caught instanceof ApiError ? caught.message : '无法加载当日资讯'))
      .finally(() => setLoading(false))
  }, [date, open])

  return (
    <Modal.Root open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose() }}>
      <Modal.Overlay className="curation-drawer-overlay" />
      <Modal.Content className="curation-drawer-content">
        <header className="curation-drawer-header">
          <div><Modal.Title>策展明细 · {date ?? '未选择日期'}</Modal.Title><p>{digest?.title ?? '查看当日精选资讯、来源和评分'}</p></div>
          <Modal.Close asChild><button className="icon-button" aria-label="关闭明细"><X /></button></Modal.Close>
        </header>
        {loading && <div className="curation-drawer-state"><LoaderCircle className="spinning" /><span>加载当日资讯...</span></div>}
        {!loading && error && <div className="curation-drawer-state is-error"><strong>{error}</strong></div>}
        {!loading && !error && !digest && <div className="curation-drawer-state"><span>该日期没有可展示的公开归档。</span></div>}
        {!loading && !error && digest && <div className="curation-drawer-body">
          <div className="curation-drawer-summary"><span>摘要</span><p>{digest.summary || '暂无摘要'}</p><small>扫描 {digest.total_scanned} 条 · 精选 {digest.items.length} 条</small></div>
          <div className="curation-item-list">
            {digest.items.map((item) => <article className="curation-item" key={item.url}>
              <div className="curation-item-heading"><a href={item.url} target="_blank" rel="noreferrer">{item.title}<ExternalLink /></a>{item.score !== null && <strong>{item.score.toFixed(1)}</strong>}</div>
              <p>{item.summary || '暂无摘要'}</p>
              <footer><span>{item.source}</span><span>{item.section}</span>{item.tags.length > 0 && <span>{item.tags.slice(0, 3).join(' · ')}</span>}</footer>
            </article>)}
          </div>
        </div>}
      </Modal.Content>
    </Modal.Root>
  )
}
