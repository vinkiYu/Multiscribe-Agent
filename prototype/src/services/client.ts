/// <reference types="vite/client" />
// Real API client with mock fallback + 401 handling.
// All endpoints below MUST stay aligned with
//   F:\software\Multiscribe\MultiscribeAgent-main\src\multiscribe_agent\api\routes

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

// CSRF: the backend issues `multiscribe_csrf` (non-HttpOnly) cookies. For
// state-changing requests, the browser must echo the cookie value back via
// the `X-CSRF-Token` header (see multiscribe_agent/api/middleware/csrf.py).
// `Authorization: Bearer ...` requests are exempt, so when a token is
// present the header is enough on its own.
function csrfHeaders(headers: Record<string, string> = {}): Record<string, string> {
  if (typeof document === 'undefined') return headers
  const match = document.cookie.split('; ').find((row) => row.startsWith('multiscribe_csrf='))
  if (!match) return headers
  const token = decodeURIComponent(match.split('=')[1] ?? '')
  if (!token) return headers
  return { ...headers, 'X-CSRF-Token': token }
}

function clearToken(): void {
  try { window.localStorage.removeItem('multiscribe_token') } catch { /* noop */ }
}

async function request<T>(path: string, init: RequestInit = {}, fallback?: () => T | Promise<T>): Promise<T> {
  const baseHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...authHeader(),
  }
  const initHeaders = init.headers
  if (initHeaders) {
    if (initHeaders instanceof Headers) {
      initHeaders.forEach((value, key) => { baseHeaders[key] = value })
    } else if (Array.isArray(initHeaders)) {
      for (const [key, value] of initHeaders) baseHeaders[key] = String(value)
    } else {
      for (const [key, value] of Object.entries(initHeaders)) baseHeaders[key] = String(value)
    }
  }
  // For non-GET requests, also send the CSRF token (no-op when the user is
  // already authenticated because the bearer header exempts us from the
  // CSRF middleware check, but it keeps the front-end compatible with
  // anonymous writes during the cold-start window).
  const method = (init.method ?? 'GET').toUpperCase()
  const withCsrf = method === 'GET' ? baseHeaders : csrfHeaders(baseHeaders)
  try {
    const response = await fetch(`${baseUrl}${path}`, { ...init, headers: withCsrf })
    if (response.status === 401) {
      clearToken()
      emitUnauthorized()
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
