"use client"

import { useState } from "react"
import { Settings, User, Bell, Shield, Key, Palette, Save } from "lucide-react"

const notificationSettings = [
  { label: "Email Notifications", desc: "Receive alerts via email", enabled: true },
  { label: "SMS Alerts", desc: "Critical alerts via SMS", enabled: false },
  { label: "Push Notifications", desc: "Browser push notifications", enabled: true },
  { label: "Weekly Report", desc: "Weekly portfolio summary", enabled: true },
]

const apiKeys = [
  { name: "Production API Key", key: "tx_live_8a7f...3b2d", created: "2024-01-15", lastUsed: "2024-06-12" },
  { name: "Development Key", key: "tx_test_4c9e...1f6a", created: "2024-03-22", lastUsed: "2024-06-11" },
]

export default function SettingsPage() {
  const [notifications, setNotifications] = useState(notificationSettings)

  const toggleNotification = (index: number) => {
    const updated = [...notifications]
    updated[index] = { ...updated[index], enabled: !updated[index].enabled }
    setNotifications(updated)
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-gray-500 text-sm mt-1">Manage your account, preferences, and API keys</p>
      </div>

      {/* Profile */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <User size={16} className="text-titan-400" /> Profile
        </h3>
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="full_name" className="block text-xs text-gray-500 mb-1">Full Name</label>
            <input id="full_name" type="text" className="input-field text-sm" defaultValue="John Doe" />
          </div>
          <div>
            <label htmlFor="email" className="block text-xs text-gray-500 mb-1">Email</label>
            <input id="email" type="email" className="input-field text-sm" defaultValue="john@example.com" />
          </div>
          <div>
            <label htmlFor="company" className="block text-xs text-gray-500 mb-1">Company</label>
            <input id="company" type="text" className="input-field text-sm" defaultValue="Acme Investments" />
          </div>
          <div>
            <label htmlFor="time_zone" className="block text-xs text-gray-500 mb-1">Time Zone</label>
            <select id="time_zone" className="input-field text-sm">
              <option>America/New_York (EST)</option>
              <option>America/Chicago (CST)</option>
              <option>America/Los_Angeles (PST)</option>
              <option>Europe/London (GMT)</option>
              <option>Asia/Singapore (SGT)</option>
            </select>
          </div>
        </div>
        <div className="mt-4">
          <button className="btn-primary text-sm"><Save size={14} /> Save Changes</button>
        </div>
      </div>

      {/* Notifications */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Bell size={16} className="text-titan-400" /> Notifications
        </h3>
        <div className="space-y-3">
          {notifications.map((n, i) => (
            <div key={n.label} className="flex items-center justify-between py-2">
              <div>
                <div className="text-sm text-white">{n.label}</div>
                <div className="text-xs text-gray-500">{n.desc}</div>
              </div>
              <button
                type="button"
                onClick={() => toggleNotification(i)}
                role="switch"
                aria-checked={n.enabled}
                aria-label={n.label}
                className={`relative w-10 h-5 rounded-full transition-colors ${
                  n.enabled ? "bg-titan-500" : "bg-white/10"
                }`}
              >
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                  n.enabled ? "left-5" : "left-0.5"
                }`} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* API Keys */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Key size={16} className="text-titan-400" /> API Keys
        </h3>
        <div className="space-y-4">
          {apiKeys.map((k) => (
            <div key={k.name} className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
              <div>
                <div className="text-sm text-white">{k.name}</div>
                <div className="text-xs font-mono text-gray-500 mt-0.5">{k.key}</div>
                <div className="text-[10px] text-gray-600 mt-1">Created: {k.created} · Last used: {k.lastUsed}</div>
              </div>
              <button className="btn-ghost text-xs">Revoke</button>
            </div>
          ))}
          <button className="btn-secondary text-sm mt-2"><Key size={14} /> Generate New Key</button>
        </div>
      </div>

      {/* Security */}
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <Shield size={16} className="text-titan-400" /> Security
        </h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between py-2">
            <div>
              <div className="text-sm text-white">Two-Factor Authentication</div>
              <div className="text-xs text-gray-500">Add an extra layer of security</div>
            </div>
            <button className="btn-secondary text-sm">Enable</button>
          </div>
          <div className="flex items-center justify-between py-2">
            <div>
              <div className="text-sm text-white">Session Timeout</div>
              <div className="text-xs text-gray-500">Auto-logout after inactivity</div>
            </div>
            <select className="input-field text-sm w-24">
              <option>15 min</option>
              <option>30 min</option>
              <option selected>1 hour</option>
              <option>4 hours</option>
              <option>Never</option>
            </select>
          </div>
          <div className="flex items-center justify-between py-2">
            <div>
              <div className="text-sm text-white">Change Password</div>
              <div className="text-xs text-gray-500">Last changed 3 months ago</div>
            </div>
            <button className="btn-secondary text-sm">Update</button>
          </div>
        </div>
      </div>
    </div>
  )
}
