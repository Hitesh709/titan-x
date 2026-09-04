const DEFAULT_API_BASE = "https://titan-x-api-oregon.onrender.com/api/v1"
const configuredApiBase = process.env.NEXT_PUBLIC_API_URL?.trim()
const API_BASE = (configuredApiBase || DEFAULT_API_BASE).replace(/\/+$/, "")

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
  skipAuthRefresh?: boolean
}

interface RefreshResponse {
  access_token: string
  refresh_token: string
  token_type?: string
}

class ApiClient {
  private token: string | null = null
  private refreshToken: string | null = null
  private refreshPromise: Promise<string | null> | null = null

  setToken(token: string | null) {
    this.token = token
    if (typeof window !== "undefined") {
      if (token) localStorage.setItem("titan_token", token)
      else localStorage.removeItem("titan_token")
    }
  }

  setRefreshToken(token: string | null) {
    this.refreshToken = token
    if (typeof window !== "undefined") {
      if (token) localStorage.setItem("titan_refresh_token", token)
      else localStorage.removeItem("titan_refresh_token")
    }
  }

  getToken(): string | null {
    if (this.token) return this.token
    if (typeof window !== "undefined") {
      this.token = localStorage.getItem("titan_token")
    }
    return this.token
  }

  getRefreshToken(): string | null {
    if (this.refreshToken) return this.refreshToken
    if (typeof window !== "undefined") {
      this.refreshToken = localStorage.getItem("titan_refresh_token")
    }
    return this.refreshToken
  }

  clearTokens() {
    this.token = null
    this.refreshToken = null
    if (typeof window !== "undefined") {
      localStorage.removeItem("titan_token")
      localStorage.removeItem("titan_refresh_token")
    }
  }

  async refreshAccessToken(): Promise<string | null> {
    const storedRefresh = this.getRefreshToken()
    if (!storedRefresh) return null
    if (this.refreshPromise) return this.refreshPromise

    this.refreshPromise = (async () => {
      try {
        const response = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: storedRefresh }),
        })

        if (!response.ok) {
          this.clearTokens()
          return null
        }

        const data = (await response.json()) as RefreshResponse
        if (!data.access_token || !data.refresh_token) {
          this.clearTokens()
          return null
        }

        this.setToken(data.access_token)
        this.setRefreshToken(data.refresh_token)
        return data.access_token
      } catch {
        return null
      } finally {
        this.refreshPromise = null
      }
    })()

    return this.refreshPromise
  }

  async request<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { method = "GET", body, headers = {}, skipAuthRefresh = false } = options
    const token = this.getToken()

    const h: Record<string, string> = {
      "Content-Type": "application/json",
      ...headers,
    }

    if (token) h["Authorization"] = `Bearer ${token}`

    const normalizedEndpoint = endpoint.startsWith("/") ? endpoint : `/${endpoint}`
    const res = await fetch(`${API_BASE}${normalizedEndpoint}`, {
      method,
      credentials: "include",
      headers: h,
      body: body ? JSON.stringify(body) : undefined,
    })

    if (res.status === 401 && !skipAuthRefresh && normalizedEndpoint !== "/auth/refresh") {
      const newToken = await this.refreshAccessToken()
      if (newToken) {
        return this.request<T>(endpoint, { ...options, skipAuthRefresh: true })
      }
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      const detail = typeof err?.detail === "string" ? err.detail : `API request failed (${res.status})`
      throw new Error(detail || "API Error")
    }

    return res.json()
  }

  get<T = unknown>(endpoint: string) { return this.request<T>(endpoint) }
  post<T = unknown>(endpoint: string, body?: unknown) { return this.request<T>(endpoint, { method: "POST", body }) }
  put<T = unknown>(endpoint: string, body?: unknown) { return this.request<T>(endpoint, { method: "PUT", body }) }
  delete<T = unknown>(endpoint: string) { return this.request<T>(endpoint, { method: "DELETE" }) }
}

export const api = new ApiClient()
export default api

export function decodeTokenPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".")
    if (parts.length < 2) return null
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/")
    const json = typeof atob === "function" ? atob(b64) : Buffer.from(b64, "base64").toString("utf-8")
    return JSON.parse(json)
  } catch {
    return null
  }
}
