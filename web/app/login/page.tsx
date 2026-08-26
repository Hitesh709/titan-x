"use client"

import { useState, useEffect, Suspense } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { TrendingUp } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { AuthShell } from "@/components/auth/AuthShell"
import { PasswordField, SubmitButton, FormError, FormSuccess } from "@/components/auth/fields"

function LoginInner() {
  const { login, completeMfaLogin, isAuthenticated } = useAuth()
  const searchParams = useSearchParams()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [mfaCode, setMfaCode] = useState("")
  const [mfaChallenge, setMfaChallenge] = useState("")
  const [mfaRequired, setMfaRequired] = useState(false)
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (searchParams.get("expired") === "1") setNotice("Your session has expired. Please sign in again.")
  }, [searchParams])

  useEffect(() => {
    if (isAuthenticated) window.location.href = "/dashboard"
  }, [isAuthenticated])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(""); setNotice(""); setLoading(true)
    try {
      await login(email, password, remember)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed"
      if (message.startsWith("MFA_REQUIRED:")) {
        setMfaChallenge(message.slice("MFA_REQUIRED:".length))
        setMfaRequired(true)
        setNotice("Enter your authenticator code or a recovery code.")
      } else setError(message)
    } finally { setLoading(false) }
  }

  const handleMfa = async (e: React.FormEvent) => {
    e.preventDefault(); setError(""); setLoading(true)
    try {
      await completeMfaLogin(mfaChallenge, mfaCode.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : "MFA verification failed")
    } finally { setLoading(false) }
  }

  return (
    <AuthShell
      title={mfaRequired ? "Two-factor verification" : "Welcome back"}
      subtitle={mfaRequired ? "Verify your identity to continue" : "Sign in to your TITAN X account"}
      aside={
        <>
          <TrendingUp className="w-16 h-16 text-titan-400 mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-white mb-3">AI-Powered Market Intelligence</h2>
          <p className="text-gray-400 leading-relaxed">Access real-time analytics, predictive models, and automated trading strategies — all from a single, secure platform.</p>
        </>
      }
    >
      {!mfaRequired ? (
        <form onSubmit={handleSubmit} className="space-y-4">
          <FormError message={error} />
          <FormSuccess message={notice} />
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-400 mb-1.5">Email</label>
            <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input-field" placeholder="you@company.com" autoComplete="email" required />
          </div>
          <PasswordField id="password" label="Password" value={password} onChange={setPassword} placeholder="Enter your password" autoComplete="current-password" />
          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 text-gray-400 cursor-pointer"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="rounded border-gray-600 bg-white/5" /> Remember me</label>
            <Link href="/forgot-password" className="text-titan-400 hover:text-titan-300">Forgot password?</Link>
          </div>
          <SubmitButton loading={loading} loadingText="Signing in...">Sign In</SubmitButton>
        </form>
      ) : (
        <form onSubmit={handleMfa} className="space-y-4">
          <FormError message={error} />
          <FormSuccess message={notice} />
          <div>
            <label htmlFor="mfa-code" className="block text-sm font-medium text-gray-400 mb-1.5">Authenticator / recovery code</label>
            <input id="mfa-code" inputMode="numeric" autoComplete="one-time-code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} className="input-field tracking-widest" placeholder="123456 or recovery code" minLength={6} maxLength={64} required />
          </div>
          <SubmitButton loading={loading} loadingText="Verifying...">Verify & Sign In</SubmitButton>
          <button type="button" onClick={() => { setMfaRequired(false); setMfaChallenge(""); setMfaCode(""); setError(""); setNotice("") }} className="w-full text-sm text-gray-400 hover:text-white">Back to password login</button>
        </form>
      )}

      {!mfaRequired && <p className="mt-6 text-center text-sm text-gray-500">Don&apos;t have an account?{" "}<Link href="/register" className="text-titan-400 hover:text-titan-300 font-medium">Create one</Link></p>}
    </AuthShell>
  )
}

export default function LoginPage() {
  return <Suspense fallback={<div className="min-h-screen bg-titan-950" />}><LoginInner /></Suspense>
}
