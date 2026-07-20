import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { triggerIngestion, getRecentLogs } from '../services/dashboardService'
import { DEFAULT_CURATION_AGENT_ID, runDigest } from '../services/digestService'
import { memoryService } from '../services/memory'
import { useToast } from '../context/ToastContext'
import type { DigestResult } from '../services/digestService'

const SAMPLE_RSS = 'http://feeds.bbci.co.uk/news/rss.xml'

function isLikelyUrl(s: string): boolean {
  try {
    const u = new URL(s.trim())
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

export default function Selection() {
  const navigate = useNavigate()
  const { showSuccess, showError, showInfo } = useToast()
  const [rssUrl, setRssUrl] = useState(SAMPLE_RSS)
  const [fetching, setFetching] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [lastFetchCount, setLastFetchCount] = useState<number | null>(null)
  const [lastFetchAt, setLastFetchAt] = useState<string | null>(null)
  const [digestResult, setDigestResult] = useState<DigestResult | null>(null)

  // Manual-only fetch: triggered by button click or Enter key, never on input change.
  const handleFetch = async () => {
    const url = rssUrl.trim()
    if (!url) {
      showError('请先填写内容来源地址')
      return
    }
    if (!isLikelyUrl(url)) {
      showError('地址格式不正确，请填写以 http:// 或 https:// 开头的完整 URL')
      return
    }
    setFetching(true)
    setLastFetchCount(null)
    try {
      const result = await triggerIngestion({
        adapter_id: 'rss',
        config: { rss_url: url },
      })
      const count = result.result_count ?? result.results?.length ?? 0
      setLastFetchCount(count)
      setLastFetchAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
      if (count > 0) {
        showSuccess(`已抓取 ${count} 条内容，已准备好生成摘要`)
      } else {
        showInfo('抓取完成，该来源暂时没有新内容')
      }
    } catch (err) {
      showError('抓取失败：' + friendlyError(err))
    } finally {
      setFetching(false)
    }
  }

  // Generate a digest PREVIEW only. Do NOT publish to any channel here.
  const handleGeneratePreview = async () => {
    setGenerating(true)
    try {
      const maxItems = memoryService.getPreferences().max_items_per_digest
      const result = await runDigest({
        curate_agent_id: DEFAULT_CURATION_AGENT_ID,
        top_n: maxItems,
        // An explicit empty target list means preview only; the backend must not apply defaults.
        targets: [],
        adapter_ids: ['rss'],
        adapter_configs: { rss: { rss_url: rssUrl } },
      })
      setDigestResult(result)
      showSuccess('摘要已生成，进入预览页面后可确认是否发布')
      navigate('/generation', { state: { digestResult: result, rssUrl: rssUrl } })
    } catch (err) {
      showError('生成失败：' + friendlyError(err))
    } finally {
      setGenerating(false)
    }
  }

  // Back-compat: keep page aware of recent activity even without a list endpoint.
  const [recentCount, setRecentCount] = useState<number | null>(null)
  const handleCheckRecent = async () => {
    try {
      const logs = await getRecentLogs(20)
      setRecentCount(
        logs.filter(l => l.task_name?.includes('digest')).length,
      )
      showInfo(`最近 20 条运行记录中有 ${logs.length} 条任务`)
    } catch (err) {
      showError('查询失败：' + friendlyError(err))
    }
  }

  const fetchedNothing =
    lastFetchCount !== null && lastFetchCount === 0

  return (
    <>
      <div className="page-head">
        <div>
          <h1>内容来源</h1>
          <p>
            添加 RSS 地址并抓取内容，再生成一份摘要供你确认。生成摘要不会发送到任何渠道。
          </p>
        </div>
        <div className="actions">
          <button
            className="btn"
            onClick={handleCheckRecent}
            type="button"
          >
            查看最近运行
          </button>
        </div>
      </div>

      {/* Step 1: Source */}
      <section className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <span>第 1 步 · 选择内容来源</span>
          {lastFetchAt && (
            <span className="text-muted text-xs">上次抓取 {lastFetchAt}</span>
          )}
        </div>
        <div className="card-body">
          <div className="field">
            <label>RSS 地址</label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <input
                className="input"
                style={{ flex: 1, minWidth: 280 }}
                placeholder="例如：http://feeds.bbci.co.uk/news/rss.xml"
                value={rssUrl}
                onChange={e => setRssUrl(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleFetch()
                  }
                }}
              />
              <button
                className="btn primary"
                onClick={handleFetch}
                disabled={fetching}
                type="button"
              >
                {fetching ? <span className="spinner" /> : '抓取最新内容'}
              </button>
            </div>
            <span className="text-muted text-xs">
              示例地址已预填（BBC News）。你可以替换为自己的 RSS 地址，仅在点击按钮或按回车时抓取。
            </span>
          </div>

          {lastFetchCount !== null && (
            <div
              className="text-sm"
              style={{
                marginTop: 12,
                padding: 12,
                borderRadius: 6,
                background: 'var(--color-subtle)',
              }}
            >
              {lastFetchCount > 0 ? (
                <>
                  ✅ 已抓取 <strong>{lastFetchCount}</strong> 条内容，已准备好生成摘要。
                </>
              ) : (
                <>该来源暂时没有新内容。你可以尝试更换地址或稍后再试。</>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Step 2: Generate preview */}
      <section className="card">
        <div className="card-head">
          <span>第 2 步 · 生成摘要</span>
        </div>
        <div className="card-body">
          <p className="text-muted text-sm" style={{ marginTop: 0 }}>
            这一步只会生成摘要，不会发送内容。请在下一页检查摘要后再发送。
          </p>
          <button
            className="btn primary"
            onClick={handleGeneratePreview}
            disabled={generating}
            type="button"
          >
            {generating ? <span className="spinner" /> : '使用最新内容生成摘要'}
          </button>

          {recentCount !== null && (
            <p className="text-muted text-xs" style={{ marginTop: 12 }}>
              最近 20 次任务中包含 {recentCount} 条摘要类任务。
            </p>
          )}

          {digestResult && (
            <p className="text-sm" style={{ marginTop: 12, color: 'var(--color-accent)' }}>
              摘要已生成，可在「摘要与发布」页面查看。
            </p>
          )}
        </div>
      </section>

      {fetchedNothing && (
        <div className="empty" style={{ marginTop: 16 }}>
          <strong>抓取完成，但没有新内容</strong>
          <p>该 RSS 来源当前没有可处理的新条目。可稍后再试或更换来源地址。</p>
        </div>
      )}
    </>
  )
}

function friendlyError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err)
  if (/Failed to fetch|NetworkError|connect|ECONN/i.test(msg)) {
    return '无法连接服务，请确认 Multiscribe 已启动'
  }
  if (/401|unauthorized/i.test(msg)) {
    return '登录已过期，请重新登录'
  }
  return msg
}
