import { request, setToken, clearToken } from './api'

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  must_change_password?: boolean
}

export async function login(password: string): Promise<LoginResponse> {
  const data = await request<LoginResponse>('/api/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })
  setToken(data.access_token)
  return data
}

export function logout(): void {
  clearToken()
}