"use client"

import { useEffect, useState } from "react"
import { Check, Crown, Shield, Zap } from "lucide-react"
import api from "@/lib/api"

type Plan = {
  code: string
  name: string
  price_inr: number
  billing_period: string
  technical_min: number
  technical_max: number
  risk_levels: string[]
  description: string
}

type SubscriptionResponse = { plan_code: string | null; status: string; expires_at?: string; plan?: Plan | null }

const fallbackPlans: Plan[] = [
  { code: "TITAN_99", name: "Titan 99", price_inr: 99, billing_period: "weekly", technical_min: 75, technical_max: 80, risk_levels: ["Low", "Medium", "High"], description: "Technical Pillar 75–80 only." },
  { code: "TITAN_499", name: "Titan 499", price_inr: 499, billing_period: "weekly", technical_min: 81, technical_max: 90, risk_levels: ["Medium"], description: "Technical Pillar 81–90 with Medium risk only." },
  { code: "TITAN_999", name: "Titan 999", price_inr: 999, billing_period: "weekly", technical_min: 90, technical_max: 100, risk_levels: ["Low", "Medium", "High"], description: "Technical Pillar 90–100 across Low, Medium and High risk." },
]

export default function SubscriptionPage() {
  const [plans, setPlans] = useState<Plan[]>(fallbackPlans)
  const [current, setCurrent] = useState<SubscriptionResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.get<{ plans: Plan[] }>("/subscriptions/plans"),
      api.get<SubscriptionResponse>("/subscriptions/me"),
    ]).then(([planResponse, subscription]) => {
      if (planResponse.plans?.length) setPlans(planResponse.plans)
      setCurrent(subscription)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2"><Crown size={20} className="text-titan-400" /><h1 className="text-2xl font-bold text-white">Titan X Premium</h1></div>
        <p className="text-gray-500 text-sm mt-1">Unlock recommendation tiers matched to Technical Pillar strength and risk.</p>
      </div>

      {current?.plan && <div className="glass-card p-4 border border-titan-500/25"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="text-xs text-gray-500 uppercase tracking-wider">Current plan</div><div className="text-lg font-semibold text-white mt-1">{current.plan.name} · ₹{current.plan.price_inr}/week</div></div><div className="text-xs text-gray-400">Active until {current.expires_at ? new Date(current.expires_at).toLocaleDateString("en-IN") : "—"}</div></div></div>}

      <div className="grid md:grid-cols-3 gap-5">
        {plans.map((plan, index) => {
          const isCurrent = current?.plan_code === plan.code && current.status === "active"
          return <div key={plan.code} className={`glass-card p-5 flex flex-col ${index === 2 ? "border border-titan-500/40" : "border border-white/5"}`}>
            <div className="flex items-center justify-between"><div><div className="text-sm font-semibold text-white">{plan.name}</div><div className="mt-2 text-3xl font-bold text-white">₹{plan.price_inr}<span className="text-xs font-normal text-gray-500"> / week</span></div></div>{index === 2 ? <Zap size={20} className="text-titan-400" /> : <Shield size={20} className="text-gray-500" />}</div>
            <div className="mt-5 space-y-3 text-sm text-gray-300 flex-1">
              <div className="flex gap-2"><Check size={15} className="text-emerald-400 mt-0.5 shrink-0" />Technical Pillar <b>{plan.technical_min}–{plan.technical_max}</b></div>
              <div className="flex gap-2"><Check size={15} className="text-emerald-400 mt-0.5 shrink-0" />Risk: <b>{plan.risk_levels.join(", ")}</b></div>
              <p className="text-xs text-gray-500 pt-1">{plan.description}</p>
            </div>
            <button disabled={isCurrent || loading} className={`mt-6 w-full ${isCurrent ? "btn-secondary" : "btn-primary"}`}>{isCurrent ? "Current Plan" : "Subscribe"}</button>
            {!isCurrent && <p className="text-[10px] text-gray-600 text-center mt-2">Payment activation will be connected to the subscription provider.</p>}
          </div>
        })}
      </div>

      <div className="glass-card p-4 text-xs text-gray-500 border border-white/5">
        <b className="text-gray-300">Recommendation entitlement:</b> Titan 99 never receives scores above 80; Titan 499 never receives scores above 90 and excludes Low-risk recommendations; Titan 999 receives scores from 90–100 across Low, Medium and High risk.
      </div>
    </div>
  )
}
