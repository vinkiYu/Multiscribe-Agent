/// <reference types="vite/client" />
// Real API client with mock fallback + 401 handling.
// All endpoints below MUST stay aligned with
//   F:\software\Multiscribe\MultiscribeAgent-main\src\multiscribe_agent\api\routes
// Whenever the backend changes (path, method, request body, response shape), update here.

const baseUrl = import.meta.env.VITE_API_BASE ?? '/api'
const useMock = import.meta.env.VITE_USE_MOCK !== 'false'

export interface ApiError extends Error {
  status: number
  detail?: string
}

type UnauthorizedListener = () => void

const listeners = new Set<UnauthorizedListener>()

export function onUnauthorized(handler: UnauthorizedListener): () => void {
  listeners.add(handler)
  return () => { listeners.delete(handler) }
}

export function emitUnauthorized(): void {
  for (const handler of listeners) handler()
}

function authHeader(): Record<string, string> {
  const token = window.localStorage.getItem('multiscribe_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function clearToken(): void {
  // Notify listeners (UI shows a Login modal) instead of redirecting.
  // A redirect to /login.html during a cold start loops Vite's SPA
  // fallback and looks like an infinite reload.
  try { window.localStorage.removeItem('multiscribe_token') } catch { /* noop */ }
  emitUnauthorized()
}

async function request<T>(path: string, init: RequestInit = {}, fallback?: () => T | Promise<T>): Promise<T> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...authHeader(),
    ...(init.headers ?? {}),
  }
  try {
    const response = await fetch(`${baseUrl}${path}`, { ...init, headers })
    if (response.status === 401) {
      clearToken()
      throw makeError(401, '会话已过期，请重新登录。')
    }
    if (!response.ok) {
      const detail = await response.text().catch(() => '')
      throw makeError(response.status, detail || response.statusText)
    }
    if (response.status === 204) return undefined as T
    return await response.json() as T
  } catch (caught) {
    if (fallback && useMock) {
      try { return await fallback() } catch (_) { /* ignore */ }
    }
    if (caught instanceof Error && 'status' in caught) throw caught
    throw makeError(0, caught instanceof Error ? caught.message : 'network error')
  }
}

function makeError(status: number, detail: string): ApiError {
  const err = new Error(detail || `HTTP ${status}`) as ApiError
  err.status = status
  err.detail = detail
  return err
}

export const api = { request }

// All backend responses that we have not yet typed end-to-end are exposed as JsonRecord so that
// TypeScript does not force every page to use a loose implicit shape.
export interface JsonDict { [key: string]: unknown }
export type JsonRecord = JsonDict

// ---------------------------------------------------------------------------
// Auth — POST /api/login (LoginRequest { password }) → { access_token, token_type, must_change_password }
// ---------------------------------------------------------------------------
export const authApi = {
  login: (password: string): Promise<{ access_token: string; token_type: 'bearer'; must_change_password: boolean }> =>
    api.request<{ access_token: string; token_type: 'bearer'; must_change_password: boolean }>(
      '/login',
      { method: 'POST', body: JSON.stringify({ password }) },
      () => ({ access_token: 'demo-token', token_type: 'bearer' as const, must_change_password: false }),
    ),
}

// ---------------------------------------------------------------------------
// Dashboard — GET /api/dashboard/{stats,logs,overview} + POST /api/dashboard/ingest
// ---------------------------------------------------------------------------
export const dashboardApi = {
  getStats: (): Promise<{ source_count: number; scheduled_tasks: number }> =>
    api.request<{ source_count: number; scheduled_tasks: number }>('/dashboard/stats', {}, () => ({ source_count: 0, scheduled_tasks: 0 })),
  getLogs: (): Promise<JsonRecord[]> => api.request<JsonRecord[]>('/dashboard/logs', {}, () => [] as JsonRecord[]),
  getOverview: (): Promise<JsonRecord> => api.request<JsonRecord>('/dashboard/overview', {}, () => ({})),
  ingest: (adapter_id: string, config: JsonDict = {}): Promise<{ result_count: number }> =>
    api.request<{ result_count: number }>(
      '/dashboard/ingest',
      { method: 'POST', body: JSON.stringify({ adapter_id, config }) },
      () => ({ result_count: 0 }),
    ),
}

