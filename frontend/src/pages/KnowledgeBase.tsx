import { useCallback, useEffect, useRef, useState } from 'react'
import { BookOpen, FileSearch, Plus, RefreshCw, Search, Trash2, X } from 'lucide-react'
import {
  knowledgeService,
  type KBDocument,
  type KBCategory,
  type KBSearchResult,
} from '../services/knowledge'

type Status = { message: string; tone: 'info' | 'error' | 'success' } | null

type Tab = 'upload' | 'search'

const SUPPORTED_TEXT_EXTENSIONS = new Set(['.txt', '.md', '.csv'])

export default function KnowledgeBase() {
  const [documents, setDocuments] = useState<KBDocument[]>([])
  const [categories, setCategories] = useState<KBCategory[]>([])
  const [tab, setTab] = useState<Tab>('search')
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(10)
  const [results, setResults] = useState<KBSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState<Status>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  // Upload form state
  const [uploadName, setUploadName] = useState('')
  const [uploadCategory, setUploadCategory] = useState('general')
  const [uploadText, setUploadText] = useState('')
  const [uploading, setUploading] = useState(false)

  // Load documents + categories on mount
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void refreshAll() }, [])

  const refreshAll = useCallback(async () => {
    setLoading(true)
    try {
      const [docs, cats] = await Promise.allSettled([
        knowledgeService.listDocuments(),
        knowledgeService.listCategories(),
      ])
      if (docs.status === 'fulfilled') setDocuments(docs.value)
      if (cats.status === 'fulfilled') setCategories(cats.value)
      setNotice(null)
    } catch {
      setNotice({ message: '无法加载知识库数据', tone: 'error' })
    } finally {
      setLoading(false)
    }
  }, [])

  const handleUpload = async () => {
    if (!uploadName.trim()) {
      setNotice({ message: '请填写文档名称', tone: 'error' })
      return
    }
    if (!uploadText.trim()) {
      setNotice({ message: '请输入文档内容', tone: 'error' })
      return
    }
    setUploading(true)
    try {
      const created = await knowledgeService.ingestText({
        text: uploadText.trim(),
        categoryId: uploadCategory,
        name: uploadName.trim(),
      })
      setDocuments(current => [created, ...current])
      setUploadName('')
      setUploadText('')
      setNotice({
        message: `文档「${created.name}」已添加，共 ${created.chunk_count} 个分块`,
        tone: 'success',
      })
      setTab('search')
    } catch (error) {
      if (error instanceof Error) {
        setNotice({ message: `上传失败：${error.message}`, tone: 'error' })
      } else {
        setNotice({ message: '文档上传失败', tone: 'error' })
      }
    } finally {
      setUploading(false)
    }
  }

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (!SUPPORTED_TEXT_EXTENSIONS.has(extension)) {
      setNotice({ message: '浏览器导入目前仅支持 .txt、.md 和 .csv 文本文件', tone: 'error' })
      if (fileInput.current) fileInput.current.value = ''
      return
    }
    const text = await file.text().catch(() => null)
    if (text === null) {
      setNotice({ message: '无法读取该文件，请检查文件权限或改用文本粘贴', tone: 'error' })
      if (fileInput.current) fileInput.current.value = ''
      return
    }
    const name = file.name.replace(/\.[^.]+$/, '')
    setUploadName(name)
    setUploadText(text)
    if (fileInput.current) fileInput.current.value = ''
    setNotice({ message: `已加载「${file.name}」内容，请检查后点击添加`, tone: 'info' })
  }

  const handleSearch = async () => {
    if (!query.trim()) return
    setLoading(true)
    try {
      const response = await knowledgeService.search(query.trim(), topK)
      const normalized = response.hits.map(h => knowledgeService.normalizeHit(h))
      setResults(normalized)
      setNotice(
        normalized.length
          ? null
          : { message: '没有匹配的知识库内容，试试其他关键词', tone: 'info' },
      )
    } catch (error) {
      setResults([])
      if (error instanceof Error) {
        setNotice({ message: `搜索失败：${error.message}`, tone: 'error' })
      } else {
        setNotice({ message: '知识库搜索失败', tone: 'error' })
      }
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await knowledgeService.deleteDocument(id)
      setDocuments(current => current.filter(d => d.id !== id))
      setNotice({ message: '文档已删除', tone: 'info' })
    } catch (error) {
      if (error instanceof Error) {
        setNotice({ message: `删除失败：${error.message}`, tone: 'error' })
      } else {
        setNotice({ message: '文档删除失败', tone: 'error' })
      }
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>知识库</h1>
          <p>上传文档供 Agent 检索，支持文本粘贴和 .txt、.md、.csv 文件导入。</p>
        </div>
        <div className="actions">
          <button className="btn" onClick={refreshAll} disabled={loading} type="button">
            <RefreshCw size={16} aria-hidden="true" className={loading ? 'spin' : ''} />
            刷新列表
          </button>
        </div>
      </div>

      {notice && (
        <div
          className={`toolbar ${notice.tone === 'error' ? 'error' : notice.tone === 'success' ? 'success' : ''}`}
          role={notice.tone === 'error' ? 'alert' : 'status'}
        >
          <span>{notice.message}</span>
          <button className="btn icon-btn" onClick={() => setNotice(null)} type="button" aria-label="关闭提示">
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      )}

      {/* Tab switcher */}
      <div className="tabs" style={{ marginBottom: 16 }}>
        {([['search', '搜索'], ['upload', '添加文档']] as const).map(([value, label]) => (
          <button
            className={`tab ${tab === value ? 'active' : ''}`}
            key={value}
            onClick={() => setTab(value)}
            type="button"
          >
            {value === 'search' ? (
              <Search size={14} aria-hidden="true" />
            ) : (
              <Plus size={14} aria-hidden="true" />
            )}
            {label}
          </button>
        ))}
      </div>

      {tab === 'upload' && (
        <section className="grid cols-2">
          <article className="card">
            <div className="card-head">
              <span>添加文档</span>
              <span className="badge">文本录入</span>
            </div>
            <div className="card-body">
              <div className="field">
                <label htmlFor="kb-name">文档名称</label>
                <input
                  id="kb-name"
                  className="input"
                  type="text"
                  placeholder="例如：LangChain 官方文档"
                  value={uploadName}
                  onChange={event => setUploadName(event.target.value)}
                />
              </div>
              <div className="field" style={{ marginTop: 12 }}>
                <label htmlFor="kb-cat">分类</label>
                <select
                  id="kb-cat"
                  value={uploadCategory}
                  onChange={event => setUploadCategory(event.target.value)}
                >
                  <option value="general">通用</option>
                  <option value="tech">技术</option>
                  <option value="news">新闻</option>
                  {categories.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="field" style={{ marginTop: 12 }}>
                <label htmlFor="kb-text">文档内容</label>
                <textarea
                  id="kb-text"
                  rows={12}
                  placeholder="粘贴文档内容..."
                  value={uploadText}
                  onChange={event => setUploadText(event.target.value)}
                  style={{ resize: 'vertical', fontFamily: 'inherit', minHeight: 160 }}
                />
              </div>
              <div className="actions" style={{ marginTop: 12 }}>
                <button
                  className="btn primary"
                  onClick={handleUpload}
                  disabled={uploading}
                  type="button"
                >
                  <Plus size={16} aria-hidden="true" />
                  {uploading ? '添加中...' : '添加到知识库'}
                </button>
                <label className="btn" style={{ cursor: 'pointer' }}>
                  <BookOpen size={16} aria-hidden="true" />
                  导入文本文件
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".md,.txt,.csv,text/plain,text/csv,text/markdown"
                    style={{ display: 'none' }}
                    onChange={handleFileUpload}
                  />
                </label>
              </div>
            </div>
          </article>

          <article className="card">
            <div className="card-head"><span>使用说明</span></div>
            <div className="card-body">
              <h4 style={{ marginTop: 0, marginBottom: 8, fontSize: '0.95rem' }}>支持的格式</h4>
              <ul style={{ paddingLeft: 20, marginBottom: 16 }}>
                <li>纯文本（.txt）— 直接粘贴</li>
                <li>Markdown（.md）— 粘贴或导入</li>
                <li>CSV（.csv）— 按纯文本导入，保留原始内容</li>
              </ul>
              <h4 style={{ marginTop: 0, marginBottom: 8, fontSize: '0.95rem' }}>工作原理</h4>
              <p className="text-sm text-muted">
                文档内容会被分块（chunk），每块生成向量嵌入，结合 FTS5 全文索引，
                通过 RRF（Reciprocal Rank Fusion）混合检索，返回最相关的结果。
              </p>
              <p className="text-sm text-muted" style={{ marginTop: 8 }}>
                PDF 和 DOCX 暂不支持浏览器直接导入，请先复制文本内容后粘贴到上方输入框。
              </p>
            </div>
          </article>
        </section>
      )}

      {tab === 'search' && (
        <>
          <section className="card" style={{ marginBottom: 16 }}>
            <div className="card-head"><span>搜索内容</span></div>
            <div className="card-body">
              <div className="actions" style={{ flexWrap: 'wrap', gap: 8 }}>
                <input
                  className="input"
                  style={{ flex: 1, minWidth: 200 }}
                  value={query}
                  placeholder="输入关键词搜索知识库"
                  onChange={event => setQuery(event.target.value)}
                  onKeyDown={event => { if (event.key === 'Enter') void handleSearch() }}
                />
                <select
                  className="input"
                  style={{ width: 80 }}
                  value={topK}
                  onChange={event => setTopK(Number(event.target.value))}
                  aria-label="返回结果数量"
                >
                  {[5, 10, 20, 50].map(n => (
                    <option key={n} value={n}>{n} 条</option>
                  ))}
                </select>
                <button
                  className="btn primary"
                  onClick={() => void handleSearch()}
                  disabled={loading || !query.trim()}
                  type="button"
                >
                  <Search size={16} aria-hidden="true" />
                  {loading ? '搜索中' : '搜索'}
                </button>
              </div>
              {results.length > 0 && (
                <div className="list" style={{ marginTop: 16 }}>
                  {results.map(result => (
                    <div className="list-item" key={`${result.document_id}-${result.score}`}>
                      <div className="list-copy">
                        <strong>{result.title}</strong>
                        <span className="text-sm text-muted" style={{ display: 'block', marginTop: 2 }}>
                          {result.chunk.length > 200
                            ? result.chunk.slice(0, 200) + '…'
                            : result.chunk}
                        </span>
                      </div>
                      <span className="badge">{Math.round(result.score * 100)}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section>
            <article className="card">
              <div className="card-head">
                <span>已上传文档</span>
                <span className="badge">{documents.length} 条</span>
              </div>
              {documents.length === 0 ? (
                <div className="empty">
                  <FileSearch size={28} aria-hidden="true" />
                  <strong>尚无可展示的文档</strong>
                  <p>点击上方「添加文档」标签上传第一篇文档。</p>
                </div>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>名称</th>
                        <th>分类</th>
                        <th>分块</th>
                        <th>创建时间</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {documents.map(document => (
                        <tr key={document.id}>
                          <td>
                            <strong>{document.name}</strong>
                            {document.summary && (
                              <span className="text-sm text-muted" style={{ display: 'block' }}>
                                {document.summary.length > 60
                                  ? document.summary.slice(0, 60) + '…'
                                  : document.summary}
                              </span>
                            )}
                          </td>
                          <td>
                            <span className="badge">{document.category_id}</span>
                          </td>
                          <td>{document.chunk_count}</td>
                          <td className="text-sm text-muted">
                            {new Date(document.created_at).toLocaleDateString('zh-CN')}
                          </td>
                          <td>
                            <button
                              className="btn icon-btn"
                              onClick={() => void handleDelete(document.id)}
                              type="button"
                              aria-label={`删除 ${document.name}`}
                            >
                              <Trash2 size={16} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </article>
          </section>
        </>
      )}
    </>
  )
}
