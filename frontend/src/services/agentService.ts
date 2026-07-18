import { request, getToken } from './api'

export interface AgentDefinition {
  id: string
  name: string
  description?: string
  system_prompt: string
  provider_id: string
  model: string
  temperature?: number
  tool_ids?: string[]
  skill_ids?: string[]
  mcp_server_ids?: string[]
  streaming?: boolean
  category?: string | null
  is_hidden?: boolean
}

export async function listAgents(): Promise<AgentDefinition[]> {
  return await request<AgentDefinition[]>('/api/agents')
}

export async function saveAgent(agent: AgentDefinition): Promise<AgentDefinition> {
  return await request<AgentDefinition>('/api/agents', {
    method: 'POST',
    body: JSON.stringify(agent),
  })
}

export async function deleteAgent(agentId: string): Promise<void> {
  await request(`/api/agents/${encodeURIComponent(agentId)}`, {
    method: 'DELETE',
  })
}

export async function* runAgent(
  agentId: string,
  input: string,
): AsyncGenerator<{ event: string; data: string }> {
  const token = getToken()
  const response = await fetch(
    `/api/agents/${encodeURIComponent(agentId)}/run`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ input }),
    },
  )
  if (!response.ok || !response.body) {
    throw new Error(`agent run failed: ${response.status}`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    let event = 'message'
    for (const line of lines) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:'))
        yield { event, data: line.slice(5).trim() }
    }
  }
}