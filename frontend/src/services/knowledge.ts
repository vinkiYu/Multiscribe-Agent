import { ApiError, getToken } from './api'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export interface KBDocument {
  id: string
  name: string
  category_id: string
  summary: string | null
  chunk_count: number
  created_at: string
}

export interface KBCategory {
  id: string
  name: string
  description: string | null
}

export interface KBCapabilities {
  vector_search: boolean
  fts_search: boolean
  embedding_runtime: boolean
  degraded: boolean
}

export interface KBChunkHit {
  chunk_id: string
  document_id: string
  content: string
  score: number
  source: string
}

export interface KBSearchResponse {
  hits: KBChunkHit[]
  degraded: boolean
  capabilities: KBCapabilities
}

export interface KBSearchResult {
  document_id: string
  title: string
  chunk: string
  score: number
  source: string
}

export class ApiUnavailableError extends Error {
  constructor(message = '知识库后端 API 尚未上线，等待 P16 完成') {
    super(message)
    this.name = 'ApiUnavailableError'
  }
}

let availability: boolean | null = null

function headers(extra: HeadersInit = {}): HeadersInit {
  const token = getToken()
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

async function requestKnowledge<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (availability === false) throw new ApiUnavailableError()
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers(options.headers as HeadersInit) },
    })
    if (response.status === 404 || response.status === 501 || response.status === 503) {
      availability = false
      throw new ApiUnavailableError()
    }
    if (!response.ok) {
      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        // ignore body parse errors
      }
      const detail =
        (payload as { detail?: string } | null)?.detail ??
        `Knowledge base request failed (${response.status})`
      throw new ApiError(detail, response.status, payload)
    }
    availability = true
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiUnavailableError || error instanceof ApiError) throw error
    availability = false
    throw new ApiUnavailableError()
  }
}

function normalizeDocument(payload: Record<string, unknown>): KBDocument {
  const chunkCount = Number(payload['chunk_count'] ?? 0)
  const created = Number(payload['created_at'] ?? 0)
  return {
    id: String(payload['id'] ?? ''),
    name: String(payload['name'] ?? '未命名文档'),
    category_id: String(payload['category_id'] ?? 'general'),
    summary: typeof payload['summary'] === 'string' ? payload['summary'] : null,
    chunk_count: Number.isFinite(chunkCount) ? chunkCount : 0,
    created_at: Number.isFinite(created) && created > 0
      ? new Date(created * 1000).toISOString()
      : new Date().toISOString(),
  }
}

function normalizeCategory(payload: Record<string, unknown>): KBCategory {
  return {
    id: String(payload['id'] ?? ''),
    name: String(payload['name'] ?? '未命名分类'),
    description: typeof payload['description'] === 'string' ? payload['description'] : null,
  }
}

function normalizeHit(hit: KBChunkHit): KBSearchResult {
  return {
    document_id: hit.document_id,
    title: hit.document_id,
    chunk: hit.content,
    score: hit.score,
    source: hit.source,
  }
}

export const knowledgeService = {
  async isAvailable(): Promise<boolean> {
    if (availability !== null) return availability
    try {
      await requestKnowledge<KBCapabilities>('/kb/capabilities')
      availability = true
    } catch (error) {
      if (error instanceof ApiUnavailableError) {
        availability = false
      } else {
        availability = true
      }
    }
    return availability
  },

  async capabilities(): Promise<KBCapabilities> {
    return await requestKnowledge<KBCapabilities>('/kb/capabilities')
  },

  async listCategories(): Promise<KBCategory[]> {
    const response = await requestKnowledge<Array<Record<string, unknown>>>('/kb/categories')
    return response.map(normalizeCategory)
  },

  async createCategory(name: string, description?: string): Promise<KBCategory> {
    const payload: Record<string, string> = { name }
    if (description) payload['description'] = description
    const response = await requestKnowledge<Record<string, unknown>>('/kb/categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return normalizeCategory(response)
  },

  async listDocuments(categoryId?: string): Promise<KBDocument[]> {
    const query = categoryId ? `?category_id=${encodeURIComponent(categoryId)}` : ''
    const response = await requestKnowledge<Array<Record<string, unknown>>>(
      `/kb/documents${query}`,
    )
    return response.map(normalizeDocument)
  },

  async ingestText(input: {
    text: string
    categoryId: string
    name: string
    summary?: string
  }): Promise<KBDocument> {
    const response = await requestKnowledge<Record<string, unknown>>('/kb/documents/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: input.text,
        category_id: input.categoryId,
        name: input.name,
        summary: input.summary ?? '',
      }),
    })
    return normalizeDocument(response)
  },

  async ingestFile(input: {
    filePath: string
    categoryId: string
    name: string
    summary?: string
  }): Promise<KBDocument> {
    const response = await requestKnowledge<Record<string, unknown>>('/kb/documents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: input.filePath,
        category_id: input.categoryId,
        name: input.name,
        summary: input.summary ?? '',
      }),
    })
    return normalizeDocument(response)
  },

  async search(query: string, topK = 10, categoryId?: string): Promise<KBSearchResponse> {
    const params = new URLSearchParams({ q: query, top_k: String(topK) })
    if (categoryId) params.set('category_id', categoryId)
    return await requestKnowledge<KBSearchResponse>(`/kb/search?${params.toString()}`)
  },

  async deleteDocument(id: string): Promise<void> {
    await requestKnowledge<{ status: string }>(`/kb/documents/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
  },

  normalizeHit,
}