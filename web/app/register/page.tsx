"use client"

import { useState } from "react"
import Link from "next/link"
import { useAuth } from "@/contexts/AuthContext"
import { Eye, EyeOff, Shield, Loader2 } from "lucide-react"

export default function RegisterPage() {
  const { register } = useAuth()
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

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
      await register(email, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-1 bg-gradient-to-br from-titan-900 to-titan-950 items-center justify-center p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-titan-600/20 via-transparent to-transparent" />
        <div className="relative text-center max-w-md">
          <Shield className="w-16 h-16 text-titan-400 mx-auto mb-6" />
          <h2 className="text-2xl font-bold text-white mb-3">Enterprise-Grade Security</h2>
          <p className="text-gray-400 leading-relaxed">
            Your data is protected with bank-grade encryption, SOC 2 compliant infrastructure, and multi-factor authentication.
          </p>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <Link href="/" className="flex items-center gap-2 mb-8">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-titan-500 to-titan-700 flex items-center justify-center">
                <span className="text-white font-bold text-xs">TX</span>
              </div>
              <span className="text-lg font-bold text-white">TITAN <span className="text-titan-400">X</span></span>
            </Link>
            <h1 className="text-2xl font-bold text-white">Create your account</h1>
            <p className="text-gray-500 mt-1">Start your 14-day free trial</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Full Name</label>
              <input type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} className="input-field" placeholder="John Doe" required />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input-field" placeholder="you@company.com" required />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Password</label>
              <div className="relative">
                <input type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} className="input-field pr-10" placeholder="Min. 8 characters" required />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1.5">Confirm Password</label>
              <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="input-field" placeholder="Repeat your password" required />
            </div>

            <div className="text-xs text-gray-500 leading-relaxed">
              By creating an account, you agree to our{" "}
              <a href="#" className="text-titan-400 hover:text-titan-300">Terms of Service</a> and{" "}
              <a href="#" className="text-titan-400 hover:text-titan-300">Privacy Policy</a>.
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? <Loader2 size={16} className="animate-spin" /> : null}
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-gray-500">
            Already have an account?{" "}
            <Link href="/login" className="text-titan-400 hover:text-titan-300 font-medium">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  )
}
