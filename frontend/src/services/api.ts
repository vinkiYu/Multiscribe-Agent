/**
 * API request wrapper with JWT bearer token injection and 401 handling.
 */
const TOKEN_KEY = 'multiscribe_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  payload: unknown
  constructor(message: string, status: number, payload?: unknown) {
    super(message)
    this.status = status
    this.payload = payload
  }
}

export async function request<T = unknown>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...((options.headers as Record<string, string>) ?? {}),
  }

  if (options.body && !headers['Content-Type'] && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(url, { ...options, headers })

  if (response.status === 401 && !url.endsWith('/api/login')) {
    clearToken()
    if (!window.location.hash.startsWith('#/login')) {
      window.location.hash = '#/login'
    }
    throw new ApiError('未授权', 401)
  }

  if (!response.ok) {
    let payload: unknown
    try {
      payload = await response.json()
    } catch {
      payload = { error: '请求失败' }
    }
    const message =
      (payload as { error?: string }).error ??
      (payload as { message?: string }).message ??
      '请求失败'
    throw new ApiError(message, response.status, payload)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}