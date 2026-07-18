const STORAGE_KEY = 'multiscribe_memory_prefs'

export interface MemoryPreferences {
  preferred_tags: string[]
  blocked_sources: string[]
  push_time: string
  max_items_per_digest: number
}

export interface MemoryEntry {
  id: string
  category: string
  content: string
  tags: string[]
  created_at: string
}

const DEFAULT_PREFERENCES: MemoryPreferences = {
  preferred_tags: [],
  blocked_sources: [],
  push_time: '09:00',
  max_items_per_digest: 5,
}

function validPreferences(value: unknown): value is MemoryPreferences {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<MemoryPreferences>
  return (
    Array.isArray(candidate.preferred_tags) &&
    candidate.preferred_tags.every(tag => typeof tag === 'string') &&
    Array.isArray(candidate.blocked_sources) &&
    candidate.blocked_sources.every(source => typeof source === 'string') &&
    typeof candidate.push_time === 'string' &&
    typeof candidate.max_items_per_digest === 'number'
  )
}

function defaultPreferences(): MemoryPreferences {
  return { ...DEFAULT_PREFERENCES, preferred_tags: [], blocked_sources: [] }
}

function normalizePreferences(value: MemoryPreferences): MemoryPreferences {
  return {
    preferred_tags: [...new Set(value.preferred_tags.map(tag => tag.trim()).filter(Boolean))],
    blocked_sources: [...new Set(value.blocked_sources.map(source => source.trim()).filter(Boolean))],
    push_time: value.push_time || DEFAULT_PREFERENCES.push_time,
    max_items_per_digest: Math.min(20, Math.max(1, Math.trunc(value.max_items_per_digest) || 5)),
  }
}

export const memoryService = {
  getPreferences(): MemoryPreferences {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return defaultPreferences()
    try {
      const decoded: unknown = JSON.parse(stored)
      return validPreferences(decoded) ? normalizePreferences(decoded) : defaultPreferences()
    } catch {
      return defaultPreferences()
    }
  },

  savePreferences(preferences: MemoryPreferences): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(normalizePreferences(preferences)))
  },

  resetPreferences(): void {
    localStorage.removeItem(STORAGE_KEY)
  },

  exportPreferences(): string {
    return JSON.stringify(this.getPreferences(), null, 2)
  },

  importPreferences(raw: string): void {
    const decoded: unknown = JSON.parse(raw)
    if (!validPreferences(decoded)) throw new Error('导入文件不包含有效的偏好配置')
    this.savePreferences(decoded)
  },

  getHistory(): MemoryEntry[] {
    return []
  },
}
