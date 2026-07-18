import { useRef, useState } from 'react'
import { FileSearch, RefreshCw, Search, Trash2, X } from 'lucide-react'
import {
  ApiUnavailableError,
  knowledgeService,
  type KBDocument,
  type KBSearchResult,
} from '../services/knowledge'

type Notice = { message: string; tone: 'info' | 'error' } | null

export default function KnowledgeBase() {
  const [documents, setDocuments] = useState<KBDocument[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<KBSearchResult[]>([])
  const [category, setCategory] = useState('general')
  const [searching, setSearching] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [notice, setNotice] = useState<Notice>(
    { message: '知识库后端 API 尚未上线，等待 P16 完成。页面与本地操作流程已就绪。', tone: 'info' },
  )
  const fileInput = useRef<HTMLInputElement>(null)

  const showError = (error: unknown, fallback: string) => {
    if (error instanceof ApiUnavailableError) {
      setNotice({ message: error.message, tone: 'info' })
      return
    }
    const message = error instanceof Error ? error.message : fallback
    setNotice({ message, tone: 'error' })
  }

  const refreshDocuments = async () => {
    try {
      const nextDocuments = await knowledgeService.listDocuments()
      setDocuments(nextDocuments)
      setNotice(null)
    } catch (error) {
      showError(error, '无法加载文档列表')
    }
  }

  const uploadDocument = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const created = await knowledgeService.uploadDocument(file, category)
      setDocuments(current => [created, ...current])
      setNotice({ message: `文档“${created.title}”已上传`, tone: 'info' })
    } catch (error) {
      showError(error, '文档上传失败')
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const searchDocuments = async () => {
    if (!query.trim()) return
    setSearching(true)
    try {
      const response = await knowledgeService.search(query.trim())
      setResults(response.results)
      setNotice(response.results.length ? null : { message: '没有匹配的知识库内容', tone: 'info' })
    } catch (error) {
      setResults([])
      showError(error, '知识库搜索失败')
    } finally {
      setSearching(false)
    }
  }

  const deleteDocument = async (id: string) => {
    try {
      await knowledgeService.deleteDocument(id)
      setDocuments(current => current.filter(document => document.id !== id))
    } catch (error) {
      showError(error, '文档删除失败')
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>知识库</h1>
          <p>上传文档供 Agent 检索。后端知识库能力将在 P16 接入。</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={refreshDocuments} type="button">
            <RefreshCw size={16} aria-hidden="true" />刷新列表
          </button>
        </div>
      </div>

      {notice && (
        <div className="toolbar" role={notice.tone === 'error' ? 'alert' : 'status'}>
          <span>{notice.message}</span>
          <button className="btn icon-btn" onClick={() => setNotice(null)} type="button" aria-label="关闭提示">
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      )}

      <section className="grid cols-2">
        <article className="card">
          <div className="card-head"><span>上传文档</span><span className="badge">等待 P16</span></div>
          <div className="card-body">
            <div className="field">
              <label htmlFor="kb-category">分类</label>
              <select id="kb-category" value={category} onChange={event => setCategory(event.target.value)}>
                <option value="general">通用</option>
                <option value="tech">技术</option>
                <option value="news">新闻</option>
              </select>
            </div>
            <div className="field" style={{ marginTop: 16 }}>
              <label htmlFor="kb-file">选择文件</label>
              <input
                id="kb-file"
                ref={fileInput}
                type="file"
                accept=".pdf,.docx,.md,.txt,.csv"
                onChange={uploadDocument}
                disabled={uploading}
              />
              <span className="text-muted text-sm">支持 PDF、DOCX、Markdown、TXT 和 CSV。</span>
            </div>
            {uploading && <span className="text-muted text-sm">正在提交文档…</span>}
          </div>
        </article>

        <article className="card">
          <div className="card-head"><span>搜索内容</span></div>
          <div className="card-body">
            <div className="actions">
              <input
                className="input"
                value={query}
                placeholder="输入关键词搜索知识库"
                onChange={event => setQuery(event.target.value)}
                onKeyDown={event => { if (event.key === 'Enter') void searchDocuments() }}
              />
              <button className="btn primary" onClick={() => void searchDocuments()} disabled={searching} type="button">
                <Search size={16} aria-hidden="true" />{searching ? '搜索中' : '搜索'}
              </button>
            </div>
            {results.length > 0 && (
              <div className="list" style={{ marginTop: 16 }}>
                {results.map(result => (
                  <div className="list-item" key={`${result.document_id}-${result.chunk}`}>
                    <div className="list-copy">
                      <strong>{result.title}</strong>
                      <span>{result.chunk}</span>
                    </div>
                    <span className="badge">{Math.round(result.score * 100)}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </article>
      </section>

      <section style={{ marginTop: 16 }}>
        <article className="card">
          <div className="card-head"><span>已上传文档</span><span className="badge">{documents.length} 条</span></div>
          {documents.length === 0 ? (
            <div className="empty">
              <FileSearch size={28} aria-hidden="true" />
              <strong>尚无可展示的文档</strong>
              <p>知识库后端 API 尚未上线。P16 合并后，上传的文档会显示在这里。</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>标题</th><th>分类</th><th>分块</th><th>创建时间</th><th>操作</th></tr></thead>
                <tbody>
                  {documents.map(document => (
                    <tr key={document.id}>
                      <td>{document.title}</td><td>{document.category}</td><td>{document.chunk_count}</td>
                      <td>{new Date(document.created_at).toLocaleDateString('zh-CN')}</td>
                      <td><button className="btn icon-btn" onClick={() => void deleteDocument(document.id)} type="button" aria-label={`删除 ${document.title}`}><Trash2 size={16} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      </section>
    </>
  )
}
