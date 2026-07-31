const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

class ApiClient {
  private token: string | null = null
  private apiKey: string | null = null

  setToken(token: string | null) {
    this.token = token
    if (typeof window !== "undefined") {
      if (token) localStorage.setItem("titan_token", token)
      else localStorage.removeItem("titan_token")
    }
  }

  getToken(): string | null {
    if (this.token) return this.token
    if (typeof window !== "undefined") {
      this.token = localStorage.getItem("titan_token")
    }
    return this.token
  }

  setApiKey(key: string | null) {
    this.apiKey = key
  }

  async request<T = unknown>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { method = "GET", body, headers = {} } = options
    const token = this.getToken()

    const h: Record<string, string> = {
      "Content-Type": "application/json",
      ...headers,
    }

    if (token) h["Authorization"] = `Bearer ${token}`
    if (this.apiKey) h["X-API-Key"] = this.apiKey

    const res = await fetch(`${API_BASE}${endpoint}`, {
      method,
      headers: h,
      body: body ? JSON.stringify(body) : undefined,
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      const detail = typeof err.detail === "string" ? err.detail : Array.isArray(err.detail) ? err.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ") : err.message || res.statusText
      throw new Error(detail || "API Error")
    }

    return res.json()
  }

  get<T = unknown>(endpoint: string) {
    return this.request<T>(endpoint)
  }

  post<T = unknown>(endpoint: string, body: unknown) {
    return this.request<T>(endpoint, { method: "POST", body })
  }

  put<T = unknown>(endpoint: string, body: unknown) {
    return this.request<T>(endpoint, { method: "PUT", body })
  }

  delete<T = unknown>(endpoint: string) {
    return this.request<T>(endpoint, { method: "DELETE" })
  }
}

export const api = new ApiClient()
export default api
