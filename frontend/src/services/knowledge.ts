import { ApiError, getToken } from './api'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export interface KBDocument {
  id: string
  title: string
  category: string
  created_at: string
  chunk_count: number
}

export interface KBSearchResult {
  document_id: string
  title: string
  chunk: string
  score: number
  highlight?: string
}

export interface KBSearchResponse {
  query: string
  results: KBSearchResult[]
  total: number
}

export class ApiUnavailableError extends Error {
  constructor(message = '知识库后端 API 尚未上线，等待 P16 完成') {
    super(message)
    this.name = 'ApiUnavailableError'
  }
}

let availability: boolean | null = null

function headers(): HeadersInit {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function requestKnowledge<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (availability === false) throw new ApiUnavailableError()
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers(), ...(options.headers ?? {}) },
    })
    if (response.status === 404 || response.status === 501) {
      availability = false
      throw new ApiUnavailableError()
    }
    if (!response.ok) {
      throw new ApiError('Knowledge base request failed', response.status)
    }
    availability = true
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiUnavailableError || error instanceof ApiError) throw error
    availability = false
    throw new ApiUnavailableError()
  }
}

export const knowledgeService = {
  async isAvailable(): Promise<boolean> {
    if (availability !== null) return availability
    try {
      await requestKnowledge<{ status: string }>('/kb/health')
      return true
    } catch (error) {
      if (error instanceof ApiUnavailableError) return false
      throw error
    }
  },

  async uploadDocument(file: File, category: string): Promise<KBDocument> {
    const form = new FormData()
    form.append('file', file)
    form.append('category', category)
    return await requestKnowledge<KBDocument>('/kb/documents', { method: 'POST', body: form })
  },

  async search(query: string, topK = 10): Promise<KBSearchResponse> {
    const params = new URLSearchParams({ q: query, top_k: String(topK) })
    return await requestKnowledge<KBSearchResponse>(`/kb/search?${params.toString()}`)
  },

  async listDocuments(): Promise<KBDocument[]> {
    return await requestKnowledge<KBDocument[]>('/kb/documents')
  },

  async deleteDocument(id: string): Promise<void> {
    await requestKnowledge<undefined>(`/kb/documents/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
  },
}
