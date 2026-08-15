// Domain types — align with backend API contracts.
// Reference: F:\software\Multiscribe\MultiscribeAgent-main\src\multiscribe_agent\api\routes

export interface SkillEntry {
  id: string
  name: string
  description: string
  instructions: string
  is_builtin: boolean
  frontmatter: {
    name: string
    description: string
    bins: string[]
  }
  dir_path?: string | null
  files: string[]
}

// Backend GET /api/dashboard/stats returns { source_count, scheduled_tasks }.
// The frontend keeps a richer in-memory model derived from /api/dashboard/overview.
export interface DashboardStats {
  source_count: number
  scheduled_tasks: number
  todayRuns: number
  nextRunAt: string
  pendingCount: number
  collectedCount: number
  curatedCount: number
  generatedCount: number
  publishedCount: number
}

// task_logs table row (snake_case) — see multiscribe_agent/domain/models.py:TaskLog
export interface TaskLog {
  id?: string | null
  task_id: string
  task_name: string
  start_time: string | null
  end_time?: string | null
  duration_ms?: number | null
  status: 'running' | 'success' | 'error' | 'interrupted' | 'skipped'
  progress?: number | null
  message?: string | null
  result_count?: number | null
}

// usage_by_model row + iteration row + evaluation aggregates.
export interface OperationsOverview {
  usage: {
    date: string
    input_tokens: number
    output_tokens: number
    total_tokens: number
    llm_calls: number
    task_count: number
  }
  cost_usd: number
  usage_by_model: Array<{
    date: string
    model_name: string
    input_tokens: number
    output_tokens: number
    total_tokens: number
    llm_calls: number
    cost_usd: number
  }>
  publish: Record<string, unknown>
  iterations: Array<{
    workflow_run_id: string
    step_id: string
    round: number
    score: number | null
    converged: boolean
    reason: string
  }>
  evaluation: {
    today_summary: Record<string, unknown>
    recent: Array<Record<string, unknown>>
  }
  task_logs: TaskLog[]
}

// alert_history row
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
  acknowledged_at: string | null
  metadata: Record<string, unknown>
}

// adapter_health.AdapterHealth.to_dict()
export interface AdapterHealth {
  adapter_id: string
  consecutive_failures: number
  disabled: boolean
  last_status: string
  last_error: string | null
  last_run_at: string | null
}

export type SourceType = 'rss' | 'github_trending' | 'follow_opml' | 'ai_search' | string

// AdapterConfig model_dump
export interface SourceEntry {
  id: string
  type: SourceType
  enabled: boolean
  config: Record<string, unknown>
}

// ScheduleTask.model_dump
export interface ScheduleTask {
  id: string
  name: string
  task_type: 'full_ingestion' | 'adapter' | 'agent_summary' | 'agent_deal' | 'daily_digest' | string
  cron: string
  enabled: boolean
  config: Record<string, unknown>
  last_run?: string | null
  last_status?: string | null
  last_error?: string | null
}

// WorkflowDefinition.model_dump
export interface WorkflowStep {
  id: string
  name: string
  step_type: 'agent' | 'workflow'
  agent_id?: string | null
  workflow_id?: string | null
  input_map?: Record<string, string> | null
  next_step_id?: string | null
  next_step_ids?: string[] | null
  enabled: boolean
  config: Record<string, unknown>
  max_iterations?: number | null
  exit_condition?: string | null
}

export interface WorkflowSummary {
  id: string
  name: string
  description: string
  steps: WorkflowStep[]
}

export type ContentStatus = 'pending' | 'curated' | 'ignored' | 'published' | string

// UnifiedData.model_dump
export interface ContentItem {
  id: string
  title: string
  url: string
  description: string
  published_date: string
  ingestion_date: string | null
  source: string
  category: string
  author?: string | null
  status?: string | null
  metadata: Record<string, unknown>
}

export type ChannelType = string

// PublisherConfig.model_dump (config keys may be redacted as "********")
export interface PublishChannel {
  id: string
  type: ChannelType
  enabled: boolean
  config: Record<string, unknown>
}

// PublishRecord row from publish_history repository
export interface PublishRecord {
  id: string
  publisher_id: string
  status: string
  title: string
  content_preview?: string | null
  result_data?: Record<string, unknown> | null
  error_message?: string | null
  published_at: string
  adapter_name?: string | null
}

// /api/publish-history response wrapper
export interface PublishHistoryPage {
  records: PublishRecord[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

// KBCategory.model_dump
export interface KnowledgeCategory {
  id: string
  name: string
  description: string
  document_count: number
  last_updated_at: number
}

// KBDocument.model_dump
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
  metadata: Record<string, unknown>
}

// MemoryEntry.model_dump
export interface MemoryEntry {
  id: string
  content: string
  importance: number
  tags: string[]
  created_at: number
  agent_id?: string | null
  metadata: Record<string, unknown>
  category?: string
}

export interface MemoryPreferences {
  preferred_tags: string[]
  block_sources: string[]
  blocked_topics: string[]
  push_time: string
  importance_threshold: number
}

// ProviderConfig.model_dump (api_key masked as "********" on read)
export interface ModelProvider {
  id: string
  name: string
  type: 'openai' | 'anthropic' | 'google' | 'ollama' | string
  enabled: boolean
  api_key: string
  base_url: string
  use_proxy: boolean
  models: string[]
  context_window_tokens: Record<string, number>
  default_output_tokens: Record<string, number>
}

// Settings GET /api/settings response shape
export interface SettingsPayload {
  providers: ModelProvider[]
  publishers: PublishChannel[]
  sources?: Array<Record<string, unknown>>
  plugins?: Array<Record<string, unknown>>
  system?: Array<Record<string, unknown>>
  http_proxy: string | null
  optional_dependencies: {
    opentelemetry: boolean
    prometheus: boolean
    vector_search: boolean
  }
}