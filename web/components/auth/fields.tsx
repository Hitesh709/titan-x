"use client"

import { useState } from "react"
import { Eye, EyeOff, Loader2 } from "lucide-react"

export function PasswordField({
  id,
  value,
  onChange,
  placeholder,
  label,
  autoComplete,
  showToggle = true,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  label?: string
  autoComplete?: string
  showToggle?: boolean
}) {
  const [show, setShow] = useState(false)
  return (
    <div>
      {label && (
        <label htmlFor={id} className="block text-sm font-medium text-gray-400 mb-1.5">
          {label}
        </label>
      )}
      <div className="relative">
        <input
          id={id}
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="input-field pr-10"
          placeholder={placeholder}
          autoComplete={autoComplete}
          required
        />
        {showToggle && (
          <button
            type="button"
            onClick={() => setShow(!show)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
            aria-label={show ? "Hide password" : "Show password"}
          >
            {show ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        )}
      </div>
    </div>
  )
}

export function SubmitButton({ loading, loadingText, children }: { loading: boolean; loadingText: string; children: React.ReactNode }) {
  return (
    <button type="submit" disabled={loading} className="btn-primary w-full">
      {loading ? <Loader2 size={16} className="animate-spin" /> : null}
      {loading ? loadingText : children}
    </button>
  )
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
      {message}
    </div>
  )
}

export function FormSuccess({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
      {message}
    </div>
  )
}
