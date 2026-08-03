export type ApiErrorKind = 'unauthenticated' | 'unavailable' | 'network' | 'unknown'

export class ApiError extends Error {
  readonly kind: ApiErrorKind

  constructor(kind: ApiErrorKind, message: string) {
    super(message)
    this.kind = kind
  }
}

export interface DashboardStats {
  source_count: number
  scheduled_tasks: number
}

export interface TaskLog {
  id: number
  task_type?: string
  task_name?: string
  status?: string
  message?: string
  created_at?: string
  started_at?: string
  finished_at?: string
}

export interface DailyUsageRecord { date: string; input_tokens: number; output_tokens: number; total_tokens: number; llm_calls: number; task_count: number }
export interface DailyUsageByModelRecord { date: string; model_name: string; input_tokens: number; output_tokens: number; total_tokens: number; llm_calls: number; cost_usd: number }
export interface PublishSummary { total: number; success: number; error: number }
export interface IterationRecord { workflow_run_id: string; step_id: string; round: number; score: number | null; converged: boolean; reason: string }
export interface CurationEvaluationRecord { workflow_run_id: string; date: string; recorded_at: number; rounds: number; converged: boolean; exit_reason: string; final_score: number | null; score_delta: number | null; avg_iter_score: number | null; result_count: number; usage: Omit<DailyUsageRecord, 'date' | 'task_count'> }
export interface CurationEvaluationsSummary { total_runs: number; converged_runs: number; avg_score: number | null; avg_final_score: number | null; avg_rounds: number; converge_rate: number; per_reason_counts: Record<string, number> }
export interface DailyCurationStat { date: string; final_score: number | null; result_count: number | null; total_scanned: number | null; efficiency: number | null; converged: boolean; exit_reason: string; rounds: number }
export interface OperationsOverview { usage: DailyUsageRecord; cost_usd: number; usage_by_model: DailyUsageByModelRecord[]; publish: PublishSummary; iterations: IterationRecord[]; evaluation: { today_summary: CurationEvaluationsSummary; recent: CurationEvaluationRecord[] }; task_logs: TaskLog[] }

export interface WorkflowSummary {
  id: string
  name: string
  description: string
  steps: WorkflowStep[]
}

export interface WorkflowStep {
  id: string
  name: string
  step_type: 'agent' | 'workflow'
  agent_id?: string | null
  workflow_id?: string | null
  input_map?: Record<string, string> | null
  next_step_id?: string | null
  next_step_ids?: string[] | null
  enabled?: boolean
  max_iterations?: number | null
  exit_condition?: string | null
}

export interface AgentSummary { id: string; name: string; description: string }
export interface WorkflowEvent { type: string; data: Record<string, unknown> }

export interface ScheduleTask {
  id: string
  name: string
  task_type: string
  cron: string
  enabled: boolean
  config: Record<string, unknown>
  last_run?: string | null
  last_status?: string | null
  last_error?: string | null
}

export interface DailyNewsItem {
  title: string
  summary: string
  url: string
  source: string
  score: number | null
  image_url: string | null
    video_url: string | null
    published_at: string | null
    section: string
    tags: string[]
}

export interface DailyDigest {
  date: string
  title: string
  summary: string
  items: DailyNewsItem[]
  total_scanned: number
  updated_at: string
}

export interface DailyNewsResponse {
  archives: Array<{ date: string; title: string; item_count: number; updated_at: string }>
  digest: DailyDigest | null
}

export interface SourceData {
  id: string
  title: string
  url: string
  description: string
  source: string
  category: string
  published_date: string
  ingestion_date: string
  adapter_name: string
}

export interface PublishHistoryRecord {
  id: string
  publisher_id: string
  status: string
  title: string
  content_preview: string
  result_data: Record<string, unknown>
  error_message: string | null
  published_at: string
  adapter_name: string | null
}