// ---------------------------------------------------------------------------
// Operations page is fed by /api/dashboard/overview today; this alias keeps the import stable.
export const operationsApi = {
  getOverview: (): Promise<JsonRecord> => dashboardApi.getOverview(),
}

// ---------------------------------------------------------------------------
// Adapter health — GET /api/adapter-health · POST /api/adapter-health/{id}/{enable,disable}
export const adapterHealthApi = {
  list: (): Promise<JsonRecord[]> => api.request<JsonRecord[]>('/adapter-health', {}, () => [] as JsonRecord[]),
  enable: (id: string): Promise<JsonRecord> => api.request<JsonRecord>(
    `/adapter-health/${encodeURIComponent(id)}/enable`,
    { method: 'POST' },
    () => ({}),
  ),
  disable: (id: string): Promise<JsonRecord> => api.request<JsonRecord>(
    `/adapter-health/${encodeURIComponent(id)}/disable`,
    { method: 'POST' },
    () => ({}),
  ),
}

// ---------------------------------------------------------------------------
// Alerts — GET /api/alerts?limit&acknowledged
export const alertsApi = {
  list: (params: { limit?: number; acknowledged?: boolean } = {}): Promise<JsonRecord[]> => {
    const query = new URLSearchParams()
    if (params.limit !== undefined) query.set('limit', String(params.limit))
    if (params.acknowledged !== undefined) query.set('acknowledged', String(params.acknowledged))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return api.request<JsonRecord[]>(`/alerts${suffix}`, {}, () => [] as JsonRecord[])
  },
  acknowledge: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(
    `/alerts/${encodeURIComponent(id)}/acknowledge`,
    { method: 'POST' },
    () => ({ status: 'acknowledged' }),
  ),
}

// ---------------------------------------------------------------------------
// Sources — GET /api/sources → { sources, available_adapters } · PUT /api/sources/{source_id}
export interface SourcesListResponse {
  sources: JsonRecord[]
  available_adapters: JsonRecord[]
}

export const sourcesApi = {
  list: (): Promise<SourcesListResponse> => api.request<SourcesListResponse>(
    '/sources',
    {},
    () => ({ sources: [], available_adapters: [] }),
  ),
  save: (source_id: string, payload: JsonRecord): Promise<JsonRecord> => api.request<JsonRecord>(
    `/sources/${encodeURIComponent(source_id)}`,
    { method: 'PUT', body: JSON.stringify(payload) },
    () => ({ id: source_id, ...payload }),
  ),
}

// ---------------------------------------------------------------------------
// Schedules — GET /api/schedules · POST /api/schedules · DELETE /api/schedules/{id} · POST /api/schedules/{id}/run
export const tasksApi = {
  list: (): Promise<JsonRecord[]> => api.request<JsonRecord[]>('/schedules', {}, () => [] as JsonRecord[]),
  create: (payload: JsonRecord): Promise<JsonRecord> => api.request<JsonRecord>(
    '/schedules',
    { method: 'POST', body: JSON.stringify(payload) },
    () => ({ id: `sched-${Date.now().toString(36)}`, ...payload }),
  ),
  remove: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(
    `/schedules/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
    () => ({ status: 'deleted' }),
  ),
  toggle: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(
    `/schedules/${encodeURIComponent(id)}/run`,
    { method: 'POST' },
    () => ({ status: 'started' }),
  ),
  run: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(
    `/schedules/${encodeURIComponent(id)}/run`,
    { method: 'POST' },
    () => ({ status: 'started' }),
  ),
}

// ---------------------------------------------------------------------------
// Workflows — GET /api/workflows · POST /api/workflows · DELETE /api/workflows/{id}
//            POST /api/workflows/{id}/run → SSE (handled separately)
export const workflowsApi = {
  list: (): Promise<JsonRecord[]> => api.request<JsonRecord[]>('/workflows', {}, () => [] as JsonRecord[]),
  get: (id: string): Promise<JsonRecord> => api.request<JsonRecord>(`/workflows/${encodeURIComponent(id)}`, {}, () => ({})),
  create: (payload: JsonRecord): Promise<JsonRecord> => api.request<JsonRecord>(
    '/workflows',
    { method: 'POST', body: JSON.stringify(payload) },
    () => ({ id: `wf-${Date.now().toString(36)}`, ...payload }),
  ),
  remove: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(
    `/workflows/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
    () => ({ status: 'deleted' }),
  ),
}

