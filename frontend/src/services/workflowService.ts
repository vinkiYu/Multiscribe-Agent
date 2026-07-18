import { request } from './api'

export interface WorkflowStep {
  id: string
  name?: string
  type: 'agent' | 'workflow'
  target_id: string
  depends_on?: string[]
}

export interface WorkflowDefinition {
  id: string
  name: string
  description?: string
  steps: WorkflowStep[]
}

export async function listWorkflows(): Promise<WorkflowDefinition[]> {
  return await request<WorkflowDefinition[]>('/api/workflows')
}

export async function saveWorkflow(wf: WorkflowDefinition): Promise<WorkflowDefinition> {
  return await request<WorkflowDefinition>('/api/workflows', {
    method: 'POST',
    body: JSON.stringify(wf),
  })
}

export async function deleteWorkflow(workflowId: string): Promise<void> {
  await request(`/api/workflows/${encodeURIComponent(workflowId)}`, {
    method: 'DELETE',
  })
}