export interface PublishHistoryResponse {
  records: PublishHistoryRecord[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface KnowledgeCategory {
  id: string
  name: string
  description: string
  document_count: number
  last_updated_at: number
}

export interface KnowledgeDocument {
  id: string
  category_id: string
  name: string
  file_name: string
  type: string
  summary: string
  chunk_count: number
  created_at: number
  updated_at: number
}

export interface KnowledgeCapabilities {
  fts: boolean
  vector: boolean
  degraded: boolean
}
export interface KnowledgeSearchHit { chunk_id: string; document_id: string; content: string; score: number; source: string }
export interface KnowledgeSearchResponse { hits: KnowledgeSearchHit[]; degraded: boolean; capabilities: KnowledgeCapabilities }

export interface MemoryEntry {
  id: string
  content: string
  importance: number
  tags: string[]
  created_at: number
  agent_id?: string | null
  metadata?: Record<string, unknown>
}

export interface MemoryPreferences {
  preferred_tags: string[]
  block_sources: string[]
  blocked_topics: string[]
  push_time: string
  importance_threshold: number
}

export interface SkillEntry {
  id: string
  name: string
  description: string
  is_builtin: boolean
  files: string[]
}

export interface SourceConfigField { key: string; label: string; type: 'text' | 'password' | 'textarea' | 'select' | 'boolean' | 'number' | 'url'; required: boolean; default: unknown; options?: string[] | null; placeholder: string; help_text: string; scope: 'adapter' | 'item' }
export interface SourceAdapterMetadata { id: string; type: string; name: string; description: string; icon: string; config_fields: SourceConfigField[]; is_builtin: boolean }
export interface SourceConfiguration { id: string; type: string; enabled: boolean; config: Record<string, unknown> }
export interface SourcesResponse { sources: SourceConfiguration[]; available_adapters: SourceAdapterMetadata[] }
export interface AdapterHealth {
  adapter_id: string
  consecutive_failures: number
  disabled: boolean
  last_status: string
  last_error: string | null
  last_run_at: string | null
}
export interface AlertRecord {
  id: string
  rule_name: string
  metric: string
  threshold: number
  value: number
  description: string
  fired_at: number
  acknowledged: boolean
  acknowledged_by: string | null
  acknowledged_at: number | null
  metadata: Record<string, unknown>
}
export interface SettingsProvider { id: string; name: string; type: string; enabled: boolean; api_key: string; base_url: string; models: string[]; context_window_tokens: Record<string, number>; default_output_tokens: Record<string, number> }
export interface SettingsPublisher { id: string; type: string; enabled: boolean; config: Record<string, unknown> }
export interface RuntimeSettings { ai_providers: SettingsProvider[]; publishers: SettingsPublisher[]; http_proxy: string; optional_dependencies: Record<string, boolean> }
export interface ProviderModelSync { provider_id: string; models: string[]; source: 'remote' | 'catalog'; note: string | null }
export interface ProviderConnectionTest { provider_id: string; ok: boolean; model_count: number }

interface LoginResponse {
  access_token: string
  token_type: string
  must_change_password: boolean
}

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

async function errorFor(response: Response): Promise<ApiError> {
  if (response.status === 401) return new ApiError('unauthenticated', '登录已失效，请重新登录后再试。')
  if (response.status === 503) return new ApiError('unavailable', '服务正在启动或暂不可用，请稍后刷新。')

  let detail = ''
  try {
    const body = await response.json() as { detail?: unknown }
    detail = typeof body.detail === 'string' ? body.detail : ''
  } catch {
    // A non-JSON response still gets a useful status-based error below.
  }
  return new ApiError('unknown', detail || `请求失败，状态码 ${response.status}。`)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = window.localStorage.getItem('multiscribe_token')
  if (!token) throw new ApiError('unauthenticated', '请先登录本地服务，再查看实时数据。')

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, ...init?.headers },
    })
  } catch {
    throw new ApiError('network', '无法连接本地服务，请确认 Multiscribe 已启动。')
  }

  if (!response.ok) {
    const error = await errorFor(response)
    if (error.kind === 'unauthenticated') {
      window.localStorage.removeItem('multiscribe_token')
      window.location.replace('./login.html')
    }
    throw error
  }
  return response.json() as Promise<T>
}

