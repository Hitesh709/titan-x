"use client"

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react"
import { useRouter } from "next/navigation"
import api from "@/lib/api"
import type { User, AuthResponse } from "@/types"

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
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
      api.get<User>("/auth/me")
        .then((u) => setUser(u))
        .catch(() => api.setToken(null))
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const data: AuthResponse = await api.post("/auth/login", { email, password })
    api.setToken(data.access_token)
    const me = await api.get<User>("/auth/me")
    setUser(me)
    router.push("/dashboard")
  }, [router])

  const register = useCallback(async (email: string, password: string) => {
    await api.post("/auth/register", { email, password })
    await login(email, password)
  }, [login])

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
