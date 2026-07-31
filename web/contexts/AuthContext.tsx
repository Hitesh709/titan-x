"use client"

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from "react"
import { useRouter } from "next/navigation"
import api, { getTokenExpiry } from "@/lib/api"
import type {
  User,
  AuthResponse,
  ForgotPasswordResponse,
  MessageResponse,
  RegisterResponse,
  SendVerificationResponse,
} from "@/types"

interface AuthContextType {
  user: User | null
  loading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string, remember?: boolean) => Promise<void>
  register: (email: string, password: string) => Promise<RegisterResponse>
  logout: () => Promise<void>
  forgotPassword: (email: string) => Promise<ForgotPasswordResponse>
  resetPassword: (token: string, newPassword: string) => Promise<MessageResponse>
  sendVerification: (email: string) => Promise<SendVerificationResponse>
  verifyEmail: (token: string) => Promise<MessageResponse>
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const REFRESH_MARGIN_MS = 60_000

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const router = useRouter()
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loggedOutRef = useRef(false)

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimer.current) {
      clearTimeout(refreshTimer.current)
      refreshTimer.current = null
    }
  }, [])

  const scheduleRefresh = useCallback(() => {
    clearRefreshTimer()
    const expiresAt = api.getTokenExpiryMs()
    if (expiresAt == null) return
    const delay = Math.max(0, expiresAt - Date.now() - REFRESH_MARGIN_MS)
    refreshTimer.current = setTimeout(async () => {
      const ok = await api.refreshTokens()
      if (ok) {
        scheduleRefresh()
      }
    }, delay)
  }, [clearRefreshTimer])

  const forceLogout = useCallback(() => {
    api.clearTokens()
    setUser(null)
    clearRefreshTimer()
    if (!loggedOutRef.current) {
      loggedOutRef.current = true
      router.replace("/login?expired=1")
    }
  }, [clearRefreshTimer, router])

  useEffect(() => {
    api.setSessionExpiredHandler(forceLogout)
    return () => {
      api.setSessionExpiredHandler(null)
      clearRefreshTimer()
    }
  }, [forceLogout, clearRefreshTimer])

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        if (!api.hasSession()) {
          if (!cancelled) setLoading(false)
          return
        }
        if (!api.getAccessToken()) {
          const ok = await api.refreshTokens()
          if (!ok || cancelled) {
            if (!cancelled) setLoading(false)
            return
          }
        }
        const me = await api.get<User>("/auth/me")
        if (cancelled) return
        setUser(me)
        scheduleRefresh()
      } catch {
        if (!cancelled) {
          api.clearTokens()
          setUser(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    bootstrap()
    return () => {
      cancelled = true
    }
  }, [scheduleRefresh])

  const login = useCallback(
    async (email: string, password: string, remember = false) => {
      const data: AuthResponse = await api.post<AuthResponse>("/auth/login", { email, password }, { skipAuth: true })
      api.setTokens(data.access_token, data.refresh_token, remember)
      const me = await api.get<User>("/auth/me")
      setUser(me)
      scheduleRefresh()
      router.push("/dashboard")
    },
    [router, scheduleRefresh]
  )

  const register = useCallback(async (email: string, password: string) => {
    const res = await api.post<RegisterResponse>("/auth/register", { email, password }, { skipAuth: true })
    return res
  }, [])

  const logout = useCallback(async () => {
    loggedOutRef.current = true
    const refreshToken = api.getRefreshToken()
    if (refreshToken) {
      try {
        await api.post<MessageResponse>("/auth/logout", { refresh_token: refreshToken }, { skipAuth: true })
      } catch {
        // ignore server-side logout errors; clear local session regardless
      }
    }
    api.clearTokens()
    setUser(null)
    clearRefreshTimer()
    router.push("/")
  }, [clearRefreshTimer, router])

  const forgotPassword = useCallback(
    async (email: string) =>
      api.post<ForgotPasswordResponse>("/auth/forgot-password", { email }, { skipAuth: true }),
    []
  )

  const resetPassword = useCallback(
    async (token: string, newPassword: string) =>
      api.post<MessageResponse>("/auth/reset-password", { token, new_password: newPassword }, { skipAuth: true }),
    []
  )

  const sendVerification = useCallback(
    async (email: string) =>
      api.post<SendVerificationResponse>("/auth/send-verification", { email }, { skipAuth: true }),
    []
  )

  const verifyEmail = useCallback(
    async (token: string) =>
      api.post<MessageResponse>("/auth/verify-email", { token }, { skipAuth: true }),
    []
  )

  const refreshUser = useCallback(async () => {
    const me = await api.get<User>("/auth/me")
    setUser(me)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
        forgotPassword,
        resetPassword,
        sendVerification,
        verifyEmail,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}

export { getTokenExpiry }
