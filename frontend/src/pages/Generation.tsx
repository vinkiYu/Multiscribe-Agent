import { useState } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { DEFAULT_CURATION_AGENT_ID, runDigest } from '../services/digestService'
import type { DigestResult, DigestTargetResult } from '../services/digestService'
import { useToast } from '../context/ToastContext'

const TARGET_LABELS: Record<string, string> = {
  feishu_bot: '飞书机器人',
  wecom_bot: '企业微信机器人',
}

const STATUS_LABELS: Record<string, string> = {
  success: '发布成功',
  error: '发布失败',
  pending: '等待中',
}

function labelTarget(id: string): string {
  return TARGET_LABELS[id] ?? id
}
function labelStatus(s: string): string {
  return STATUS_LABELS[s] ?? s
}

function normalizeTargets(
  targets: DigestResult['targets'],
): DigestTargetResult[] {
  if (Array.isArray(targets)) return targets
  return Object.entries(targets ?? {}).map(([target_id, result]) => ({
    target_id,
    ...result,
  }))
}

export default function Generation() {
  const location = useLocation()
  const { showSuccess, showError } = useToast()
  const [markdown, setMarkdown] = useState('')
  const [editing, setEditing] = useState(false)
  const [published, setPublished] = useState(false)
  const [targets, setTargets] = useState<DigestTargetResult[]>([])
  const [publishing, setPublishing] = useState(false)

  const result = (location.state?.digestResult ?? null) as DigestResult | null
  const sourceUrl = typeof location.state?.rssUrl === 'string' ? location.state.rssUrl : undefined

  // Auto-populate from digest result on first render
  if (result?.curated?.length && !markdown) {
    const lines = result.curated
      .map((item, i) => {
        const title = item.title ?? '标题'
        const summary = item.summary ?? ''
        return `## ${i + 1}. ${title}\n\n${summary}`
      })
      .join('\n\n---\n\n')
    setMarkdown(lines)
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdown)
      showSuccess('摘要已复制')
    } catch {
      showError('无法自动复制，请手动选择文本')
    }
  }

  // Publish action is explicit and channel-specific. Confirms scope before sending.
  const handlePublish = async () => {
    if (publishing) return
    const ok = window.confirm(
      '确认重新生成摘要并发送到已设置的渠道？这会发出一份新的摘要。',
    )
    if (!ok) return
    setPublishing(true)
    try {
      const publishResult = await runDigest({
        // The backend re-runs the pipeline and pushes to the requested targets.
        curate_agent_id: DEFAULT_CURATION_AGENT_ID,
        targets: ['feishu_bot'],
        top_n: result?.curated?.length ?? 5,
        ...(sourceUrl
          ? { adapter_ids: ['rss'], adapter_configs: { rss: { rss_url: sourceUrl } } }
          : {}),
      })
      setTargets(normalizeTargets(publishResult.targets))
      setPublished(true)
      showSuccess('已重新生成并发送，请查看下方结果')
    } catch (err) {
      showError('发布失败：' + friendlyError(err))
    } finally {
      setPublishing(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{published ? '本次发送结果' : '摘要与发布'}</h1>
          <p>
            {published
              ? '这里显示本次生成的摘要，以及发送到各渠道的结果。'
              : '这里显示刚生成的摘要。编辑只影响当前页面和复制内容；点击发送会按当前设置重新生成摘要，并发送到已配置的渠道。'}
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={handleCopy} disabled={!markdown} type="button">
            复制摘要
          </button>
          <button
            className="btn"
            onClick={() => setEditing(e => !e)}
            disabled={!markdown}
            type="button"
          >
            {editing ? '完成编辑' : '修改当前摘要'}
          </button>
          {published ? (
            <Link className="btn" to="/history">
              查看运行记录
            </Link>
          ) : (
            <button
              className="btn primary"
              onClick={handlePublish}
              disabled={!markdown || publishing}
              type="button"
            >
              {publishing ? <span className="spinner" /> : '重新生成并发送'}
            </button>
          )}
        </div>
      </div>

      {/* Publish result panel */}
      {targets.length > 0 && (
        <div className="toolbar" style={{ marginBottom: 16 }}>
          <span className="text-muted text-sm">发送结果：</span>
          {targets.map(t => (
            <span
              key={t.target_id}
              className={'badge ' + (t.status === 'success' ? 'live' : '')}
            >
              {labelTarget(t.target_id)}：{labelStatus(t.status)}
              {t.items_count ? `（共 ${t.items_count} 条）` : ''}
              {t.message ? ` — ${t.message}` : ''}
            </span>
          ))}
        </div>
      )}

      {markdown ? (
        editing ? (
          <textarea
            className="input"
            style={{
              minHeight: 480,
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              resize: 'vertical',
            }}
            value={markdown}
            onChange={e => setMarkdown(e.target.value)}
          />
        ) : (
          <article className="card">
            <div className="card-body" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
              {markdown.split('\n\n---\n\n').map((block, i) => {
                const lines = block.split('\n')
                return (
                  <div
                    key={i}
                    style={{
                      padding: '16px 0',
                      borderBottom:
                        i < (result?.curated?.length ?? 1) - 1
                          ? '1px solid var(--color-border)'
                          : 'none',
                    }}
                  >
                    {lines.map((line, j) => {
                      if (line.startsWith('## ')) {
                        return (
                          <h2
                            key={j}
                            style={{ fontSize: 18, margin: '0 0 8px', fontWeight: 800 }}
                          >
                            {line.replace('## ', '')}
                          </h2>
                        )
                      }
                      return (
                        <p key={j} style={{ margin: 0, color: 'var(--color-muted)' }}>
                          {line}
                        </p>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          </article>
        )
      ) : (
        <div className="empty">
          <strong>暂无摘要</strong>
          <p>请先在「内容来源」抓取内容并生成摘要。</p>
          <Link
            className="btn"
            to="/selection"
            style={{ marginTop: 16, display: 'inline-flex' }}
          >
            前往内容来源
          </Link>
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