// ---------------------------------------------------------------------------
// Content — relies on /api/source-data/search since no /api/content endpoint exists.
export const contentApi = {
  search: (q: string, limit = 20): Promise<JsonRecord[]> => {
    const query = new URLSearchParams({ q, limit: String(limit) })
    return api.request<JsonRecord[]>(`/source-data/search?${query.toString()}`, {}, () => [] as JsonRecord[])
  },
  curate: (ids: string[]): Promise<{ status: string; ids: string[] }> => api.request<{ status: string; ids: string[] }>(
    '/source-data/curate',
    { method: 'POST', body: JSON.stringify({ ids }) },
    () => ({ status: 'curated', ids }),
  ),
  ignore: (ids: string[]): Promise<{ status: string; ids: string[] }> => api.request<{ status: string; ids: string[] }>(
    '/source-data/ignore',
    { method: 'POST', body: JSON.stringify({ ids }) },
    () => ({ status: 'ignored', ids }),
  ),
  publish: (ids: string[]): Promise<{ status: string; ids: string[] }> => api.request<{ status: string; ids: string[] }>(
    '/source-data/publish',
    { method: 'POST', body: JSON.stringify({ ids }) },
    () => ({ status: 'published', ids }),
  ),
}

// Channels — no dedicated /api/channels route; we read publishers from /api/settings.
export const channelsApi = {
  list: (): Promise<JsonRecord[]> => api.request<{ publishers: JsonRecord[] }>(
    '/settings',
    {},
    () => ({ publishers: [] }),
  ).then((payload) => payload.publishers),
}

