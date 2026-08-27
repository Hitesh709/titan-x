"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Eye, EyeOff, Shield, Loader2, QrCode, RefreshCw } from "lucide-react"
import api from "@/lib/api"

type QRCreate = { challenge_id: string; qr_data_url: string; expires_in_seconds: number; sms_number?: string | null }
type QRStatus = { status: "PENDING" | "APPROVED" | "EMAIL_OTP_REQUIRED" | "DECLINED" | "EXPIRED" | "CANCELLED" | "USED"; access_token?: string | null; refresh_token?: string | null }

export default function RegisterPage() {
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [loading, setLoading] = useState(false)
  const [qr, setQr] = useState<QRCreate | null>(null)
  const [seconds, setSeconds] = useState(0)
  const [status, setStatus] = useState<QRStatus["status"] | null>(null)
  const [emailOtp, setEmailOtp] = useState("")
  const [verifyingEmail, setVerifyingEmail] = useState(false)

  useEffect(() => {
    if (!qr || seconds <= 0 || ["EMAIL_OTP_REQUIRED", "APPROVED", "USED", "DECLINED", "EXPIRED", "CANCELLED"].includes(status || "")) return
    const t = window.setInterval(() => setSeconds(v => Math.max(0, v - 1)), 1000)
    return () => window.clearInterval(t)
  }, [qr, seconds, status])

  useEffect(() => {
    if (!qr || seconds <= 0 || ["USED", "DECLINED", "EXPIRED", "CANCELLED"].includes(status || "")) return
    const t = window.setInterval(async () => {
      try {
        const data = await api.get<QRStatus>(`/auth/qr/status/${encodeURIComponent(qr.challenge_id)}`)
        setStatus(data.status)
        if (data.status === "EMAIL_OTP_REQUIRED") setNotice("Mobile verified. A 6-digit OTP has been sent to your email address.")
        if (data.status === "USED" && data.access_token && data.refresh_token) {
          api.setToken(data.access_token)
          api.setRefreshToken(data.refresh_token)
          window.location.href = "/dashboard"
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not check registration status")
      }
    }, 1500)
    return () => window.clearInterval(t)
  }, [qr, seconds, status])

  useEffect(() => {
    if (qr && seconds === 0 && ["PENDING"].includes(status || "")) setStatus("EXPIRED")
  }, [qr, seconds, status])

  const createQr = async () => {
    setError("")
    setNotice("")
    if (!username.trim() || password !== confirmPassword || password.length < 8 || (!email.trim() && !phone.trim())) {
      setError("Enter username, matching 8+ character passwords, and email or phone.")
      return
    }
    if (email.trim() && !phone.trim()) {
      setError("Mobile number is required when you register an email, because QR + SMS verifies the phone first.")
      return
    }
    setLoading(true)
    try {
      const data = await api.post<QRCreate>("/auth/qr/register/create", { username: username.trim(), password, confirm_password: confirmPassword, email: email.trim() || null, phone: phone.trim() || null })
      setQr(data)
      setStatus("PENDING")
      setSeconds(data.expires_in_seconds)
      setNotice("Scan with any smartphone camera and send the prefilled SMS from the phone being registered.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create registration QR")
    } finally {
      setLoading(false)
    }
  }

  const verifyEmailOtp = async () => {
    if (!qr || !/^\d{6}$/.test(emailOtp)) {
      setError("Enter the 6-digit email OTP.")
      return
    }
    setError("")
    setNotice("")
    setVerifyingEmail(true)
    try {
      await api.post("/auth/qr/register/email-otp/verify", { challenge_id: qr.challenge_id, otp: emailOtp })
      const data = await api.get<QRStatus>(`/auth/qr/status/${encodeURIComponent(qr.challenge_id)}`)
      if (data.status === "USED" && data.access_token && data.refresh_token) {
        api.setToken(data.access_token)
        api.setRefreshToken(data.refresh_token)
        setNotice("Email verified. Registration complete. Signing you in...")
        window.location.href = "/dashboard"
        return
      }
      setStatus(data.status)
      setNotice("Email verified. Completing registration...")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Email OTP verification failed")
    } finally {
      setVerifyingEmail(false)
    }
  }

  return <div className="min-h-screen flex"><div className="hidden lg:flex flex-1 bg-gradient-to-br from-titan-900 to-titan-950 items-center justify-center p-12"><div className="text-center max-w-md"><Shield className="w-16 h-16 text-titan-400 mx-auto mb-6" /><h2 className="text-2xl font-bold text-white mb-3">Secure Account Registration</h2><p className="text-gray-400 leading-relaxed">Verify your mobile by QR + SMS and verify your email with a one-time OTP before Titan-X creates the account.</p></div></div><div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8"><div className="w-full max-w-sm"><div className="mb-8"><Link href="/" className="text-lg font-bold text-white">TITAN <span className="text-titan-400">X</span></Link><h1 className="text-2xl font-bold text-white mt-8">Create your account</h1><p className="text-gray-500 mt-1">Verify mobile by QR + SMS{email.trim() ? " and email by OTP" : ""}</p></div>{error && <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>}{notice && <div className="mb-4 p-3 rounded-lg bg-titan-500/10 border border-titan-500/20 text-titan-300 text-sm">{notice}</div>}{!qr || ["EXPIRED", "DECLINED"].includes(status || "") ? <div className="space-y-4"><input value={username} onChange={e => setUsername(e.target.value)} className="input-field" placeholder="Username" required /><input value={email} onChange={e => setEmail(e.target.value)} className="input-field" placeholder="Email (optional)" type="email" /><input value={phone} onChange={e => setPhone(e.target.value)} className="input-field" placeholder="Mobile number" type="tel" required /><div className="relative"><input type={showPassword ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)} className="input-field pr-10" placeholder="Password" required /><button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button></div><input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} className="input-field" placeholder="Re-enter password" required /><button type="button" onClick={() => void createQr()} disabled={loading} className="btn-primary w-full">{loading ? <Loader2 size={16} className="animate-spin" /> : <QrCode size={16} />}{loading ? "Generating..." : "Generate QR & Verify Mobile"}</button></div> : status === "EMAIL_OTP_REQUIRED" ? <div className="space-y-4"><div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-center"><h2 className="text-lg font-semibold text-white">Verify your email</h2><p className="mt-2 text-sm text-gray-400">Enter the 6-digit OTP sent to {email}.</p></div><input value={emailOtp} onChange={e => setEmailOtp(e.target.value.replace(/\D/g, "").slice(0, 6))} className="input-field text-center tracking-[0.5em]" inputMode="numeric" autoComplete="one-time-code" placeholder="000000" maxLength={6} /><button type="button" onClick={() => void verifyEmailOtp()} disabled={verifyingEmail || emailOtp.length !== 6} className="btn-primary w-full">{verifyingEmail ? "Verifying..." : "Verify Email OTP"}</button></div> : <div className="space-y-4"><div className="rounded-2xl bg-white p-4 mx-auto w-fit"><img src={qr.qr_data_url} alt="Registration QR code" className="w-56 h-56" /></div><p className="text-center text-sm text-gray-400">Scan with any smartphone camera, then send the prefilled SMS from the phone being registered.</p><p className="text-center text-white font-medium">{status === "PENDING" ? `Expires in ${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}` : status}</p>{status === "EXPIRED" && <button type="button" onClick={() => { setQr(null); setStatus(null); setSeconds(0) }} className="w-full rounded-xl border border-white/10 py-3 text-gray-300"><RefreshCw className="inline mr-2 h-4 w-4" />Generate New QR</button>}</div>}<p className="mt-6 text-center text-sm text-gray-500">Already have an account? <Link href="/login" className="text-titan-400 hover:text-titan-300 font-medium">Sign in</Link></p></div></div></div>
}
