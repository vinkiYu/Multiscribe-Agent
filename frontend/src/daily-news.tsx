import { StrictMode, useCallback, useEffect, useMemo, useState, type ReactElement } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowLeft, ArrowRight, CalendarDays, Clock3, ExternalLink, FileText, Menu, RefreshCw, Rss, Sparkles, Tags, X } from 'lucide-react'
import logoUrl from '../multiscribe-logo.svg'
import './daily-news.css'

interface ArchiveSummary { date: string; title: string; item_count: number; updated_at: string }
interface NewsItem { title: string; summary: string; url: string; source: string; score: number | null; image_url: string | null; published_at: string | null; section: string; tags: string[] }
interface Digest { date: string; title: string; summary: string; items: NewsItem[]; total_scanned: number; updated_at: string }
interface DailyNewsResponse { archives: ArchiveSummary[]; digest: Digest | null }

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'
const DIGEST_SECTIONS = ['产品与功能更新', '前沿研究', '行业展望与社会影响', '开源TOP项目'] as const

function formatDate(value: string, options: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'long', day: 'numeric' }): string {
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', options).format(date)
}

function formatTime(value: string | null): string {
  if (!value) return '时间未知'
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

async function fetchDigest(date?: string): Promise<DailyNewsResponse> {
  const params = new URLSearchParams({ limit: '31' })
  if (date) params.set('date', date)
  const response = await fetch(`${API_BASE}/daily-news?${params}`)
  if (!response.ok) throw new Error(response.status === 503 ? '资讯服务正在启动，请稍后刷新。' : '暂时无法读取每日资讯。')
  return response.json() as Promise<DailyNewsResponse>
}

function DailyNewsApp(): ReactElement {
  const [selectedDate, setSelectedDate] = useState<string | undefined>()
  const [data, setData] = useState<DailyNewsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const [activeSection, setActiveSection] = useState<string | null>(null)

  const load = useCallback(async (): Promise<void> => {
    setLoading(true); setError('')
    try { setData(await fetchDigest(selectedDate)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : '暂时无法读取每日资讯。') }
    finally { setLoading(false) }
  }, [selectedDate])

  useEffect(() => { void load() }, [load])
  const digest = data?.digest ?? null
  const selectedIndex = useMemo(() => data?.archives.findIndex((archive) => archive.date === digest?.date) ?? -1, [data, digest?.date])
  const newer = selectedIndex > 0 ? data?.archives[selectedIndex - 1] : undefined
  const older = selectedIndex >= 0 ? data?.archives[selectedIndex + 1] : undefined
  const chooseDate = (date: string): void => { setSelectedDate(date); setActiveSection(null); setMenuOpen(false); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  const sections = useMemo(() => {
    const groups = new Map<string, NewsItem[]>()
    digest?.items.forEach((item) => { const section = item.section || '产品与功能更新'; groups.set(section, [...(groups.get(section) ?? []), item]) })
    return DIGEST_SECTIONS
      .map((section) => [section, groups.get(section) ?? []] as const)
      .filter(([, items]) => items.length > 0)
  }, [digest])
  const contentsActiveSection = sections.some(([section]) => section === activeSection) ? activeSection : sections[0]?.[0]

  return <div className="news-page">
    <header className="news-header">
      <div className="news-header-inner">
        <a className="news-brand" href="./index.html" aria-label="返回 Multiscribe 官网"><img src={logoUrl} alt="Multiscribe" /><strong>Multi<span>scribe</span></strong></a>
        <nav className={menuOpen ? 'news-nav open' : 'news-nav'} aria-label="网站导航">
          <a href="./index.html">项目介绍</a>
          <a className="active" href="./daily-news.html" aria-current="page">每日资讯</a>
          <span aria-disabled="true" title="开始使用页面暂未开放">开始使用</span>
          <span aria-disabled="true" title="了解作者页面暂未开放">了解作者</span>
        </nav>
        <button className="news-menu-button" type="button" aria-label={menuOpen ? '关闭导航' : '打开导航'} onClick={() => setMenuOpen((open) => !open)}>{menuOpen ? <X /> : <Menu />}</button>
      </div>
    </header>
    <main>
      <section className="news-hero">
        <div className="news-container">
          <p className="news-kicker"><Sparkles />每日资讯</p>
          <div className="news-hero-grid">
            <div><h1>{digest ? formatDate(digest.date) : '每日资讯归档'}</h1><p>{digest?.summary || '从多源内容中筛选重点资讯，生成可追溯的每日阅读清单。'}</p></div>
            <div className="news-hero-meta"><span><Rss />已扫描 {digest?.total_scanned ?? 0} 条</span><span><FileText />精选 {digest?.items.length ?? 0} 条</span><span><Clock3 />{digest ? `更新于 ${formatTime(digest.updated_at)}` : '等待日报生成'}</span></div>
          </div>
        </div>
      </section>
      <div className="news-container news-layout">
        <aside className="archive-panel" aria-label="日报归档">
          <div className="archive-heading"><CalendarDays /><div><strong>日报归档</strong><span>{data?.archives.length ?? 0} 期内容</span></div></div>
          {data?.archives.length ? <div className="archive-list">{data.archives.map((archive) => <button key={archive.date} type="button" className={archive.date === digest?.date ? 'archive-item active' : 'archive-item'} onClick={() => chooseDate(archive.date)}><time>{formatDate(archive.date, { month: 'numeric', day: 'numeric' })}</time><span>{archive.item_count} 条资讯</span></button>)}</div> : <p className="archive-empty">日报生成后会在这里按日期归档。</p>}
        </aside>
        <article className="news-article" aria-busy={loading}>
          {loading && <section className="news-state"><RefreshCw className="spin" /><h2>正在读取今日资讯</h2><p>正在加载归档和精选内容。</p></section>}
          {!loading && error && <section className="news-state error"><h2>暂时无法加载</h2><p>{error}</p><button type="button" onClick={() => void load()}><RefreshCw />重新加载</button></section>}
          {!loading && !error && !digest && <section className="news-state"><FileText /><h2>尚未生成日报</h2><p>运行每日资讯流水线后，AI 精选结果会自动归档到此处。</p></section>}
          {!loading && !error && digest && <>
            <section className="article-heading" id="today-summary"><p>今日摘要</p><h2>{digest.title}</h2><span>共 {digest.items.length} 条精选资讯，按主题分模块阅读</span></section>
            {sections.map(([section, items]) => <section className="news-section" id={`section-${section}`} key={section}><header className="news-section-heading"><h2>{section}</h2><span>{items.length} 条</span></header><ol className="news-list">{items.map((item, index) => <li className={item.image_url ? 'news-item has-image' : 'news-item'} key={`${item.url}-${index}`}>
              <span className="news-index">{String(index + 1).padStart(2, '0')}</span>
              <div className="news-item-body"><div className="news-item-meta"><span>{item.source || '未知来源'}</span><time>{formatTime(item.published_at)}</time>{item.score !== null && <b>{item.score.toFixed(1)} 分</b>}</div><h3><a href={item.url} target="_blank" rel="noreferrer">{item.title}<ExternalLink /></a></h3><p>{item.summary || '该条资讯暂未提供摘要。'}</p>{item.tags.length > 0 && <div className="news-tags"><Tags />{item.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}</div>
              {item.image_url && <img className="news-item-image" src={item.image_url} alt="" loading="lazy" onError={(event) => { event.currentTarget.hidden = true }} />}
            </li>)}</ol></section>)}
            <nav className="article-pagination" aria-label="日报翻页"><button type="button" disabled={!newer} onClick={() => newer && chooseDate(newer.date)}><ArrowLeft />{newer ? formatDate(newer.date, { month: 'numeric', day: 'numeric' }) : '没有更新日报'}</button><button type="button" disabled={!older} onClick={() => older && chooseDate(older.date)}>{older ? formatDate(older.date, { month: 'numeric', day: 'numeric' }) : '没有更早日报'}<ArrowRight /></button></nav>
          </>}
        </article>
        {digest && <aside className="contents-panel" aria-label="本页目录"><div className="contents-heading"><Menu /><div><strong>本页目录</strong><span>按板块阅读</span></div></div><div className="contents-list">{sections.map(([section]) => <a key={section} className={section === contentsActiveSection ? 'contents-item active' : 'contents-item'} href={`#section-${section}`} onClick={() => setActiveSection(section)}>{section}</a>)}</div><button type="button" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>回到顶部</button></aside>}
      </div>
    </main>
    <footer className="news-footer"><div className="news-container"><p>Multiscribe 每日资讯，由内容采集、去重、AI 精选与摘要流水线生成。</p><a href="./index.html">返回项目介绍</a></div></footer>
  </div>
}

export default DailyNewsApp

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DailyNewsApp />
  </StrictMode>,
)
