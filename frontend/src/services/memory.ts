import { ApiError, getToken } from './api'

const STORAGE_KEY = 'multiscribe_memory_prefs'
const API_BASE = import.meta.env.VITE_API_BASE || '/api'

// ---------------------------------------------------------------------------
// Domain types (align with backend /api/memory schema)
// ---------------------------------------------------------------------------

export interface MemoryPreferences {
  preferred_tags: string[]
  blocked_sources: string[]
  push_time: string
  max_items_per_digest: number // frontend-only; not sent to backend
}

export interface MemoryEntry {
  id: string
  category: string
  content: string
  tags: string[]
  importance: number
  created_at: string
  agent_id?: string | null
  metadata?: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// localStorage defaults (survive when backend is offline)
// ---------------------------------------------------------------------------

const DEFAULT_PREFERENCES: MemoryPreferences = {
  preferred_tags: [],
  blocked_sources: [],
  push_time: '09:00',
  max_items_per_digest: 5,
}

// ---------------------------------------------------------------------------
// localStorage round-trip helpers
// ---------------------------------------------------------------------------

function validPreferences(value: unknown): value is MemoryPreferences {
  if (!value || typeof value !== 'object') return false
  const p = value as Partial<MemoryPreferences>
  return (
    Array.isArray(p.preferred_tags) &&
    p.preferred_tags.every(t => typeof t === 'string') &&
    Array.isArray(p.blocked_sources) &&
    p.blocked_sources.every(s => typeof s === 'string') &&
    typeof p.push_time === 'string' &&
    typeof p.max_items_per_digest === 'number'
  )
}

function normalizePrefs(raw: unknown): MemoryPreferences {
  if (!validPreferences(raw)) return { ...DEFAULT_PREFERENCES }
  const p = raw as MemoryPreferences
  return {
    preferred_tags: [...new Set(p.preferred_tags.map(t => t.trim()).filter(Boolean))],
    blocked_sources: [...new Set(p.blocked_sources.map(s => s.trim()).filter(Boolean))],
    push_time: p.push_time || DEFAULT_PREFERENCES.push_time,
    max_items_per_digest: Math.min(20, Math.max(1, Math.trunc(p.max_items_per_digest) || 5)),
  }
}

function backendPrefs(p: MemoryPreferences): Record<string, unknown> {
  return {
    preferred_tags: p.preferred_tags,
    block_sources: p.blocked_sources,
    push_time: p.push_time,
    importance_threshold: 3,
  }
}

// ---------------------------------------------------------------------------
// Backend API client
// ---------------------------------------------------------------------------

let _backendAvailable: boolean | null = null

function headers(): HeadersInit {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function requestMemory<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (_backendAvailable === false) throw new BackendUnavailableError()
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...headers() },
    })
    if (response.status === 404 || response.status === 501 || response.status === 503) {
      _backendAvailable = false
      throw new BackendUnavailableError()
    }
    if (!response.ok) {
      let payload: unknown = null
      try {
        payload = await response.json()
      } catch {
        // ignore
      }
      const detail =
        (payload as { detail?: string } | null)?.detail ?? `Memory API failed (${response.status})`
      throw new ApiError(detail, response.status, payload)
    }
    _backendAvailable = true
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  } catch (error) {
    if (error instanceof BackendUnavailableError || error instanceof ApiError) throw error
    _backendAvailable = false
    throw new BackendUnavailableError()
  }
}

function normalizeEntry(raw: Record<string, unknown>): MemoryEntry {
  const createdTs = Number(raw['created_at'] ?? 0)
  return {
    id: String(raw['id'] ?? ''),
    category: String(raw['category'] ?? 'general'),
    content: String(raw['content'] ?? ''),
    tags: Array.isArray(raw['tags']) ? (raw['tags'] as string[]) : [],
    importance: Number(raw['importance'] ?? 5),
    created_at:
      Number.isFinite(createdTs) && createdTs > 0
        ? new Date(createdTs * 1000).toISOString()
        : new Date().toISOString(),
    agent_id:
      typeof raw['agent_id'] === 'string' ? raw['agent_id'] : null,
    metadata:
      raw['metadata'] && typeof raw['metadata'] === 'object' && !Array.isArray(raw['metadata'])
        ? (raw['metadata'] as Record<string, unknown>)
        : undefined,
  }
}

