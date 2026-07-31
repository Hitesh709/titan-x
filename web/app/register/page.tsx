"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Shield, MailCheck, Loader2 } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { AuthShell } from "@/components/auth/AuthShell"
import { PasswordField, SubmitButton, FormError } from "@/components/auth/fields"

export default function RegisterPage() {
  const { register, login, sendVerification, isAuthenticated } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [verificationUrl, setVerificationUrl] = useState<string | null>(null)
  const [resending, setResending] = useState(false)

  useEffect(() => {
    if (isAuthenticated) {
      router.replace("/dashboard")
    }
  }, [isAuthenticated, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (password !== confirmPassword) {
      setError("Passwords do not match")
      return
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters")
      return
    }

    setLoading(true)
    try {
      await register(email, password)
      await login(email, password, true)
      try {
        const res = await sendVerification(email)
        setVerificationUrl(res.verification_url ?? null)
      } catch {
        setVerificationUrl(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed")
      setLoading(false)
    }
  }

  const handleResend = async () => {
    setResending(true)
    setError("")
    try {
      const res = await sendVerification(email)
      setVerificationUrl(res.verification_url ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend verification email")
    } finally {
      setResending(false)
    }
  }

  if (verificationUrl !== null) {
    return (
      <AuthShell
        title="Verify your email"
        subtitle="One more step before you're fully set up"
        aside={
          <>
            <MailCheck className="w-16 h-16 text-titan-400 mx-auto mb-6" />
            <h2 className="text-2xl font-bold text-white mb-3">Almost there</h2>
            <p className="text-gray-400 leading-relaxed">
              Confirm your email address to activate all TITAN X features, including alerts and secure account recovery.
            </p>
          </>
        }
      >
        <div className="space-y-4">
          <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
            Account created for <span className="font-medium">{email}</span>. Click below to verify your email address.
          </div>

          <a href={verificationUrl} className="btn-primary w-full justify-center">
            Verify Email Now
          </a>

          <p className="text-center text-sm text-gray-500">
            Didn&apos;t get the link?{" "}
            <button
              type="button"
              onClick={handleResend}
              disabled={resending}
              className="text-titan-400 hover:text-titan-300 font-medium disabled:opacity-50"
            >
              {resending ? <Loader2 size={14} className="inline animate-spin" /> : "Resend"}
            </button>
          </p>

          <Link href="/dashboard" className="btn-secondary w-full justify-center">
            Skip for now — Go to Dashboard
          </Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start your 14-day free trial"
      aside={
        <>
          <Shield className="w-16 h-16 text-titan-400 mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-white mb-3">Enterprise-Grade Security</h2>
          <p className="text-gray-400 leading-relaxed">
            Your data is protected with bank-grade encryption, SOC 2 compliant infrastructure, and secure session management.
          </p>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormError message={error} />

        <div>
          <label htmlFor="email" className="block text-sm font-medium text-gray-400 mb-1.5">
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input-field"
            placeholder="you@company.com"
            autoComplete="email"
            required
          />
        </div>

        <PasswordField
          id="password"
          label="Password"
          value={password}
          onChange={setPassword}
          placeholder="Min. 8 characters"
          autoComplete="new-password"
        />

        <PasswordField
          id="confirm-password"
          label="Confirm Password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          placeholder="Repeat your password"
          autoComplete="new-password"
        />

        <div className="text-xs text-gray-500 leading-relaxed">
          By creating an account, you agree to our{" "}
          <a href="#" className="text-titan-400 hover:text-titan-300">Terms of Service</a> and{" "}
          <a href="#" className="text-titan-400 hover:text-titan-300">Privacy Policy</a>.
        </div>

        <SubmitButton loading={loading} loadingText="Creating account...">
          Create Account
        </SubmitButton>
      </form>

      <p className="mt-6 text-center text-sm text-gray-500">
        Already have an account?{" "}
        <Link href="/login" className="text-titan-400 hover:text-titan-300 font-medium">
          Sign in
        </Link>
      </p>
    </AuthShell>
  )
}
