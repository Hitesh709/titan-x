"use client"

import { useEffect, useState } from "react"
import { Bell, Crown, Key, Save, Shield, User } from "lucide-react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/contexts/AuthContext"
import api from "@/lib/api"

type Profile = {
  id: string | number
  username?: string | null
  email: string
  phone?: string | null
  role?: string
  is_active?: boolean
  is_verified?: boolean
  created_at?: string | null
}

type Subscription = {
  plan_code: string | null
  status: string
  expires_at?: string
  plan?: { name: string; price_inr: number } | null
}

const notificationSettings = [
  { label: "Email Notifications", desc: "Receive alerts via email", enabled: true },
  { label: "SMS Alerts", desc: "Critical alerts via SMS", enabled: false },
  { label: "Push Notifications", desc: "Browser push notifications", enabled: true },
  { label: "Weekly Report", desc: "Weekly portfolio summary", enabled: true },
]

export default function SettingsPage() {
  const { user, loading: authLoading } = useAuth()
  const router = useRouter()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [username, setUsername] = useState("")
  const [phone, setPhone] = useState("")
  const [timeZone, setTimeZone] = useState("UTC")
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [notifications, setNotifications] = useState(notificationSettings)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState("")

  useEffect(() => {
    if (typeof window !== "undefined") setTimeZone(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC")
  }, [])

  useEffect(() => {
    if (authLoading || !user) return
    Promise.all([
      api.get<Profile>("/profile/me"),
      api.get<Subscription>("/subscriptions/me"),
    ]).then(([profileData, subscriptionData]) => {
      setProfile(profileData)
      setUsername(profileData.username || user.username || user.email.split("@")[0])
      setPhone(profileData.phone || user.phone || "")
      setSubscription(subscriptionData)
    }).catch(() => {
      setUsername(user.username || user.email.split("@")[0])
      setPhone(user.phone || "")
    })
  }, [authLoading, user])

  const saveProfile = async () => {
    if (!user || saving) return
    setSaving(true)
    setMessage("")
    try {
      const updated = await api.patch<Profile>("/profile/me", {
        username: username.trim(),
        phone: phone.trim() || null,
      })
      setProfile(updated)
      setMessage("Profile updated successfully")
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update profile")
    } finally {
      setSaving(false)
    }
  }

  const toggleNotification = (index: number) => {
    const updated = [...notifications]
    updated[index] = { ...updated[index], enabled: !updated[index].enabled }
    setNotifications(updated)
  }

  if (authLoading || !user) return null

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-gray-500 text-sm mt-1">Manage your Titan X account, profile, subscription and preferences.</p>
      </div>

      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><User size={16} className="text-titan-400" /> Profile</h3>
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="username" className="block text-xs text-gray-500 mb-1">Username</label>
            <input id="username" type="text" value={username} onChange={(e) => setUsername(e.target.value)} className="input-field text-sm" />
          </div>
          <div>
            <label htmlFor="email" className="block text-xs text-gray-500 mb-1">Email</label>
            <input id="email" type="email" value={profile?.email || user.email} readOnly className="input-field text-sm opacity-80 cursor-not-allowed" />
          </div>
          <div>
            <label htmlFor="phone" className="block text-xs text-gray-500 mb-1">Mobile</label>
            <input id="phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Add mobile number" className="input-field text-sm" />
          </div>
          <div>
            <label htmlFor="time_zone" className="block text-xs text-gray-500 mb-1">Time Zone</label>
            <input id="time_zone" type="text" value={timeZone} readOnly className="input-field text-sm opacity-80 cursor-not-allowed" />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button onClick={saveProfile} disabled={saving} className="btn-primary text-sm"><Save size={14} /> {saving ? "Saving..." : "Save Changes"}</button>
          {message && <span className="text-xs text-gray-400">{message}</span>}
        </div>
      </div>

      <div className="glass-card p-5 border border-titan-500/20">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2"><Crown size={16} className="text-titan-400" /> Subscription</h3>
          <button onClick={() => router.push("/dashboard/subscription")} className="btn-secondary text-xs">View Plans</button>
        </div>
        {subscription?.plan ? (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div><div className="text-xs text-gray-500 uppercase">Current plan</div><div className="text-lg font-semibold text-white mt-1">{subscription.plan.name} · ₹{subscription.plan.price_inr}/week</div></div>
            <div className="text-xs text-gray-400">{subscription.expires_at ? `Active until ${new Date(subscription.expires_at).toLocaleDateString("en-IN")}` : "Active"}</div>
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><div><div className="text-sm text-white">No active subscription</div><div className="text-xs text-gray-500 mt-1">Choose a Titan X recommendation tier to unlock premium recommendations.</div></div><button onClick={() => router.push("/dashboard/subscription")} className="btn-primary text-sm">Choose a Plan</button></div>
        )}
      </div>

      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Bell size={16} className="text-titan-400" /> Notifications</h3>
        <div className="space-y-3">{notifications.map((n, i) => <div key={n.label} className="flex items-center justify-between py-2"><div><div className="text-sm text-white">{n.label}</div><div className="text-xs text-gray-500">{n.desc}</div></div><button type="button" onClick={() => toggleNotification(i)} role="switch" aria-checked={n.enabled} aria-label={n.label} className={`relative w-10 h-5 rounded-full transition-colors ${n.enabled ? "bg-titan-500" : "bg-white/10"}`}><div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${n.enabled ? "left-5" : "left-0.5"}`} /></button></div>)}</div>
      </div>

      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Key size={16} className="text-titan-400" /> API Keys</h3>
        <div className="p-3 bg-white/5 rounded-lg"><div className="text-sm text-white">API key management</div><div className="text-xs text-gray-500 mt-1">Production keys are managed securely by Titan X.</div></div>
      </div>

      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2"><Shield size={16} className="text-titan-400" /> Security</h3>
        <div className="flex items-center justify-between py-2"><div><div className="text-sm text-white">Two-Factor Authentication</div><div className="text-xs text-gray-500">Add an extra layer of security</div></div><button className="btn-secondary text-sm">Enable</button></div>
      </div>
    </div>
  )
}
