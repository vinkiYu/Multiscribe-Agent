import { useCallback, useState, type ReactElement } from 'react'
import { Files, Search } from 'lucide-react'
import { ApiError, sourceDataApi, type SourceData } from '../services/api'

export function SourceSearchPage(): ReactElement {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SourceData[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = useCallback(async (): Promise<void> => {
    const normalized = query.trim()
    if (!normalized) return
    setLoading(true)
    setError(null)
    try {
      setResults(await sourceDataApi.search(normalized))
    } catch (caught) {
      setResults(null)
      setError(caught instanceof ApiError ? caught.message : '搜索失败')
    } finally {
      setLoading(false)
    }
  }, [query])

  return <div className="data-stack source-search-page">
    <section className="data-panel">
      <div className="data-summary"><Search /><span>数据源搜索</span></div>
      <form className="search-bar" onSubmit={(event) => { event.preventDefault(); void handleSearch() }}>
        <input aria-label="搜索数据源" placeholder="输入关键词搜索数据源" value={query} onChange={(event) => setQuery(event.target.value)} />
        <button type="submit" className="button compact" disabled={loading || !query.trim()}><Search />{loading ? '搜索中' : '搜索'}</button>
      </form>
    </section>

    {error && <p className="empty-inline source-search-error">{error}</p>}
    {results !== null && <section className="data-panel">
      <div className="data-summary"><Files /><span>找到 {results.length} 条结果</span></div>
      {results.length === 0 ? <p className="empty-inline">未找到匹配结果</p> : <div className="data-list">{results.map((item) => <article className="data-row source-search-result" key={item.id}>
        <div>
          <a className="content-link" href={item.url} target="_blank" rel="noreferrer"><strong>{item.title}</strong></a>
          <HighlightedDescription value={item.description} />
          <div className="tag-list"><span className="tag">{item.source}</span><span className="tag">{item.adapter_name}</span></div>
        </div>
        <span className="row-meta">{item.published_date}</span>
      </article>)}</div>}
    </section>}
  </div>
}

function HighlightedDescription({ value }: { value: string }): ReactElement {
  const parts = value.split(/(<mark>.*?<\/mark>)/gi)
  return <p>{parts.map((part, index) => part.toLowerCase().startsWith('<mark>') ? <mark key={`${index}-${part}`}>{part.slice(6, -7)}</mark> : part)}</p>
}

export default SourceSearchPage
