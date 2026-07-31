"use client"

import { useState, useEffect, Suspense, useCallback } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { MailCheck, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"
import { AuthShell } from "@/components/auth/AuthShell"
import { decodeTokenPayload } from "@/lib/api"

function VerifyEmailInner() {
  const { verifyEmail, sendVerification } = useAuth()
  const searchParams = useSearchParams()
  const token = searchParams.get("token") ?? ""
  const payload = token ? decodeTokenPayload(token) : null
  const email = typeof payload?.email === "string" ? payload.email : ""
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading")
  const [message, setMessage] = useState("")

  const runVerification = useCallback(
    async (tokenValue: string) => {
      setStatus("loading")
      setMessage("")
      try {
        await verifyEmail(tokenValue)
        setStatus("success")
      } catch (err) {
        setStatus("error")
        setMessage(err instanceof Error ? err.message : "Verification failed")
      }
    },
    [verifyEmail]
  )

  useEffect(() => {
    if (token) {
      runVerification(token)
    } else {
      setStatus("error")
      setMessage("Missing verification token.")
    }
  }, [token, runVerification])

  const handleResend = async () => {
    setMessage("")
    try {
      const res = await sendVerification(email)
      if (res.verification_url) window.location.href = res.verification_url
      else setMessage("Verification email sent. Check your inbox.")
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not resend verification email")
    }
  }

  if (status === "loading") {
    return (
      <AuthShell
        title="Verifying your email"
        subtitle="Please wait while we confirm your email address"
        aside={
          <>
            <MailCheck className="w-16 h-16 text-titan-400 mx-auto mb-6" />
            <h2 className="text-2xl font-bold text-white mb-3">One moment</h2>
            <p className="text-gray-400 leading-relaxed">Verifying your email address...</p>
          </>
        }
      >
        <div className="flex items-center justify-center py-8">
          <Loader2 size={28} className="animate-spin text-titan-400" />
        </div>
      </AuthShell>
    )
  }

  if (status === "success") {
    return (
      <AuthShell
        title="Email verified"
        subtitle="Your email address has been confirmed"
        aside={
          <>
            <MailCheck className="w-16 h-16 text-titan-400 mx-auto mb-6" />
            <h2 className="text-2xl font-bold text-white mb-3">All set</h2>
            <p className="text-gray-400 leading-relaxed">
              Your email is verified. You can now access all TITAN X features.
            </p>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
            <CheckCircle2 size={18} className="shrink-0" />
            Your email has been verified successfully.
          </div>
          <Link href="/dashboard" className="btn-primary w-full justify-center">
            Go to Dashboard
          </Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Verification failed"
      subtitle="We couldn't verify your email"
      aside={
        <>
          <AlertTriangle className="w-16 h-16 text-titan-400 mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-white mb-3">Something went wrong</h2>
          <p className="text-gray-400 leading-relaxed">
            The verification link may be expired or invalid. Request a new one.
          </p>
        </>
      }
    >
      <div className="space-y-4">
        <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {message}
        </div>
        <Link href="/login" className="btn-primary w-full justify-center">
          Sign In
        </Link>
        <p className="text-center text-sm text-gray-500">
          Need a new link?{" "}
          <button type="button" onClick={handleResend} className="text-titan-400 hover:text-titan-300 font-medium">
            Resend verification
          </button>
        </p>
      </div>
    </AuthShell>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-titan-950" />}>
      <VerifyEmailInner />
    </Suspense>
  )
}
