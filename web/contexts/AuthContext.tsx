"use client"

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react"
import { useRouter } from "next/navigation"
import api from "@/lib/api"
import type { User, AuthResponse } from "@/types"

interface VerificationResult {
  message: string
  verification_url?: string
  reset_url?: string
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string, remember?: boolean) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  isAuthenticated: boolean
  verifyEmail: (token: string) => Promise<void>
  sendVerification: (email: string) => Promise<VerificationResult>
  forgotPassword: (email: string) => Promise<VerificationResult>
  resetPassword: (token: string, newPassword: string) => Promise<void>
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

  const login = useCallback(async (email: string, password: string, _remember = true) => {
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

  const verifyEmail = useCallback(async (token: string) => {
    await api.post("/auth/verify-email", { token })
  }, [])

  const sendVerification = useCallback(async (email: string) => {
    return api.post<VerificationResult>("/auth/send-verification", { email })
  }, [])

  const forgotPassword = useCallback(async (email: string) => {
    return api.post<VerificationResult>("/auth/forgot-password", { email })
  }, [])

  const resetPassword = useCallback(async (token: string, newPassword: string) => {
    await api.post("/auth/reset-password", { token, new_password: newPassword })
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, isAuthenticated: !!user, verifyEmail, sendVerification, forgotPassword, resetPassword }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
