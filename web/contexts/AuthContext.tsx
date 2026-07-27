"use client"

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react"
import { useRouter } from "next/navigation"
import api from "@/lib/api"
import type { User, AuthResponse } from "@/types"

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName: string) => Promise<void>
  logout: () => void
  isAuthenticated: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()

  useEffect(() => {
    const token = api.getToken()
    if (token) {
      api.get<User[]>("/users/me")
        .then((u) => setUser(Array.isArray(u) ? u[0] : u))
        .catch(() => api.setToken(null))
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const formData = new URLSearchParams({ username: email, password })
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Login failed" }))
      throw new Error(err.detail)
    }
    const data: AuthResponse = await res.json()
    api.setToken(data.access_token)
    setUser(data.user)
    router.push("/dashboard")
  }, [router])

  const register = useCallback(async (email: string, password: string, fullName: string) => {
    const data: AuthResponse = await api.post("/auth/register", {
      email,
      password,
      full_name: fullName,
    })
    api.setToken(data.access_token)
    setUser(data.user)
    router.push("/dashboard")
  }, [router])

  const logout = useCallback(() => {
    api.setToken(null)
    setUser(null)
    router.push("/")
  }, [router])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
