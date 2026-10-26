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
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') {
        detail = body.detail
      } else if (Array.isArray(body.detail)) {
        // FastAPI validation errors: surface the first message instead of "[object Object]".
        detail = body.detail
          .map((item) => {
            if (item && typeof item === 'object' && 'msg' in item) {
              const entry = item as { msg?: string; loc?: unknown[] }
              const where = Array.isArray(entry.loc) ? entry.loc.join('.') : ''
              return where ? `${where}: ${entry.msg ?? ''}` : String(entry.msg ?? '')
            }
            return JSON.stringify(item)
          })
          .join('; ')
      }
    } catch {
      // Keep the status text when the body is not JSON.
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) {
    // No content: deleting a document succeeds without a body.
    return undefined as T
  }

  return (await response.json()) as T
}

/** Convenience wrapper for JSON requests with a method and a body. */
export function sendJson<T>(method: string, path: string, body?: unknown): Promise<T> {
  return apiJson<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body)
  })
}
