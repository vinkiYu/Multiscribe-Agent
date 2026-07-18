import { request } from './api'

export interface DigestTargetResult {
  target_id: string
  status: 'success' | 'error' | 'pending'
  items_count?: number
  message?: string
}

export interface DigestResult {
  status?: string
  curated?: Array<{
    id?: string
    title?: string
    summary?: string
    score?: number
    [key: string]: unknown
  }>
  targets?: DigestTargetResult[]
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