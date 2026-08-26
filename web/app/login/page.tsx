"use client"

import { useCallback, useEffect, useState, Suspense } from "react"
import Link from "next/link"
import { QrCode, RefreshCw, Smartphone, TrendingUp, X } from "lucide-react"
import { useSearchParams } from "next/navigation"
import { useAuth } from "@/contexts/AuthContext"
import { AuthShell } from "@/components/auth/AuthShell"
import { PasswordField, SubmitButton, FormError, FormSuccess } from "@/components/auth/fields"
import api from "@/lib/api"
import type { User } from "@/types"

type QRCreateResponse = {
  challenge_id: string
  qr_data_url: string
  expires_at: string
  expires_in_seconds: number
  sms_number?: string | null
}

type QRStatusResponse = {
  status:
    | "PENDING"
    | "SCANNED"
    | "APPROVED"
    | "DECLINED"
    | "EXPIRED"
    | "CANCELLED"
    | "USED"
  access_token?: string | null
  refresh_token?: string | null
  user?: User | null
}

const QR_TERMINAL_STATES: QRStatusResponse["status"][] = [
  "DECLINED",
  "EXPIRED",
  "CANCELLED",
  "USED",
]

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
  const [qrMode, setQrMode] = useState(false)
  const [qr, setQr] = useState<QRCreateResponse | null>(null)
  const [qrStatus, setQrStatus] = useState<QRStatusResponse["status"] | null>(null)
  const [qrSeconds, setQrSeconds] = useState(0)

  useEffect(() => {
    if (searchParams.get("expired") === "1") {
      setNotice("Your session has expired. Please sign in again.")
    }
  }, [searchParams])

  useEffect(() => {
    if (isAuthenticated) {
      window.location.href = "/dashboard"
    }
  }, [isAuthenticated])

  const resetQr = useCallback(() => {
    setQr(null)
    setQrStatus(null)
    setQrSeconds(0)
    setError("")
  }, [])

  const createQr = useCallback(async () => {
    const identifier = email.trim()
    if (!identifier) {
      setError("Enter your user ID, email, or registered phone number first.")
      return
    }

    setError("")
    setNotice("")
    setLoading(true)

    try {
      const data = await api.post<QRCreateResponse>("/auth/qr/create", {
        identifier,
      })
      setQr(data)
      setQrStatus("PENDING")
      setQrSeconds(data.expires_in_seconds)
      setNotice(
        "Scan with any smartphone camera, then send the prefilled SMS from your registered mobile number.",
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create QR login")
    } finally {
      setLoading(false)
    }
  }, [email])

  useEffect(() => {
    if (
      !qrMode ||
      !qr ||
      qrSeconds <= 0 ||
      QR_TERMINAL_STATES.includes(qrStatus || "PENDING")
    ) {
      return
    }

    const timer = window.setInterval(() => {
      setQrSeconds((value) => Math.max(0, value - 1))
    }, 1000)

    return () => window.clearInterval(timer)
  }, [qrMode, qr, qrSeconds, qrStatus])

  useEffect(() => {
    if (
      !qrMode ||
      !qr ||
      qrSeconds <= 0 ||
      QR_TERMINAL_STATES.includes(qrStatus || "PENDING")
    ) {
      return
    }

    const poll = window.setInterval(async () => {
      try {
        const data = await api.get<QRStatusResponse>(
          `/auth/qr/status/${encodeURIComponent(qr.challenge_id)}`,
        )
        setQrStatus(data.status)

        if (data.status === "USED" && data.access_token && data.refresh_token) {
          api.setToken(data.access_token)
          api.setRefreshToken(data.refresh_token)
          setNotice("Login approved. Signing you in...")
          window.setTimeout(() => {
            window.location.href = "/dashboard"
          }, 350)
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : ""
        if (message.toLowerCase().includes("expired")) {
          setQrStatus("EXPIRED")
        }
      }
    }, 1500)

    return () => window.clearInterval(poll)
  }, [qrMode, qr, qrSeconds, qrStatus])

  useEffect(() => {
    if (
      qrMode &&
      qrSeconds === 0 &&
      qrStatus &&
      ["PENDING", "SCANNED"].includes(qrStatus)
    ) {
      setQrStatus("EXPIRED")
    }
  }, [qrMode, qrSeconds, qrStatus])

  const cancelQr = async () => {
    if (!qr) return

    try {
      await api.post("/auth/qr/cancel", { challenge_id: qr.challenge_id })
    } catch {
      // The local state is still reset even if the cancellation request fails.
    }

    resetQr()
    setQrMode(false)
    setNotice("")
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    setNotice("")
    setLoading(true)

    try {
      await login(email, password, remember)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed"
      if (message.startsWith("MFA_REQUIRED:")) {
        setMfaChallenge(message.slice("MFA_REQUIRED:".length))
        setMfaRequired(true)
        setNotice("Enter your authenticator code or a recovery code.")
      } else {
        setError(message)
      }
    } finally {
      setLoading(false)
    }
  }

  const handleMfa = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    setLoading(true)

    try {
      await completeMfaLogin(mfaChallenge, mfaCode.trim())
    } catch (err) {
      setError(err instanceof Error ? err.message : "MFA verification failed")
    } finally {
      setLoading(false)
    }
  }

  const title = mfaRequired
    ? "Two-factor verification"
    : qrMode
      ? "Login with Mobile QR"
      : "Welcome back"

  const subtitle = mfaRequired
    ? "Verify your identity to continue"
    : qrMode
      ? "Scan with any smartphone and verify by SMS"
      : "Sign in to your TITAN X account"

  const aside = (
    <>
      <TrendingUp className="w-16 h-16 text-titan-400 mx-auto mb-6" />
      <h2 className="text-2xl font-bold text-white mb-3">
        AI-Powered Market Intelligence
      </h2>
      <p className="text-gray-400 leading-relaxed">
        Access real-time analytics, predictive models, and automated trading
        strategies — all from a single, secure platform.
      </p>
    </>
  )

  return (
    <AuthShell title={title} subtitle={subtitle} aside={aside}>
      {mfaRequired ? (
        <form onSubmit={handleMfa} className="space-y-4">
          <FormError message={error} />
          <FormSuccess message={notice} />
          <input
            id="mfa-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={mfaCode}
            onChange={(event) => setMfaCode(event.target.value)}
            className="input-field tracking-widest"
            placeholder="123456 or recovery code"
            minLength={6}
            maxLength={64}
            required
          />
          <SubmitButton loading={loading} loadingText="Verifying...">
            Verify &amp; Sign In
          </SubmitButton>
          <button
            type="button"
            onClick={() => {
              setMfaRequired(false)
              setMfaChallenge("")
              setMfaCode("")
              setError("")
              setNotice("")
            }}
            className="w-full text-sm text-gray-400 hover:text-white"
          >
            Back to password login
          </button>
        </form>
      ) : qrMode ? (
        <div className="space-y-4">
          <FormError message={error} />
          <FormSuccess message={notice} />

          {!qr ? (
            <>
              <div>
                <label
                  htmlFor="qr-identifier"
                  className="block text-sm font-medium text-gray-400 mb-1.5"
                >
                  User ID / Email / Registered Phone
                </label>
                <input
                  id="qr-identifier"
                  type="text"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="input-field"
                  placeholder="Enter your user ID, email, or phone"
                  autoComplete="username"
                  autoFocus
                  required
                />
                <p className="mt-1.5 text-xs text-gray-500">
                  Enter the identifier belonging to your registered account.
                </p>
              </div>

              <button
                type="button"
                onClick={createQr}
                disabled={loading || !email.trim()}
                className="w-full rounded-xl border border-titan-500/40 bg-titan-500/10 py-3 text-titan-300 disabled:opacity-50"
              >
                <QrCode className="inline-block mr-2 h-5 w-5" />
                {loading ? "Generating secure QR..." : "Generate secure QR"}
              </button>
            </>
          ) : (
            <>
              <div className="rounded-2xl bg-white p-4 mx-auto w-fit shadow-xl">
                <img
                  src={qr.qr_data_url}
                  alt="One-time login QR code"
                  className="w-56 h-56"
                />
              </div>

              <div className="text-center text-sm text-gray-400">
                <div className="font-medium text-white">
                  {qrStatus === "USED"
                    ? "LOGIN APPROVED"
                    : qrStatus === "DECLINED"
                      ? "LOGIN REQUEST DECLINED"
                      : qrStatus === "EXPIRED"
                        ? "QR CODE EXPIRED"
                        : "Scan with any smartphone camera"}
                </div>
                <div className="mt-1">
                  {qrStatus === "PENDING"
                    ? `Expires in ${String(Math.floor(qrSeconds / 60)).padStart(2, "0")}:${String(qrSeconds % 60).padStart(2, "0")}`
                    : qrStatus === "DECLINED"
                      ? "No web session was created."
                      : qrStatus === "EXPIRED"
                        ? "Generate a new QR code."
                        : qrStatus !== "USED"
                          ? "Your phone will open a secure page and send the verification SMS."
                          : "Signing you in..."}
                </div>
              </div>

              {["EXPIRED", "DECLINED"].includes(qrStatus || "") ? (
                <button
                  type="button"
                  onClick={resetQr}
                  className="w-full rounded-xl border border-white/10 py-3 text-gray-300"
                >
                  <RefreshCw className="inline-block mr-2 h-4 w-4" />
                  Generate New QR
                </button>
              ) : (
                <button
                  type="button"
                  onClick={cancelQr}
                  className="w-full rounded-xl border border-white/10 py-3 text-gray-400"
                >
                  <X className="inline-block mr-2 h-4 w-4" />
                  Cancel
                </button>
              )}
            </>
          )}

          <button
            type="button"
            onClick={() => {
              void cancelQr()
            }}
            className="w-full text-sm text-gray-400 hover:text-white"
          >
            <Smartphone className="inline-block mr-1 h-4 w-4" />
            Login another way
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <FormError message={error} />
          <FormSuccess message={notice} />

          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-400 mb-1.5"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
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
            placeholder="Enter your password"
            autoComplete="current-password"
          />

          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
                className="rounded border-gray-600 bg-white/5"
              />
              Remember me
            </label>
            <Link
              href="/forgot-password"
              className="text-titan-400 hover:text-titan-300"
            >
              Forgot password?
            </Link>
          </div>

          <SubmitButton loading={loading} loadingText="Signing in...">
            Sign In
          </SubmitButton>

          <button
            type="button"
            onClick={() => {
              setQrMode(true)
              resetQr()
            }}
            className="w-full rounded-xl border border-titan-500/30 bg-titan-500/5 py-3 text-titan-300 hover:bg-titan-500/10"
          >
            <QrCode className="inline-block mr-2 h-5 w-5" />
            Login with Mobile QR
          </button>
        </form>
      )}

      {!mfaRequired && !qrMode && (
        <p className="mt-6 text-center text-sm text-gray-500">
          Don&apos;t have an account?{" "}
          <Link
            href="/register"
            className="text-titan-400 hover:text-titan-300 font-medium"
          >
            Create one
          </Link>
        </p>
      )}
    </AuthShell>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-titan-950" />}>
      <LoginInner />
    </Suspense>
  )
}
