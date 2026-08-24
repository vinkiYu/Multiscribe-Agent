import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { ChevronRight, Database, FileText, FolderPlus, LibraryBig, RefreshCw, Search, Sparkles, Trash, Upload } from 'lucide-react'
import { SectionHeading } from '../components/SectionHeading'
import { DataStatus } from '../components/DataStatus'
import { knowledgeApi, type JsonRecord } from '../services/api'
import { useRemoteData } from '../hooks/useRemoteData'
import type { KnowledgeCategory, KnowledgeDocument } from '../types'

function formatTimestamp(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return '尚未更新'
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

interface KBSearchHit {
  chunk_id: string
  document_id: string
  content: string
  score: number
  source: string
}

function categoryName(categories: KnowledgeCategory[], id: string): string {
  return categories.find((item) => item.id === id)?.name ?? id
}

interface LocalCategory extends KnowledgeCategory {
  child_count?: number
}

export function KnowledgePage({ onFlash }: { onFlash: (message: string) => void }): ReactElement {
  const categoriesRemote = useRemoteData<JsonRecord[]>(() => knowledgeApi.categories())
  const documentsRemote = useRemoteData<JsonRecord[]>(() => knowledgeApi.documents())
  const categories = useMemo<LocalCategory[]>(
    () => (categoriesRemote.data ?? []).map((row) => ({ ...(row as unknown as KnowledgeCategory) })),
    [categoriesRemote.data],
  )
  const docs = (documentsRemote.data ?? []) as unknown as KnowledgeDocument[]
  const loading = (categoriesRemote.loading || documentsRemote.loading) && !categoriesRemote.data && !documentsRemote.data
  const error = categoriesRemote.error?.message ?? documentsRemote.error?.message ?? null
  const hasData = Boolean(categoriesRemote.data) || Boolean(documentsRemote.data)

  const [activeCategory, setActiveCategory] = useState<string>('all')
  const [query, setQuery] = useState('')
  const [activeDocId, setActiveDocId] = useState<string>('')
  const [hits, setHits] = useState<KBSearchHit[]>([])
  const [searching, setSearching] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  useEffect(() => {
    if (!activeDocId && docs.length > 0) setActiveDocId(docs[0].id)
  }, [activeDocId, docs])

  const filtered = useMemo(() => {
    return docs.filter((doc) => {
      if (activeCategory !== 'all' && doc.category_id !== activeCategory) return false
      if (query.trim() && !`${doc.name}${doc.summary}`.toLowerCase().includes(query.trim().toLowerCase())) return false
      return true
    })
  }, [docs, activeCategory, query])

  const activeDoc = docs.find((d) => d.id === activeDocId) ?? filtered[0] ?? null

  const runSearch = async (text: string): Promise<void> => {
    if (!text.trim()) {
      setHits([])
      return
    }
    setSearching(true)
    try {
      const result = await knowledgeApi.search(text.trim(), 10, activeCategory === 'all' ? undefined : activeCategory)
      setHits(result.hits.map((hit) => hit as unknown as KBSearchHit))
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '检索失败')
    } finally {
      setSearching(false)
    }
  }

  const removeDoc = async (id: string): Promise<void> => {
    setPendingDelete(id)
    try {
      await knowledgeApi.removeDocument(id)
      onFlash(`已删除文档 ${id}。`)
      await documentsRemote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '删除失败')
    } finally {
      setPendingDelete(null)
    }
  }

  const ingestText = async (): Promise<void> => {
    const text = window.prompt('请输入要导入的纯文本：')
    if (!text) return
    if (!activeDoc && categories[0] === undefined) {
      onFlash('请先创建类目再导入文档。')
      return
    }
    try {
      const categoryId = activeCategory === 'all' ? categories[0]?.id : activeCategory
      if (!categoryId) {
        onFlash('请选择目标类目。')
        return
      }
      await knowledgeApi.ingestText({
        text,
        category_id: categoryId,
        name: text.slice(0, 32),
        summary: text.slice(0, 120),
      })
      onFlash('已提交文本导入任务，请稍候。')
      await documentsRemote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '导入失败')
    }
  }

  const createCategory = async (): Promise<void> => {
    const name = window.prompt('请输入新类目名称：')
    if (!name) return
    try {
      await knowledgeApi.createCategory(name.trim(), '')
      onFlash(`类目「${name}」已创建。`)
      await categoriesRemote.reload()
    } catch (caught) {
      onFlash(caught instanceof Error ? caught.message : '创建类目失败')
    }
  }

  return (
    <>
      <SectionHeading
        icon={<LibraryBig />}
        title="知识库"
        description="对接 /api/kb/*：浏览类目、检索文档、导入文本到向量库。"
        actions={
          <>
            <button className="btn" type="button" onClick={() => { void categoriesRemote.reload(); void documentsRemote.reload() }}>
              <RefreshCw /> 刷新
            </button>
            <button className="btn" type="button" onClick={createCategory}>
              <FolderPlus /> 新建类目
            </button>
            <button className="btn btn-primary" type="button" onClick={ingestText}>
              <Upload /> 导入文本
            </button>
          </>
        }
      />

      <DataStatus
        loading={loading}
        error={error}
        empty={!hasData && !loading}
        emptyTitle="暂无文档"
        emptyDescription="完成首次导入后，向量检索会立即生效。"
        onRetry={() => { void categoriesRemote.reload(); void documentsRemote.reload() }}
      >
        <section className="section">
          <div className="knowledge-layout">
            <aside className="knowledge-tree" aria-label="类目">
              <header className="knowledge-tree-header">
                <strong>类目</strong>
                <span>{categories.length} 个</span>
              </header>
              <ul className="knowledge-tree-list">
                <li className="knowledge-tree-item">
                  <button
                    type="button"
                    className={activeCategory === 'all' ? 'knowledge-tree-row is-active' : 'knowledge-tree-row'}
                    onClick={() => setActiveCategory('all')}
                  >
                    <span className="knowledge-tree-caret knowledge-tree-caret-leaf" aria-hidden="true" />
                    <span className="knowledge-tree-label">全部文档</span>
                    <span className="knowledge-tree-count">{docs.length}</span>
                  </button>
                </li>
                {categories.map((category) => {
                  const isActive = activeCategory === category.id
                  return (
                    <li className="knowledge-tree-item" key={category.id}>
                      <button
                        type="button"
                        className={isActive ? 'knowledge-tree-row is-active' : 'knowledge-tree-row'}
                        onClick={() => setActiveCategory(category.id)}
                      >
                        <ChevronRight className="knowledge-tree-caret" aria-hidden="true" />
                        <span className="knowledge-tree-label">{category.name}</span>
                        <span className="knowledge-tree-count">{category.document_count}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </aside>

            <article className="knowledge-list" aria-label="文档列表">
              <header className="knowledge-list-header">
                <label className="knowledge-search">
                  <Search />
                  <input
                    type="search"
                    value={query}
                    placeholder="搜索文档标题或正文"
                    onChange={(event) => {
                      setQuery(event.target.value)
                      void runSearch(event.target.value)
                    }}
                  />
                </label>
                <span className="knowledge-result-count">{filtered.length} 个文档</span>
              </header>
              {filtered.length === 0 ? (
                <div className="empty-card">
                  <div>
                    <div className="empty-icon" aria-hidden="true"><FileText /></div>
                    <h3 className="empty-title">没有匹配的文档</h3>
                    <p className="empty-description">试试清空搜索框或切换到其他类目。</p>
                  </div>
                </div>
              ) : (
                <ul className="knowledge-doc-list">
                  {filtered.map((doc) => {
                    const isActive = doc.id === activeDocId
                    return (
                      <li
                        key={doc.id}
                        className={isActive ? 'knowledge-doc-card is-active' : 'knowledge-doc-card'}
                        onClick={() => setActiveDocId(doc.id)}
                      >
                        <span className="knowledge-doc-icon" aria-hidden="true"><FileText /></span>
                        <div className="knowledge-doc-main">
                          <strong>{doc.name}</strong>
                          <p>{doc.summary}</p>
                          <div className="knowledge-doc-meta">
                            <span>{doc.type}</span>
                            <span>{doc.chunk_count} chunks</span>
                            <time>{formatTimestamp(doc.updated_at)}</time>
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </article>

            <aside className="knowledge-detail" aria-label="文档详情">
              {!activeDoc ? (
                <div className="state-panel"><LibraryBig /><h2>选择文档</h2><p>条目选中后，可在此查看摘要、检索片段和操作。</p></div>
              ) : (
                <>
                  <header className="knowledge-detail-header">
                    <div>
                      <h2>{activeDoc.name}</h2>
                      <p>{activeDoc.file_name} · {formatTimestamp(activeDoc.updated_at)} · {activeDoc.chunk_count} chunks</p>
                    </div>
                    <span className="pill pill-neutral">{activeDoc.type}</span>
                  </header>

                  <section className="knowledge-detail-section">
                    <h3>摘要</h3>
                    <p>{activeDoc.summary || '尚未填写摘要。'}</p>
                  </section>

                  <section className="knowledge-detail-section">
                    <h3><Sparkles /> 检索片段 {searching ? '· 检索中…' : ''}</h3>
                    {hits.length === 0 ? (
                      <p className="knowledge-detail-empty">在上方搜索框输入关键词触发 /api/kb/search。</p>
                    ) : (
                      <ul className="knowledge-hit-list">
                        {hits.map((hit) => (
                          <li key={hit.chunk_id} className="knowledge-hit">
                            <span className={`score-pill ${hit.score >= 0.85 ? 'score-high' : 'score-mid'}`}>{hit.score.toFixed(2)}</span>
                            <p>{hit.content}</p>
                            <small>{hit.source}</small>
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>

                  <section className="knowledge-detail-section">
                    <h3><Database /> 元数据</h3>
                    <ul className="knowledge-meta-list">
                      <li><span>类目</span><strong>{categoryName(categories, activeDoc.category_id)}</strong></li>
                      <li><span>Chunks</span><strong>{activeDoc.chunk_count}</strong></li>
                      <li><span>更新时间</span><strong>{formatTimestamp(activeDoc.updated_at)}</strong></li>
                    </ul>
                  </section>

                  <footer className="knowledge-detail-footer">
                    <button className="btn" type="button" disabled={pendingDelete === activeDoc.id} onClick={() => void removeDoc(activeDoc.id)}>
                      <Trash /> {pendingDelete === activeDoc.id ? '删除中…' : '删除'}
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