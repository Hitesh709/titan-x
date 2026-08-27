"use client"

import { useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Suspense } from "react"
import api from "@/lib/api"

function MobileAuthBridge() {
  const params = useSearchParams()
  const challenge = params.get("challenge") || ""
  const flow = params.get("flow") === "registration" ? "registration" : "login"
  const isRegistration = flow === "registration"
  const [state, setState] = useState<"idle" | "working" | "success" | "error">("idle")
  const [message, setMessage] = useState("")

  useEffect(() => {
    if (!challenge || !isRegistration) return
    let cancelled = false
    setState("working")
    api.post<{ status: string; email_otp_required: boolean; message: string }>("/auth/qr/register/scan", { challenge_id: challenge })
      .then(data => {
        if (cancelled) return
        setState("success")
        setMessage(data.message)
      })
      .catch(err => {
        if (cancelled) return
        setState("error")
        setMessage(err instanceof Error ? err.message : "Unable to process this QR code")
      })
    return () => { cancelled = true }
  }, [challenge, isRegistration])

  if (!challenge) return <main className="min-h-screen bg-titan-950 text-white flex items-center justify-center p-6"><div className="max-w-md text-center"><h1 className="text-2xl font-bold">Invalid QR Code</h1><p className="mt-3 text-gray-400">This QR authentication link is missing its challenge.</p></div></main>

  return <main className="min-h-screen bg-titan-950 text-white flex items-center justify-center p-6"><div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/5 p-8 text-center shadow-2xl"><h1 className="text-2xl font-bold">{isRegistration ? "Confirm Sign Up" : "Confirm Login"}</h1>{isRegistration ? <><p className="mt-3 text-gray-400">You scanned a secure Titan-X registration QR. The QR is one-time and expires in 2 minutes.</p>{state === "working" && <div className="mt-6 rounded-xl border border-white/10 bg-black/20 p-4 text-sm text-gray-300">Processing QR and sending the email verification code…</div>}{state === "success" && <div className="mt-6 rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-5"><p className="font-semibold text-emerald-300">✓ QR verified</p><p className="mt-2 text-sm text-gray-300">{message}</p><p className="mt-2 text-sm text-gray-400">Return to your browser and enter the email OTP.</p></div>}{state === "error" && <div className="mt-6 rounded-xl border border-red-400/30 bg-red-400/10 p-5 text-sm text-red-300">{message}</div>}</> : <div className="mt-6 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-200">QR login remains available through the existing login authentication flow. Registered-phone approval will be added separately; this temporary signup change does not weaken existing login security.</div>}<p className="mt-6 text-xs text-gray-500">Never share a QR authentication link.</p></div></main>
}

export default function MobileAuthPage() {
  return <Suspense fallback={<main className="min-h-screen bg-titan-950" />}><MobileAuthBridge /></Suspense>
}
