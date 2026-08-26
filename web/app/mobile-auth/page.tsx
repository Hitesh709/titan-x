"use client"

import { useSearchParams } from "next/navigation"
import { Suspense } from "react"
import { Smartphone, ShieldCheck } from "lucide-react"

function MobileAuthBridge() {
  const params = useSearchParams()
  const challenge = params.get("challenge")
  return <main className="min-h-screen bg-titan-950 text-white flex items-center justify-center p-6"><div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/5 p-8 text-center shadow-2xl"><ShieldCheck className="mx-auto mb-5 h-12 w-12 text-titan-400" /><h1 className="text-2xl font-bold">Xecaps Mobile Login</h1><p className="mt-3 text-gray-400">This QR request must be approved from your registered Xecaps mobile app. Scanning alone never approves the login.</p>{challenge ? <div className="mt-6 rounded-xl border border-white/10 bg-black/20 p-4"><Smartphone className="mx-auto mb-3 h-8 w-8 text-gray-300" /><p className="text-sm text-gray-300">Open your registered mobile app to review and approve this login request.</p></div> : <p className="mt-6 text-sm text-red-300">Invalid or missing login challenge.</p>}<p className="mt-6 text-xs text-gray-500">If the mobile app is not installed, return to the login page and choose another method.</p></div></main>
}

export default function MobileAuthPage() { return <Suspense fallback={<main className="min-h-screen bg-titan-950" />}><MobileAuthBridge /></Suspense> }