// ---------------------------------------------------------------------------
// Publishing — GET /api/publish-history · GET /api/publish-history/summary
export interface PublishHistoryPageResponse {
  records: JsonRecord[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export const publishingApi = {
  list: (params: { publisher_id?: string; from_date?: string; to_date?: string; limit?: number; offset?: number } = {}): Promise<PublishHistoryPageResponse> => {
    const query = new URLSearchParams()
    if (params.publisher_id) query.set('publisher_id', params.publisher_id)
    if (params.from_date) query.set('from_date', params.from_date)
    if (params.to_date) query.set('to_date', params.to_date)
    if (params.limit !== undefined) query.set('limit', String(params.limit))
    if (params.offset !== undefined) query.set('offset', String(params.offset))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return api.request<PublishHistoryPageResponse>(`/publish-history${suffix}`, {}, () => ({ records: [], total: 0, limit: params.limit ?? 0, offset: params.offset ?? 0, has_more: false }))
  },
  summary: (): Promise<JsonRecord> => api.request<JsonRecord>('/publish-history/summary', {}, () => ({})),
}

// ---------------------------------------------------------------------------
// Knowledge — /api/kb/*
export const knowledgeApi = {
  capabilities: (): Promise<Record<string, boolean>> => api.request<Record<string, boolean>>('/kb/capabilities', {}, () => ({})),
  categories: (): Promise<JsonRecord[]> => api.request<JsonRecord[]>('/kb/categories', {}, () => [] as JsonRecord[]),
  documents: (category_id?: string): Promise<JsonRecord[]> => {
    const query = category_id ? `?category_id=${encodeURIComponent(category_id)}` : ''
    return api.request<JsonRecord[]>(`/kb/documents${query}`, {}, () => [] as JsonRecord[])
  },
  createCategory: (name: string, description = ''): Promise<JsonRecord> => api.request<JsonRecord>(
    '/kb/categories',
    { method: 'POST', body: JSON.stringify({ name, description }) },
    () => ({ id: `cat-${Date.now().toString(36)}`, name, description }),
  ),
  ingestDocument: (payload: { file_path: string; category_id: string; name: string; summary?: string }): Promise<JsonRecord> => api.request<JsonRecord>(
    '/kb/documents',
    { method: 'POST', body: JSON.stringify(payload) },
    () => ({ id: `doc-${Date.now().toString(36)}`, ...payload }),
  ),
  ingestText: (payload: { text: string; category_id: string; name: string; summary?: string }): Promise<JsonRecord> => api.request<JsonRecord>(
    '/kb/documents/text',
    { method: 'POST', body: JSON.stringify(payload) },
    () => ({ id: `doc-${Date.now().toString(36)}`, ...payload }),
  ),
  removeDocument: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(
    `/kb/documents/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
    () => ({ status: 'deleted' }),
  ),
  search: (q: string, top_k = 10, category_id?: string): Promise<{ hits: JsonRecord[]; degraded: boolean; capabilities: Record<string, boolean> }> => {
    const query = new URLSearchParams({ q, top_k: String(top_k) })
    if (category_id) query.set('category_id', category_id)
    return api.request<{ hits: JsonRecord[]; degraded: boolean; capabilities: Record<string, boolean> }>(
      `/kb/search?${query.toString()}`,
      {},
      () => ({ hits: [], degraded: false, capabilities: {} }),
    )
  },
  moveToMemory: (document_id: string, target_memory_category: string): Promise<{ document_id: string; moved_count: number }> => api.request<{ document_id: string; moved_count: number }>(
    `/kb/documents/${encodeURIComponent(document_id)}/move-to-memory`,
    { method: 'POST', body: JSON.stringify({ target_memory_category }) },
    () => ({ document_id, moved_count: 0 }),
  ),
}

// ---------------------------------------------------------------------------
// Memory — /api/memory/*
export interface MemoryPreferencesPayload {
  preferred_tags: string[]
  block_sources: string[]
  blocked_topics: string[]
  push_time: string
  importance_threshold: number
}

export const memoryApi = {
  preferences: (): Promise<MemoryPreferencesPayload> => api.request<MemoryPreferencesPayload>('/memory/preferences', {}, () => ({
    preferred_tags: [],
    block_sources: [],
    blocked_topics: [],
    push_time: '18:30',
    importance_threshold: 5,
  })),
  savePreferences: (prefs: MemoryPreferencesPayload): Promise<MemoryPreferencesPayload> => api.request<MemoryPreferencesPayload>(
    '/memory/preferences',
    { method: 'PUT', body: JSON.stringify(prefs) },
    () => prefs,
  ),
  list: (params: { category?: string; tag?: string; limit?: number } = {}): Promise<JsonRecord[]> => {
    const query = new URLSearchParams()
    if (params.category) query.set('category', params.category)
    if (params.tag) query.set('tag', params.tag)
    if (params.limit !== undefined) query.set('limit', String(params.limit))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return api.request<JsonRecord[]>(`/memory/entries${suffix}`, {}, () => [] as JsonRecord[])
  },
  search: (q: string, limit = 20): Promise<JsonRecord[]> => {
    const query = new URLSearchParams({ q, limit: String(limit) })
    return api.request<JsonRecord[]>(`/memory/entries/search?${query.toString()}`, {}, () => [] as JsonRecord[])
  },
  create: (payload: JsonRecord): Promise<{ id: string }> => api.request<{ id: string }>(
    '/memory/entries',
    { method: 'POST', body: JSON.stringify(payload) },
    () => ({ id: `mem-${Date.now().toString(36)}` }),
  ),
  remove: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(
    `/memory/entries/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
    () => ({ status: 'deleted' }),
  ),
  extract: (days = 30): Promise<{ extracted: unknown }> => api.request<{ extracted: unknown }>(
    '/memory/extract',
    { method: 'POST', body: JSON.stringify({ days }) },
    () => ({ extracted: null }),
  ),
}

// ---------------------------------------------------------------------------
// Settings — GET /api/settings · PUT /api/settings · POST /api/settings/providers/{id}/{models,test}
export interface SettingsPayloadRaw {
  ai_providers: JsonRecord[]
  publishers: JsonRecord[]
  http_proxy: string | null
  optional_dependencies: Record<string, boolean>
}

export const settingsApi = {
  get: (): Promise<SettingsPayloadRaw> => api.request<SettingsPayloadRaw>('/settings', {}, () => ({
    ai_providers: [],
    publishers: [],
    http_proxy: null,
    optional_dependencies: { opentelemetry: false, prometheus: false, vector_search: false },
  })),
  save: (payload: JsonRecord): Promise<JsonRecord> => api.request<JsonRecord>(
    '/settings',
    { method: 'PUT', body: JSON.stringify(payload) },
    () => payload,
  ),
  testProvider: (provider_id: string, payload: { base_url?: string; api_key?: string } = {}): Promise<{ provider_id: string; ok: true; model_count: number }> =>
    api.request<{ provider_id: string; ok: true; model_count: number }>(
      `/settings/providers/${encodeURIComponent(provider_id)}/test`,
      { method: 'POST', body: JSON.stringify(payload) },
      () => ({ provider_id, ok: true as const, model_count: 0 }),
    ),
  listProviderModels: (provider_id: string, payload: { base_url?: string; api_key?: string } = {}): Promise<{ provider_id: string; models: string[]; source: string; note: string | null }> =>
    api.request<{ provider_id: string; models: string[]; source: string; note: string | null }>(
      `/settings/providers/${encodeURIComponent(provider_id)}/models`,
      { method: 'POST', body: JSON.stringify(payload) },
      () => ({ provider_id, models: [], source: 'mock', note: null }),
    ),
}

// ---------------------------------------------------------------------------
// Skills — /api/skills/*
export const skillsApi = {
  list: (): Promise<JsonRecord[]> => api.request<JsonRecord[]>('/skills', {}, () => [] as JsonRecord[]),
  get: (id: string): Promise<JsonRecord> => api.request<JsonRecord>(`/skills/${encodeURIComponent(id)}`, {}, () => ({})),
  create: (payload: { id: string; frontmatter: JsonDict; instructions: string }): Promise<JsonRecord> =>
    api.request<JsonRecord>('/skills', { method: 'POST', body: JSON.stringify(payload) }, () => payload as unknown as JsonRecord),
  reload: (): Promise<{ loaded: number }> => api.request<{ loaded: number }>('/skills/reload', { method: 'POST' }, () => ({ loaded: 0 })),
  remove: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(
    `/skills/${encodeURIComponent(id)}`,
    { method: 'DELETE' },
    () => ({ status: 'deleted' }),
  ),
}

// ---------------------------------------------------------------------------
// Chat — /api/chat/* (admin only, see backend auth gate)
export interface ChatSession {
  id: string
  title: string
  created_at: number
  updated_at: number
  message_count: number
}

export interface ChatMessage {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: number
}

export const chatApi = {
  listSessions: (limit = 50): Promise<JsonRecord[]> => api.request<JsonRecord[]>(`/chat/sessions?limit=${limit}`, {}, () => [] as JsonRecord[]),
  createSession: (title = ''): Promise<JsonRecord> => api.request<JsonRecord>('/chat/sessions', { method: 'POST', body: JSON.stringify({ title }) }, () => ({ id: `s-${Date.now().toString(36)}`, title, message_count: 0 })),
  deleteSession: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(`/chat/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }, () => ({ status: 'deleted' })),
  listMessages: (session_id: string, limit = 200): Promise<JsonRecord[]> => api.request<JsonRecord[]>(`/chat/sessions/${encodeURIComponent(session_id)}/messages?limit=${limit}`, {}, () => [] as JsonRecord[]),
  sendMessage: (session_id: string, content: string): Promise<JsonRecord> => api.request<JsonRecord>(`/chat/sessions/${encodeURIComponent(session_id)}/messages`, { method: 'POST', body: JSON.stringify({ content }) }, () => ({ id: `m-${Date.now().toString(36)}`, role: 'assistant', content })),
}

// ---------------------------------------------------------------------------
// Agents & workflow runs — /api/agents/* and /api/workflows/{id}/run are SSE streams
// and need EventSource, not fetch.
export const agentsApi = {
  list: (): Promise<JsonRecord[]> => api.request<JsonRecord[]>('/agents', {}, () => [] as JsonRecord[]),
  create: (payload: JsonRecord): Promise<JsonRecord> => api.request<JsonRecord>('/agents', { method: 'POST', body: JSON.stringify(payload) }, () => payload),
  remove: (id: string): Promise<{ status: string }> => api.request<{ status: string }>(`/agents/${encodeURIComponent(id)}`, { method: 'DELETE' }, () => ({ status: 'deleted' })),
  approveToolCall: (tool_call: JsonRecord, ttl_seconds = 300): Promise<{ approval_token: string; expires_in: number }> =>
    api.request<{ approval_token: string; expires_in: number }>(
      '/agents/tools/approve',
      { method: 'POST', body: JSON.stringify({ tool_call, ttl_seconds }) },
      () => ({ approval_token: 'demo-token', expires_in: ttl_seconds }),
    ),
  runPath: (agent_id: string): string => `/agents/${encodeURIComponent(agent_id)}/run`,
}

export const workflowRunPath = (workflow_id: string): string => `/workflows/${encodeURIComponent(workflow_id)}/run`

// ---------------------------------------------------------------------------
// MCP / interop / digest
export const mcpApi = {
  listTools: (): Promise<JsonRecord[]> => api.request<JsonRecord[]>('/mcp/tools', {}, () => [] as JsonRecord[]),
  callTool: (tool_name: string, payload: JsonRecord): Promise<JsonRecord> => api.request<JsonRecord>(
    `/mcp/tools/${encodeURIComponent(tool_name)}/call`,
    { method: 'POST', body: JSON.stringify(payload) },
    () => ({}),
  ),
}

export const digestApi = {
  run: (payload: JsonRecord): Promise<JsonRecord> => api.request<JsonRecord>('/digest/run', { method: 'POST', body: JSON.stringify(payload) }, () => ({})),
  approve: (date: string, payload: JsonRecord = {}): Promise<JsonRecord> => api.request<JsonRecord>(`/digest/${encodeURIComponent(date)}/approve`, { method: 'POST', body: JSON.stringify(payload) }, () => ({})),
  reject: (date: string): Promise<{ status: string; date: string }> => api.request<{ status: string; date: string }>(`/digest/${encodeURIComponent(date)}/reject`, { method: 'POST' }, () => ({ status: 'rejected', date })),
}

export const curationApi = {
  summary: (from_date?: string, to_date?: string): Promise<JsonRecord> => {
    const query = new URLSearchParams()
    if (from_date) query.set('from_date', from_date)
    if (to_date) query.set('to_date', to_date)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return api.request<JsonRecord>(`/curation-evaluations/summary${suffix}`, {}, () => ({}))
  },
  list: (from_date?: string, to_date?: string, limit = 50): Promise<JsonRecord[]> => {
    const query = new URLSearchParams()
    if (from_date) query.set('from_date', from_date)
    if (to_date) query.set('to_date', to_date)
    if (limit) query.set('limit', String(limit))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return api.request<JsonRecord[]>(`/curation-evaluations${suffix}`, {}, () => [] as JsonRecord[])
  },
  statsByPeriod: (from_date?: string, to_date?: string): Promise<JsonRecord[]> => {
    const query = new URLSearchParams()
    if (from_date) query.set('from_date', from_date)
    if (to_date) query.set('to_date', to_date)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return api.request<JsonRecord[]>(`/curation-stats/by-period${suffix}`, {}, () => [] as JsonRecord[])
  },
  baseline: (): Promise<{ avg_f1: number | null }> => api.request<{ avg_f1: number | null }>('/curation-stats/baseline', {}, () => ({ avg_f1: null })),
}

export const workflowIterationsApi = {
  list: (params: { run_id?: string; step_id?: string; limit?: number } = {}): Promise<JsonRecord[]> => {
    const query = new URLSearchParams()
    if (params.run_id) query.set('run_id', params.run_id)
    if (params.step_id) query.set('step_id', params.step_id)
    if (params.limit !== undefined) query.set('limit', String(params.limit))
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return api.request<JsonRecord[]>(`/workflow-iterations${suffix}`, {}, () => [] as JsonRecord[])
  },
}

export const dailyNewsApi = {
  read: (date?: string, limit = 31): Promise<{ archives: JsonRecord[]; digest: JsonRecord | null }> => {
    const query = new URLSearchParams({ limit: String(limit) })
    if (date) query.set('date', date)
    return api.request<{ archives: JsonRecord[]; digest: JsonRecord | null }>(`/daily-news?${query.toString()}`, {}, () => ({ archives: [], digest: null }))
  },
}