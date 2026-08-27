"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Eye, EyeOff, Shield, Loader2, MailCheck } from "lucide-react"
import api from "@/lib/api"

type CreateResponse = {
  challenge_id: string
  expires_in_seconds: number
  message: string
}

type TokenResponse = {
  access_token?: string | null
  refresh_token?: string | null
}

export default function RegisterPage() {
  const [username, setUsername] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [challengeId, setChallengeId] = useState<string | null>(null)
  const [otp, setOtp] = useState("")
  const [seconds, setSeconds] = useState(0)
  const [loading, setLoading] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  useEffect(() => {
    if (!challengeId || seconds <= 0) return
    const timer = window.setInterval(() => setSeconds(value => Math.max(0, value - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [challengeId, seconds])

  const requestOtp = async () => {
    setError("")
    setNotice("")
    if (!username.trim() || !email.trim() || !phone.trim() || password.length < 8 || password !== confirmPassword) {
      setError("Enter username, email, mobile number, and matching 8+ character passwords.")
      return
    }
    setLoading(true)
    try {
      const data = await api.post<CreateResponse>("/auth/register/email-otp/create", {
        username: username.trim(),
        email: email.trim(),
        phone: phone.trim(),
        password,
        confirm_password: confirmPassword,
      })
      setChallengeId(data.challenge_id)
      setSeconds(data.expires_in_seconds)
      setNotice("A 6-digit verification code has been sent to your email.")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send email verification code")
    } finally {
      setLoading(false)
    }
  }

  const verifyOtp = async () => {
    if (!challengeId || !/^\d{6}$/.test(otp)) {
      setError("Enter the 6-digit email OTP.")
      return
    }
    setError("")
    setNotice("")
    setVerifying(true)
    try {
      const data = await api.post<TokenResponse>("/auth/register/email-otp/verify", {
        challenge_id: challengeId,
        otp,
      })
      if (!data.access_token || !data.refresh_token) throw new Error("Account was created but a secure session could not be established.")
      api.setToken(data.access_token)
      api.setRefreshToken(data.refresh_token)
      window.location.href = "/dashboard"
    } catch (err) {
      setError(err instanceof Error ? err.message : "Email OTP verification failed")
    } finally {
      setVerifying(false)
    }
  }

  const reset = () => {
    setChallengeId(null)
    setOtp("")
    setSeconds(0)
    setError("")
    setNotice("")
  }

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-1 bg-gradient-to-br from-titan-900 to-titan-950 items-center justify-center p-12">
        <div className="text-center max-w-md">
          <Shield className="w-16 h-16 text-titan-400 mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-white mb-3">Secure Account Registration</h2>
          <p className="text-gray-400 leading-relaxed">Mobile number is mandatory. Email OTP is the only verification step during registration.</p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <Link href="/" className="text-lg font-bold text-white">TITAN <span className="text-titan-400">X</span></Link>
            <h1 className="text-2xl font-bold text-white mt-8">Create your account</h1>
            <p className="text-gray-500 mt-1">Mobile required • Email OTP verification</p>
          </div>

          {error && <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>}
          {notice && <div className="mb-4 p-3 rounded-lg bg-titan-500/10 border border-titan-500/20 text-titan-300 text-sm">{notice}</div>}

          {!challengeId ? (
            <div className="space-y-4">
              <input value={username} onChange={e => setUsername(e.target.value)} className="input-field" placeholder="Username" autoComplete="username" required />
              <input value={email} onChange={e => setEmail(e.target.value)} className="input-field" placeholder="Email" type="email" autoComplete="email" required />
              <input value={phone} onChange={e => setPhone(e.target.value)} className="input-field" placeholder="Mobile number (required)" type="tel" autoComplete="tel" required />
              <div className="relative">
                <input type={showPassword ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)} className="input-field pr-10" placeholder="Password" autoComplete="new-password" required />
                <button type="button" onClick={() => setShowPassword(value => !value)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button>
              </div>
              <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} className="input-field" placeholder="Re-enter password" autoComplete="new-password" required />
              <button type="button" onClick={() => void requestOtp()} disabled={loading} className="btn-primary w-full">
                {loading ? <Loader2 size={16} className="animate-spin" /> : <MailCheck size={16} />}
                {loading ? "Sending OTP..." : "Send Email OTP"}
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-center">
                <MailCheck className="mx-auto h-8 w-8 text-titan-400" />
                <h2 className="text-lg font-semibold text-white mt-3">Verify your email</h2>
                <p className="mt-2 text-sm text-gray-400">Enter the 6-digit OTP sent to <span className="text-gray-200">{email}</span>.</p>
                <p className="mt-2 text-xs text-gray-500">Expires in {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</p>
              </div>
              <input value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))} className="input-field text-center tracking-[0.5em]" inputMode="numeric" autoComplete="one-time-code" placeholder="000000" maxLength={6} />
              <button type="button" onClick={() => void verifyOtp()} disabled={verifying || otp.length !== 6 || seconds <= 0} className="btn-primary w-full">
                {verifying ? <Loader2 size={16} className="animate-spin" /> : <MailCheck size={16} />}
                {verifying ? "Verifying..." : "Verify & Create Account"}
              </button>
              <button type="button" onClick={reset} className="w-full rounded-xl border border-white/10 py-3 text-sm text-gray-400 hover:text-white">Start over</button>
            </div>
          )}

          <p className="mt-6 text-center text-sm text-gray-500">Already have an account? <Link href="/login" className="text-titan-400 hover:text-titan-300 font-medium">Sign in</Link></p>
        </div>
      </div>
    </div>
  )
}
