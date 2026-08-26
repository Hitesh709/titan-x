"use client"

import { useState, useEffect, Suspense, useCallback } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { QrCode, RefreshCw, Smartphone, TrendingUp, X } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { AuthShell } from "@/components/auth/AuthShell"
import { PasswordField, SubmitButton, FormError, FormSuccess } from "@/components/auth/fields"
import api from "@/lib/api"
import type { User } from "@/types"

type QRCreateResponse = { challenge_id: string; qr_data_url: string; expires_at: string; expires_in_seconds: number }
type QRStatusResponse = { status: "PENDING" | "SCANNED" | "APPROVED" | "DECLINED" | "EXPIRED" | "CANCELLED" | "USED"; access_token?: string | null; refresh_token?: string | null; user?: User | null }

function LoginInner() {
  const { login, completeMfaLogin, isAuthenticated } = useAuth()
  const searchParams = useSearchParams()
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [mfaCode, setMfaCode] = useState(""); const [mfaChallenge, setMfaChallenge] = useState("")
  const [mfaRequired, setMfaRequired] = useState(false); const [remember, setRemember] = useState(true); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [loading, setLoading] = useState(false)
  const [qrMode, setQrMode] = useState(false); const [qr, setQr] = useState<QRCreateResponse | null>(null); const [qrStatus, setQrStatus] = useState<QRStatusResponse["status"] | null>(null); const [qrSeconds, setQrSeconds] = useState(0)

  useEffect(() => { if (searchParams.get("expired") === "1") setNotice("Your session has expired. Please sign in again.") }, [searchParams])
  useEffect(() => { if (isAuthenticated) window.location.href = "/dashboard" }, [isAuthenticated])

  const resetQr = useCallback(() => { setQr(null); setQrStatus(null); setQrSeconds(0); setError("") }, [])
  const createQr = useCallback(async () => {
    setError(""); setNotice(""); setLoading(true)
    try { const data = await api.post<QRCreateResponse>("/auth/qr/create"); setQr(data); setQrStatus("PENDING"); setQrSeconds(data.expires_in_seconds); setNotice("Scan this QR code with your registered Xecaps mobile app.") }
    catch (err) { setError(err instanceof Error ? err.message : "Could not create QR login") }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    if (!qrMode || !qr || qrSeconds <= 0 || qrStatus === "USED" || qrStatus === "DECLINED" || qrStatus === "EXPIRED" || qrStatus === "CANCELLED") return
    const timer = window.setInterval(() => setQrSeconds((value) => Math.max(0, value - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [qrMode, qr, qrSeconds, qrStatus])

  useEffect(() => {
    if (!qrMode || !qr || qrSeconds <= 0 || qrStatus === "DECLINED" || qrStatus === "EXPIRED" || qrStatus === "CANCELLED" || qrStatus === "USED") return
    const poll = window.setInterval(async () => {
      try {
        const data = await api.get<QRStatusResponse>(`/auth/qr/status/${encodeURIComponent(qr.challenge_id)}`)
        setQrStatus(data.status)
        if (data.status === "USED" && data.access_token && data.refresh_token) {
          api.setToken(data.access_token); api.setRefreshToken(data.refresh_token); setNotice("Login approved. Signing you in..."); window.setTimeout(() => { window.location.href = "/dashboard" }, 350)
        }
      } catch (err) { const message = err instanceof Error ? err.message : "QR status check failed"; if (message.includes("expired")) setQrStatus("EXPIRED") }
    }, 1500)
    return () => window.clearInterval(poll)
  }, [qrMode, qr, qrSeconds, qrStatus])

  useEffect(() => { if (qrMode && qrSeconds === 0 && qrStatus && ["PENDING", "SCANNED"].includes(qrStatus)) setQrStatus("EXPIRED") }, [qrMode, qrSeconds, qrStatus])

  const cancelQr = async () => { if (!qr) return; try { await api.post("/auth/qr/cancel", { challenge_id: qr.challenge_id }) } catch {} resetQr(); setQrMode(false); setNotice("") }
  const handleSubmit = async (e: React.FormEvent) => { e.preventDefault(); setError(""); setNotice(""); setLoading(true); try { await login(email, password, remember) } catch (err) { const message = err instanceof Error ? err.message : "Login failed"; if (message.startsWith("MFA_REQUIRED:")) { setMfaChallenge(message.slice("MFA_REQUIRED:".length)); setMfaRequired(true); setNotice("Enter your authenticator code or a recovery code.") } else setError(message) } finally { setLoading(false) } }
  const handleMfa = async (e: React.FormEvent) => { e.preventDefault(); setError(""); setLoading(true); try { await completeMfaLogin(mfaChallenge, mfaCode.trim()) } catch (err) { setError(err instanceof Error ? err.message : "MFA verification failed") } finally { setLoading(false) } }

  return <AuthShell title={mfaRequired ? "Two-factor verification" : qrMode ? "Login with Mobile QR" : "Welcome back"} subtitle={mfaRequired ? "Verify your identity to continue" : qrMode ? "Approve this login from your registered mobile" : "Sign in to your TITAN X account"} aside={<><TrendingUp className="w-16 h-16 text-titan-400 mx-auto mb-6" /><h2 className="text-2xl font-bold text-white mb-3">AI-Powered Market Intelligence</h2><p className="text-gray-400 leading-relaxed">Access real-time analytics, predictive models, and automated trading strategies — all from a single, secure platform.</p></>}>
    {mfaRequired ? <form onSubmit={handleMfa} className="space-y-4"><FormError message={error} /><FormSuccess message={notice} /><div><label htmlFor="mfa-code" className="block text-sm font-medium text-gray-400 mb-1.5">Authenticator / recovery code</label><input id="mfa-code" inputMode="numeric" autoComplete="one-time-code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} className="input-field tracking-widest" placeholder="123456 or recovery code" minLength={6} maxLength={64} required /></div><SubmitButton loading={loading} loadingText="Verifying...">Verify & Sign In</SubmitButton><button type="button" onClick={() => { setMfaRequired(false); setMfaChallenge(""); setMfaCode(""); setError(""); setNotice("") }} className="w-full text-sm text-gray-400 hover:text-white">Back to password login</button></form> : qrMode ? <div className="space-y-4"><FormError message={error} /><FormSuccess message={notice} />{!qr ? <button type="button" onClick={createQr} disabled={loading} className="w-full rounded-xl border border-titan-500/40 bg-titan-500/10 py-3 text-titan-300 hover:bg-titan-500/20 disabled:opacity-50"><QrCode className="inline-block mr-2 h-5 w-5" />{loading ? "Generating secure QR..." : "Generate secure QR"}</button> : <><div className="rounded-2xl bg-white p-4 mx-auto w-fit shadow-xl"><img src={qr.qr_data_url} alt="One-time login QR code" className="w-56 h-56" /></div><div className="text-center text-sm text-gray-400"><div className="font-medium text-white">{qrStatus === "SCANNED" ? "QR SCANNED — check your mobile" : qrStatus === "DECLINED" ? "Login request declined" : qrStatus === "EXPIRED" ? "QR CODE EXPIRED" : "Scan with Xecaps Mobile App"}</div><div className="mt-1">{qrStatus === "SCANNED" ? "Approve the login request on your registered device." : qrStatus === "PENDING" ? `Expires in ${String(Math.floor(qrSeconds / 60)).padStart(2, "0")}:${String(qrSeconds % 60).padStart(2, "0")}` : qrStatus === "DECLINED" ? "No web session was created." : qrStatus === "EXPIRED" ? "Generate a new QR code to try again." : ""}</div></div>{(qrStatus === "EXPIRED" || qrStatus === "DECLINED") ? <button type="button" onClick={resetQr} className="w-full rounded-xl border border-white/10 py-3 text-gray-300 hover:bg-white/5"><RefreshCw className="inline-block mr-2 h-4 w-4" />Generate New QR</button> : <button type="button" onClick={cancelQr} className="w-full rounded-xl border border-white/10 py-3 text-gray-400 hover:text-white"><X className="inline-block mr-2 h-4 w-4" />Cancel</button>}</>}</div><button type="button" onClick={() => { void cancelQr() }} className="w-full text-sm text-gray-400 hover:text-white"><Smartphone className="inline-block mr-1 h-4 w-4" />Login another way</button></div> : <form onSubmit={handleSubmit} className="space-y-4"><FormError message={error} /><FormSuccess message={notice} /><div><label htmlFor="email" className="block text-sm font-medium text-gray-400 mb-1.5">Email</label><input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input-field" placeholder="you@company.com" autoComplete="email" required /></div><PasswordField id="password" label="Password" value={password} onChange={setPassword} placeholder="Enter your password" autoComplete="current-password" /><div className="flex items-center justify-between text-sm"><label className="flex items-center gap-2 text-gray-400 cursor-pointer"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="rounded border-gray-600 bg-white/5" /> Remember me</label><Link href="/forgot-password" className="text-titan-400 hover:text-titan-300">Forgot password?</Link></div><SubmitButton loading={loading} loadingText="Signing in...">Sign In</SubmitButton><button type="button" onClick={() => { setQrMode(true); resetQr(); void createQr() }} className="w-full rounded-xl border border-titan-500/30 bg-titan-500/5 py-3 text-titan-300 hover:bg-titan-500/10"><QrCode className="inline-block mr-2 h-5 w-5" />Login with Mobile QR</button></form>}
    {!mfaRequired && !qrMode && <p className="mt-6 text-center text-sm text-gray-500">Don&apos;t have an account? <Link href="/register" className="text-titan-400 hover:text-titan-300 font-medium">Create one</Link></p>}
  </AuthShell>
}
export default function LoginPage() { return <Suspense fallback={<div className="min-h-screen bg-titan-950" />}><LoginInner /></Suspense> }