async function publicRequest<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`)
  } catch {
    throw new ApiError('network', '无法连接本地服务，请确认 Multiscribe 已启动。')
  }
  if (!response.ok) throw await errorFor(response)
  return response.json() as Promise<T>
}

export const dashboardApi = {
  getStats: (): Promise<DashboardStats> => request<DashboardStats>('/dashboard/stats'),
  getLogs: (): Promise<TaskLog[]> => request<TaskLog[]>('/dashboard/logs?limit=8'),
}

export const operationsApi = {
  getOverview: (): Promise<OperationsOverview> => request<OperationsOverview>('/dashboard/overview'),
}

export const alertsApi = {
  list: (options?: { limit?: number; acknowledged?: boolean }): Promise<AlertRecord[]> => {
    const params = new URLSearchParams()
    if (options?.limit !== undefined) params.set('limit', String(options.limit))
    if (options?.acknowledged !== undefined) params.set('acknowledged', String(options.acknowledged))
    const query = params.toString()
    return request<AlertRecord[]>(`/alerts${query ? `?${query}` : ''}`)
  },
}

export const curationStatsApi = {
  getByPeriod: (fromDate?: string, toDate?: string): Promise<DailyCurationStat[]> => {
    const params = new URLSearchParams()
    if (fromDate) params.set('from_date', fromDate)
    if (toDate) params.set('to_date', toDate)
    const query = params.toString()
    return request<DailyCurationStat[]>(`/curation-stats/by-period${query ? `?${query}` : ''}`)
  },
}

export const workflowsApi = {
  list: (): Promise<WorkflowSummary[]> => request<WorkflowSummary[]>('/workflows'),
  save: (workflow: WorkflowSummary): Promise<WorkflowSummary> => request<WorkflowSummary>('/workflows', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(workflow) }),
  remove: (workflowId: string): Promise<{ status: string }> => request<{ status: string }>(`/workflows/${encodeURIComponent(workflowId)}`, { method: 'DELETE' }),
  run: async (workflowId: string, input: string, onEvent: (event: WorkflowEvent) => void): Promise<void> => {
    const token = window.localStorage.getItem('multiscribe_token')
    const response = await fetch(`${API_BASE}/workflows/${encodeURIComponent(workflowId)}/run`, { method: 'POST', headers: { Authorization: `Bearer ${token ?? ''}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ input }) })
    if (!response.ok || !response.body) {
      const error = await errorFor(response)
      if (error.kind === 'unauthenticated') {
        window.localStorage.removeItem('multiscribe_token')
        window.location.replace('./login.html')
      }
      throw error
    }
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''
    while (true) { const chunk = await reader.read(); if (chunk.done) break; buffer += decoder.decode(chunk.value, { stream: true }); const blocks = buffer.split(/\r?\n\r?\n/); buffer = blocks.pop() ?? ''; for (const block of blocks) { const event = block.match(/^event:\s*(.+)$/m)?.[1]; const data = block.match(/^data:\s*(.+)$/m)?.[1]; if (event && data) { try { onEvent({ type: event, data: JSON.parse(data) as Record<string, unknown> }) } catch { onEvent({ type: event, data: { message: data } }) } } } }
  },
}

export const agentsApi = { list: (): Promise<AgentSummary[]> => request<AgentSummary[]>('/agents') }

export const schedulesApi = {
  list: (): Promise<ScheduleTask[]> => request<ScheduleTask[]>('/schedules'),
  create: (task: ScheduleTask): Promise<ScheduleTask> => request<ScheduleTask>('/schedules', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(task) }),
  remove: (id: string): Promise<{ status: string }> => request(`/schedules/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  run: (id: string): Promise<{ status: string }> => request(`/schedules/${id}/run`, { method: 'POST' }),
}

export const dailyNewsApi = {
  latest: (): Promise<DailyNewsResponse> => publicRequest<DailyNewsResponse>('/daily-news?limit=31'),
  byDate: (date: string): Promise<DailyNewsResponse> => publicRequest<DailyNewsResponse>(`/daily-news?date=${encodeURIComponent(date)}&limit=31`),
}

export const publishHistoryApi = {
  list: (options?: { limit?: number; offset?: number }): Promise<PublishHistoryResponse> => {
    const limit = options?.limit ?? 50
    const offset = options?.offset ?? 0
    return request<PublishHistoryResponse>(`/publish-history?limit=${limit}&offset=${offset}`)
  },
}

export const knowledgeApi = {
  capabilities: (): Promise<KnowledgeCapabilities> => request<KnowledgeCapabilities>('/kb/capabilities'),
  categories: (): Promise<KnowledgeCategory[]> => request<KnowledgeCategory[]>('/kb/categories'),
  documents: (): Promise<KnowledgeDocument[]> => request<KnowledgeDocument[]>('/kb/documents'),
  createCategory: (payload: { name: string; description?: string }): Promise<KnowledgeCategory> => request<KnowledgeCategory>('/kb/categories', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  ingestText: (payload: { name: string; category_id: string; text: string; summary?: string }): Promise<KnowledgeDocument> => request<KnowledgeDocument>('/kb/documents/text', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  remove: (documentId: string): Promise<{ status: string }> => request<{ status: string }>(`/kb/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' }),
  search: (query: string, categoryId?: string): Promise<KnowledgeSearchResponse> => request<KnowledgeSearchResponse>(`/kb/search?q=${encodeURIComponent(query)}${categoryId ? `&category_id=${encodeURIComponent(categoryId)}` : ''}`),
}