export class BackendUnavailableError extends Error {
  constructor(message = '记忆后端 API 尚未上线，仅本地配置生效') {
    super(message)
    this.name = 'BackendUnavailableError'
  }
}

// ---------------------------------------------------------------------------
// Memory service (frontend-first with backend sync)
// ---------------------------------------------------------------------------

export const memoryService = {
  // ----- availability check -----
  async isBackendAvailable(): Promise<boolean> {
    if (_backendAvailable !== null) return _backendAvailable
    try {
      await requestMemory<MemoryPreferences>('/memory/preferences')
      _backendAvailable = true
    } catch {
      _backendAvailable = false
    }
    return _backendAvailable
  },

  // ----- preferences (localStorage + optional backend sync) -----
  getPreferences(): MemoryPreferences {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return { ...DEFAULT_PREFERENCES }
    try {
      return normalizePrefs(JSON.parse(stored))
    } catch {
      return { ...DEFAULT_PREFERENCES }
    }
  },

  savePreferences(preferences: MemoryPreferences): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizePrefs(preferences)))
  },

  resetPreferences(): void {
    localStorage.removeItem(STORAGE_KEY)
  },

  exportPreferences(): string {
    return JSON.stringify(this.getPreferences(), null, 2)
  },

  importPreferences(json: string): void {
    const decoded = JSON.parse(json)
    if (!validPreferences(decoded)) throw new Error('导入文件不包含有效的偏好配置')
    this.savePreferences(decoded)
  },

  // Sync preferences to backend (best-effort; fails silently if offline)
  async syncPreferencesToBackend(preferences: MemoryPreferences): Promise<void> {
    try {
      await requestMemory<Record<string, unknown>>('/memory/preferences', {
        method: 'PUT',
        body: JSON.stringify(backendPrefs(preferences)),
      })
    } catch {
      // offline — preferences already saved locally
    }
  },

  // Fetch preferences from backend (falls back to localStorage on failure)
  async fetchPreferencesFromBackend(): Promise<MemoryPreferences> {
    const prefs = await requestMemory<Record<string, unknown>>('/memory/preferences')
    return {
      preferred_tags: Array.isArray(prefs['preferred_tags'])
        ? (prefs['preferred_tags'] as string[])
        : [],
      blocked_sources: Array.isArray(prefs['block_sources'])
        ? (prefs['block_sources'] as string[])
        : [],
      push_time: typeof prefs['push_time'] === 'string' ? prefs['push_time'] : '09:00',
      max_items_per_digest: this.getPreferences().max_items_per_digest,
    }
  },

  // ----- memory entries (backend only) -----
  // days parameter is reserved for future server-side filtering; currently all entries are returned
  async getHistory(days = 30, limit = 50): Promise<MemoryEntry[]> {
    try {
      const response = await requestMemory<Array<Record<string, unknown>>>(
        `/memory/entries?limit=${limit}`,
      )
      void days // reserved for server-side date filtering
      return response.map(normalizeEntry)
    } catch {
      return []
    }
  },

  async searchEntries(query: string, limit = 20): Promise<MemoryEntry[]> {
    try {
      const response = await requestMemory<Array<Record<string, unknown>>>(
        `/memory/entries/search?q=${encodeURIComponent(query)}&limit=${limit}`,
      )
      return response.map(normalizeEntry)
    } catch {
      return []
    }
  },

  async createEntry(entry: Omit<MemoryEntry, 'id' | 'created_at'>): Promise<string | null> {
    try {
      const response = await requestMemory<{ id: string }>('/memory/entries', {
        method: 'POST',
        body: JSON.stringify({
          category: entry.category,
          content: entry.content,
          tags: entry.tags,
          importance: entry.importance,
          agent_id: entry.agent_id ?? null,
          metadata: entry.metadata ?? {},
        }),
      })
      return response.id ?? null
    } catch {
      return null
    }
  },

  async deleteEntry(id: string): Promise<boolean> {
    try {
      await requestMemory<{ status: string }>(`/memory/entries/${encodeURIComponent(id)}`, {
        method: 'DELETE',
      })
      return true
    } catch {
      return false
    }
  },
}
