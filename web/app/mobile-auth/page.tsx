"use client"

import { useSearchParams } from "next/navigation"
import { Suspense } from "react"

function MobileAuthBridge() {
  const params = useSearchParams()
  const challenge = params.get("challenge") || ""
  const smsNumber = process.env.NEXT_PUBLIC_QR_SMS_NUMBER || ""
  const smsHref = challenge && smsNumber ? `sms:${smsNumber}?body=${encodeURIComponent(`TXQR:${challenge}`)}` : ""

  return <main className="min-h-screen bg-titan-950 text-white flex items-center justify-center p-6"><div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/5 p-8 text-center shadow-2xl"><h1 className="text-2xl font-bold">Confirm Login</h1><p className="mt-3 text-gray-400">Your camera has opened the secure Titan-X verification page. Sending the prefilled SMS from your registered phone approves this one-time request.</p>{challenge && smsHref ? <><div className="mt-6 rounded-xl border border-white/10 bg-black/20 p-4 text-left"><p className="text-sm text-gray-300">1. Confirm this is your login or registration request.</p><p className="mt-2 text-sm text-gray-300">2. Tap the button below.</p><p className="mt-2 text-sm text-gray-300">3. Send the prefilled SMS without changing its contents.</p></div><a href={smsHref} className="mt-6 block w-full rounded-xl bg-titan-500 px-4 py-3 font-semibold text-white">Approve by SMS</a></> : <div className="mt-6 rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-200">SMS verification is not configured. Please contact the administrator.</div>}<p className="mt-6 text-xs text-gray-500">Never share or forward the QR challenge or verification SMS.</p></div></main>
}

export default function MobileAuthPage() { return <Suspense fallback={<main className="min-h-screen bg-titan-950" />}><MobileAuthBridge /></Suspense> }
