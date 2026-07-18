import { request } from './api'

export interface ScheduleTask {
  id: string
  name: string
  task_type: string
  cron: string
  enabled: boolean
  config: Record<string, unknown>
}

export async function listSchedules(): Promise<ScheduleTask[]> {
  return await request<ScheduleTask[]>('/api/schedules')
}

export async function saveSchedule(task: ScheduleTask): Promise<ScheduleTask> {
  return await request<ScheduleTask>('/api/schedules', {
    method: 'POST',
    body: JSON.stringify(task),
  })
}

export async function deleteSchedule(taskId: string): Promise<void> {
  await request(`/api/schedules/${encodeURIComponent(taskId)}`, {
    method: 'DELETE',
  })
}

export async function runScheduleNow(taskId: string): Promise<void> {
  await request(`/api/schedules/${encodeURIComponent(taskId)}/run`, {
    method: 'POST',
  })
}