type Archive = { date: string; item_count: number }
type Digest = { date: string; summary: string; items: Array<{ title: string; section: string; image_url: string | null }> }

import './marketing-news.css'

const apiBase = import.meta.env.VITE_API_BASE ?? '/api'
const target = document.querySelector('#pricing')

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date(`${value}T00:00:00`))
}

function createCard(digest: Digest): HTMLAnchorElement {
  const card = document.createElement('a')
  card.className = 'marketing-news-card'
  card.href = `./daily-news.html?date=${encodeURIComponent(digest.date)}`
  const image = digest.items.find((item) => item.image_url)?.image_url
  if (image) {
    const media = document.createElement('img')
    media.src = image
    media.alt = ''
    media.loading = 'lazy'
    media.onerror = () => media.remove()
    card.append(media)
  }
  const body = document.createElement('div')
  const meta = document.createElement('p')
  meta.textContent = `${dateLabel(digest.date)} · ${digest.items.length} 条精选`
  const title = document.createElement('h3')
  title.textContent = digest.items[0]?.title ?? 'AI 资讯日报'
  const summary = document.createElement('span')
  summary.textContent = digest.summary || digest.items[0]?.section || '多源 AI 资讯精选'
  body.append(meta, title, summary)
  card.append(body)
  return card
}

async function renderNews(): Promise<void> {
  if (!target) return
  target.innerHTML = ''
  target.className = 'marketing-news-section'
  const heading = document.createElement('div')
  heading.className = 'marketing-news-heading'
  heading.innerHTML = '<span>AI 资讯日报</span><h2>最近 7 期，<b>一眼掌握 AI 动态</b></h2><p>来自 RSS、研究、行业观察和开源项目的每日精选。</p>'
  const grid = document.createElement('div')
  grid.className = 'marketing-news-grid'
  const response = await fetch(`${apiBase}/daily-news?limit=6`)
  if (!response.ok) throw new Error('daily news unavailable')
  const data = await response.json() as { archives: Archive[] }
  const digests = await Promise.all(data.archives.slice(0, 6).map(async (archive) => {
    const itemResponse = await fetch(`${apiBase}/daily-news?date=${archive.date}`)
    const payload = await itemResponse.json() as { digest: Digest | null }
    return payload.digest
  }))
  digests.filter((digest): digest is Digest => digest !== null).forEach((digest) => grid.append(createCard(digest)))
  const more = document.createElement('a')
  more.className = 'marketing-news-more'
  more.href = './daily-news.html'
  more.textContent = '查看全部日报 →'
  target.append(heading, grid, more)
}

void renderNews().catch(() => {
  if (target instanceof HTMLElement) target.hidden = true
})