export const memoryApi = {
  entries: (): Promise<MemoryEntry[]> => request<MemoryEntry[]>('/memory/entries'),
  preferences: (): Promise<MemoryPreferences> => request<MemoryPreferences>('/memory/preferences'),
  savePreferences: (payload: MemoryPreferences): Promise<MemoryPreferences> => request<MemoryPreferences>('/memory/preferences', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  search: (query: string): Promise<MemoryEntry[]> => request<MemoryEntry[]>(`/memory/entries/search?q=${encodeURIComponent(query)}`),
  create: (payload: { content: string; importance: number; tags: string[] }): Promise<{ id: string }> => request<{ id: string }>('/memory/entries', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  remove: (entryId: string): Promise<{ status: string }> => request<{ status: string }>(`/memory/entries/${encodeURIComponent(entryId)}`, { method: 'DELETE' }),
  extractFromHistory: (days: number): Promise<{ extracted: number }> => request<{ extracted: number }>('/memory/extract', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ days }) }),
}

export const skillsApi = {
  list: (): Promise<SkillEntry[]> => request<SkillEntry[]>('/skills'),
  reload: (): Promise<{ loaded: number }> => request('/skills/reload', { method: 'POST' }),
}

export const sourcesApi = {
  list: (): Promise<SourcesResponse> => request<SourcesResponse>('/sources'),
  save: (id: string, source: Omit<SourceConfiguration, 'id'>): Promise<SourceConfiguration> => request<SourceConfiguration>(`/sources/${encodeURIComponent(id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(source) }),
}

export const sourceDataApi = {
  search: (query: string, limit = 20): Promise<SourceData[]> => request<SourceData[]>(`/source-data/search?q=${encodeURIComponent(query)}&limit=${limit}`),
}

export const adapterHealthApi = {
  list: (): Promise<AdapterHealth[]> => request<AdapterHealth[]>('/adapter-health'),
  enable: (id: string): Promise<AdapterHealth> => request<AdapterHealth>(`/adapter-health/${encodeURIComponent(id)}/enable`, { method: 'POST' }),
  disable: (id: string): Promise<AdapterHealth> => request<AdapterHealth>(`/adapter-health/${encodeURIComponent(id)}/disable`, { method: 'POST' }),
}

export const settingsApi = {
  get: (): Promise<RuntimeSettings> => request<RuntimeSettings>('/settings'),
  save: (settings: Partial<RuntimeSettings>): Promise<RuntimeSettings> => request<RuntimeSettings>('/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) }),
  syncModels: (provider: Pick<SettingsProvider, 'id' | 'base_url' | 'api_key'>): Promise<ProviderModelSync> => request<ProviderModelSync>(`/settings/providers/${encodeURIComponent(provider.id)}/models`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: provider.base_url, api_key: provider.api_key }) }),
  testConnection: (provider: Pick<SettingsProvider, 'id' | 'base_url' | 'api_key'>): Promise<ProviderConnectionTest> => request<ProviderConnectionTest>(`/settings/providers/${encodeURIComponent(provider.id)}/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ base_url: provider.base_url, api_key: provider.api_key }) }),
}

export async function loginApi(password: string): Promise<LoginResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })
  } catch {
    throw new Error('无法连接本地服务，请确认 Multiscribe 已启动。')
  }

  if (response.status === 401) throw new Error('密码不正确，请重新输入。')
  if (!response.ok) throw new Error('登录服务暂时不可用，请稍后重试。')
  return response.json() as Promise<LoginResponse>
}
