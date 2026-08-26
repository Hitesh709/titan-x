"use client"

import { createContext, useContext, useEffect, useState, useCallback, useMemo, type ReactNode } from "react"
import { useRouter } from "next/navigation"
import api from "@/lib/api"
import type { User, AuthResponse } from "@/types"

interface VerificationResult {
  message: string
  verification_url?: string
  reset_url?: string
}
interface MfaAuthResponse extends AuthResponse {
  mfa_required?: boolean
  mfa_challenge?: string | null
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string, remember?: boolean) => Promise<void>
  completeMfaLogin: (challenge: string, code: string) => Promise<void>
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
    const refreshToken = api.getRefreshToken()
    if (token || refreshToken) {
      api.get<User>("/auth/me")
        .then((u) => setUser(u))
        .catch(() => { api.clearTokens(); setUser(null) })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!user) return
    const refresh = () => { if (api.getRefreshToken()) void api.refreshAccessToken() }
    const interval = window.setInterval(refresh, 10 * 60 * 1000)
    return () => window.clearInterval(interval)
  }, [user])

  const login = useCallback(async (email: string, password: string, _remember = true) => {
    const data = await api.post<MfaAuthResponse>("/auth/login", { email, password })
    if (data.mfa_required && data.mfa_challenge) {
      throw new Error(`MFA_REQUIRED:${data.mfa_challenge}`)
    }
    if (!data.access_token || !data.refresh_token) throw new Error("Login failed")
    api.setToken(data.access_token)
    api.setRefreshToken(data.refresh_token)
    const me = await api.get<User>("/auth/me")
    setUser(me)
    router.push("/dashboard")
  }, [router])

  const completeMfaLogin = useCallback(async (challenge: string, code: string) => {
    const data = await api.post<AuthResponse>("/auth/mfa-login", { challenge, code })
    if (!data.access_token || !data.refresh_token) throw new Error("MFA verification failed")
    api.setToken(data.access_token)
    api.setRefreshToken(data.refresh_token)
    const me = await api.get<User>("/auth/me")
    setUser(me)
    router.push("/dashboard")
  }, [router])

  const register = useCallback(async (email: string, password: string) => {
    await api.post("/auth/register", { email, password })
    await login(email, password)
  }, [login])

  const logout = useCallback(() => {
    const refreshToken = api.getRefreshToken()
    if (refreshToken) void api.post("/auth/logout", { refresh_token: refreshToken })
    api.clearTokens()
    setUser(null)
    router.push("/")
  }, [router])

  const verifyEmail = useCallback(async (token: string) => { await api.post("/auth/verify-email", { token }) }, [])
  const sendVerification = useCallback(async (email: string) => api.post<VerificationResult>("/auth/send-verification", { email }), [])
  const forgotPassword = useCallback(async (email: string) => api.post<VerificationResult>("/auth/forgot-password", { email }), [])
  const resetPassword = useCallback(async (token: string, newPassword: string) => { await api.post("/auth/reset-password", { token, new_password: newPassword }) }, [])

  const value = useMemo<AuthContextType>(() => ({
    user, loading, login, completeMfaLogin, register, logout, isAuthenticated: !!user,
    verifyEmail, sendVerification, forgotPassword, resetPassword,
  }), [user, loading, login, completeMfaLogin, register, logout, verifyEmail, sendVerification, forgotPassword, resetPassword])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
