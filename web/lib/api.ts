const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

const ACCESS_KEY = "titan_x_access"
const REFRESH_KEY = "titan_x_refresh"
const REMEMBER_KEY = "titan_x_remember"

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
  skipAuth?: boolean
  _retried?: boolean
}

function decodeTokenPayload(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split(".")[1]
    if (!payload) return null
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/")
    const json = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    )
    return JSON.parse(json)
  } catch {
    return null
  }
}

function getTokenExpiry(token: string | null): number | null {
  if (!token) return null
  const payload = decodeTokenPayload(token)
  if (!payload || typeof payload.exp !== "number") return null
  return payload.exp * 1000
}

class ApiClient {
  private accessToken: string | null = null
  private refreshToken: string | null = null
  private remember = false
  private refreshPromise: Promise<boolean> | null = null
  private apiKey: string | null =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_KEY
      ? process.env.NEXT_PUBLIC_API_KEY
      : null
  private onSessionExpired: (() => void) | null = null

  constructor() {
    if (typeof window !== "undefined") {
      const remember = localStorage.getItem(REMEMBER_KEY) === "1"
      this.remember = remember
      this.refreshToken = (remember ? localStorage : sessionStorage).getItem(REFRESH_KEY)
      this.accessToken = sessionStorage.getItem(ACCESS_KEY)
    }
  }

  setSessionExpiredHandler(handler: (() => void) | null) {
    this.onSessionExpired = handler
  }

  setTokens(accessToken: string | null, refreshToken: string | null, remember: boolean) {
    this.accessToken = accessToken
    this.refreshToken = refreshToken
    this.remember = remember
    if (typeof window !== "undefined") {
      const store = remember ? localStorage : sessionStorage
      if (refreshToken) store.setItem(REFRESH_KEY, refreshToken)
      else store.removeItem(REFRESH_KEY)
      if (accessToken) sessionStorage.setItem(ACCESS_KEY, accessToken)
      else sessionStorage.removeItem(ACCESS_KEY)
      if (remember) localStorage.setItem(REMEMBER_KEY, "1")
      else localStorage.removeItem(REMEMBER_KEY)
    }
  }

  clearTokens() {
    this.accessToken = null
    this.refreshToken = null
    if (typeof window !== "undefined") {
      localStorage.removeItem(REFRESH_KEY)
      sessionStorage.removeItem(REFRESH_KEY)
      sessionStorage.removeItem(ACCESS_KEY)
      localStorage.removeItem(REMEMBER_KEY)
    }
  }

  getAccessToken(): string | null {
    return this.accessToken
  }

  getRefreshToken(): string | null {
    return this.refreshToken
  }

  getRemember(): boolean {
    return this.remember
  }

  hasSession(): boolean {
    return !!this.accessToken || !!this.refreshToken
  }

  getTokenExpiryMs(): number | null {
    return getTokenExpiry(this.accessToken)
  }

  setApiKey(key: string | null) {
    this.apiKey = key
  }

  async refreshTokens(): Promise<boolean> {
    if (!this.refreshToken) return false
    if (this.refreshPromise) return this.refreshPromise

    this.refreshPromise = (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: this.refreshToken }),
        })
        if (!res.ok) {
          this.clearTokens()
          this.onSessionExpired?.()
          return false
        }
        const data = await res.json()
        this.setTokens(data.access_token, data.refresh_token, this.remember)
        return true
      } catch {
        this.clearTokens()
        this.onSessionExpired?.()
        return false
      } finally {
        this.refreshPromise = null
      }
    })()

    return this.refreshPromise
  }

  async request<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { method = "GET", body, headers = {}, skipAuth = false } = options
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      ...headers,
    }

    if (this.accessToken) h["Authorization"] = `Bearer ${this.accessToken}`
    if (this.apiKey) h["X-API-Key"] = this.apiKey

    const doFetch = () =>
      fetch(`${API_BASE}${endpoint}`, {
        method,
        headers: h,
        body: body ? JSON.stringify(body) : undefined,
      })

    let res = await doFetch()

    if (res.status === 401 && !skipAuth && !options._retried && this.refreshToken) {
      const refreshed = await this.refreshTokens()
      if (refreshed) {
        h["Authorization"] = `Bearer ${this.accessToken}`
        res = await doFetch()
      }
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      const detail =
        typeof err.detail === "string"
          ? err.detail
          : Array.isArray(err.detail)
            ? err.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ")
            : err.message || res.statusText
      throw new Error(detail || "API Error")
    }

    return res.json()
  }

  get<T = unknown>(endpoint: string, options?: RequestOptions) {
    return this.request<T>(endpoint, options)
  }

  post<T = unknown>(endpoint: string, body: unknown, options?: RequestOptions) {
    return this.request<T>(endpoint, { method: "POST", body, ...options })
  }

  put<T = unknown>(endpoint: string, body: unknown, options?: RequestOptions) {
    return this.request<T>(endpoint, { method: "PUT", body, ...options })
  }

  delete<T = unknown>(endpoint: string, options?: RequestOptions) {
    return this.request<T>(endpoint, { method: "DELETE", ...options })
  }
}

export const api = new ApiClient()
export { getTokenExpiry, decodeTokenPayload }
export default api
