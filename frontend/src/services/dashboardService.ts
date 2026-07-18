import { request } from './api'

export interface DashboardStats {
  source_count: number
  scheduled_tasks: number
}

export interface TaskLog {
  id: number
  task_id: string
  task_name: string
  start_time: string
  end_time?: string | null
  duration?: number | null
  status: 'success' | 'error' | 'running' | 'pending'
  progress?: number | null
  message?: string | null
  result_count?: number | null
}

export async function getStats(): Promise<DashboardStats> {
  return await request<DashboardStats>('/api/dashboard/stats')
}

export async function getRecentLogs(limit = 20): Promise<TaskLog[]> {
  return await request<TaskLog[]>(`/api/dashboard/logs?limit=${limit}`)
}

export async function triggerIngestion(payload: {
  adapter_id?: string
  config?: Record<string, unknown>
  adapter_configs?: Array<{
    adapter_id: string
    config: Record<string, unknown>
  }>
}): Promise<{ result_count?: number; results?: unknown[] }> {
  return await request<{ result_count?: number; results?: unknown[] }>(
    '/api/dashboard/ingest',
    { method: 'POST', body: JSON.stringify(payload) },
  )
}