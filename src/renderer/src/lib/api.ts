import type { HealthResponse } from './api-types'

export type { HealthResponse }

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/**
 * Calls the local service through the same-origin `/api` proxy.
 * `path` is relative to `/api` (use `/health`, not `/api/health`).
 */
export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) }
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // Keep the status text when the body is not JSON.
    }
    throw new ApiError(response.status, detail)
  }

  return (await response.json()) as T
}
