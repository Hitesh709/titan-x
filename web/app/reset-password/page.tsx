"use client"

import { useState, useEffect, Suspense } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { ShieldCheck, CheckCircle2, AlertTriangle } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { AuthShell } from "@/components/auth/AuthShell"
import { PasswordField, SubmitButton, FormError } from "@/components/auth/fields"

function ResetPasswordInner() {
  const { resetPassword } = useAuth()
  const searchParams = useSearchParams()
  const token = searchParams.get("token") ?? ""
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!token) setError("Invalid or missing reset token. Please request a new reset link.")
  }, [token])

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
      await resetPassword(token, password)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password reset failed")
    } finally {
      setLoading(false)
    }
  }

  if (success) {
    return (
      <AuthShell
        title="Password reset"
        subtitle="Your password has been updated"
        aside={
          <>
            <ShieldCheck className="w-16 h-16 text-titan-400 mx-auto mb-6" />
            <h2 className="text-2xl font-bold text-white mb-3">You're all set</h2>
            <p className="text-gray-400 leading-relaxed">
              Your account is secure. Sign in with your new password to continue.
            </p>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
            <CheckCircle2 size={18} className="shrink-0" />
            Password changed successfully.
          </div>
          <Link href="/login" className="btn-primary w-full justify-center">
            Sign In
          </Link>
        </div>
      </AuthShell>
    )
  }

  if (!token) {
    return (
      <AuthShell
        title="Invalid link"
        subtitle="This reset link is missing or invalid"
        aside={
          <>
            <AlertTriangle className="w-16 h-16 text-titan-400 mx-auto mb-6" />
            <h2 className="text-2xl font-bold text-white mb-3">Link required</h2>
            <p className="text-gray-400 leading-relaxed">
              Use the link sent to your email, or request a new one.
            </p>
          </>
        }
      >
        <div className="space-y-4">
          <FormError message={error} />
          <Link href="/forgot-password" className="btn-primary w-full justify-center">
            Request New Link
          </Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Set a new password"
      subtitle="Choose a strong password for your account"
      aside={
        <>
          <ShieldCheck className="w-16 h-16 text-titan-400 mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-white mb-3">Secure your account</h2>
          <p className="text-gray-400 leading-relaxed">
            Use at least 8 characters with a mix of letters, numbers, and symbols.
          </p>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormError message={error} />

        <PasswordField
          id="new-password"
          label="New Password"
          value={password}
          onChange={setPassword}
          placeholder="Min. 8 characters"
          autoComplete="new-password"
        />

        <PasswordField
          id="confirm-new-password"
          label="Confirm New Password"
          value={confirmPassword}
          onChange={setConfirmPassword}
          placeholder="Repeat your new password"
          autoComplete="new-password"
        />

        <SubmitButton loading={loading} loadingText="Resetting...">
          Reset Password
        </SubmitButton>
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

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-titan-950" />}>
      <ResetPasswordInner />
    </Suspense>
  )
}
