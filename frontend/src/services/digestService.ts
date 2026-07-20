import { request } from './api'

export const DEFAULT_CURATION_AGENT_ID = 'default-curation-agent'

export interface DigestTargetResult {
  target_id: string
  status: 'success' | 'error' | 'pending'
  items_count?: number
  message?: string
  response?: unknown
  error?: string
}

export type DigestTargetMap = Record<string, Omit<DigestTargetResult, 'target_id'>>

export interface DigestResult {
  status?: string
  curated?: Array<{
    id?: string
    title?: string
    summary?: string
    score?: number
    [key: string]: unknown
  }>
  targets?: DigestTargetMap | DigestTargetResult[]
  started_at?: string
  finished_at?: string
  [key: string]: unknown
}

export async function runDigest(
  config: Record<string, unknown>,
): Promise<DigestResult> {
  return await request<DigestResult>('/api/digest/run', {
    method: 'POST',
    body: JSON.stringify(config),
  })
}
