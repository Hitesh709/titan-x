"use client"

import { useState } from "react"
import Link from "next/link"
import { KeyRound } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { AuthShell } from "@/components/auth/AuthShell"
import { SubmitButton, FormError } from "@/components/auth/fields"

export default function ForgotPasswordPage() {
  const { forgotPassword } = useAuth()
  const [email, setEmail] = useState("")
  const [error, setError] = useState("")
  const [resetUrl, setResetUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setResetUrl(null)
    setLoading(true)
    try {
      const res = await forgotPassword(email)
      setResetUrl(res.reset_url ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong")
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      title="Forgot password"
      subtitle="We'll email you a link to reset your password"
      aside={
        <>
          <KeyRound className="w-16 h-16 text-titan-400 mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-white mb-3">Recover your account</h2>
          <p className="text-gray-400 leading-relaxed">
            If an account exists for your email, a secure reset link will be sent to you. Links expire after 30 minutes.
          </p>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormError message={error} />

        {resetUrl && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
              Reset link generated. Click below to set a new password.
            </div>
            <a href={resetUrl} className="btn-primary w-full justify-center">
              Reset Password
            </a>
          </div>
        )}

        {!resetUrl && (
          <>
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

            <SubmitButton loading={loading} loadingText="Sending link...">
              Send Reset Link
            </SubmitButton>
          </>
        )}
      </form>

      <p className="mt-6 text-center text-sm text-gray-500">
        Remembered your password?{" "}
        <Link href="/login" className="text-titan-400 hover:text-titan-300 font-medium">
          Sign in
        </Link>
      </p>
    </AuthShell>
  )
}
