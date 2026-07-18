import { useState } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { runDigest } from '../services/digestService'
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

export default function Generation() {
  const location = useLocation()
  const { showSuccess, showError } = useToast()
  const [markdown, setMarkdown] = useState('')
  const [editing, setEditing] = useState(false)
  const [published, setPublished] = useState(false)
  const [targets, setTargets] = useState<DigestTargetResult[]>([])
  const [publishing, setPublishing] = useState(false)

  const result = (location.state?.digestResult ?? null) as DigestResult | null

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
      '确认将本次摘要发布到飞书机器人？该操作会将内容发送到对应群组。',
    )
    if (!ok) return
    setPublishing(true)
    try {
      const publishResult = await runDigest({
        // The backend re-runs the pipeline and pushes to the requested targets.
        targets: ['feishu_bot'],
        top_n: result?.curated?.length ?? 5,
      })
      setTargets(publishResult.targets ?? [])
      setPublished(true)
      showSuccess('已尝试发布，请查看下方结果')
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
          <h1>{published ? '本次运行结果' : '摘要预览'}</h1>
          <p>
            {published
              ? '以下是本次生成的摘要及各发布渠道的结果。'
              : '查看 AI 生成的摘要，可编辑后再决定是否发布。生成本身不会向任何渠道发送内容。'}
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
            {editing ? '完成编辑' : '编辑摘要'}
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
              {publishing ? <span className="spinner" /> : '发布到飞书机器人'}
            </button>
          )}
        </div>
      </div>

      {/* Publish result panel */}
      {targets.length > 0 && (
        <div className="toolbar" style={{ marginBottom: 16 }}>
          <span className="text-muted text-sm">发布结果：</span>
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
          <p>请先在「采集与筛选」页面抓取内容并生成摘要预览。</p>
          <Link
            className="btn"
            to="/selection"
            style={{ marginTop: 16, display: 'inline-flex' }}
          >
            去采集与筛选
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
