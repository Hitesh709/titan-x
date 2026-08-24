"use client"

import Link from "next/link"
import type { ReactNode } from "react"

export function AuthShell({
  title,
  subtitle,
  children,
  aside,
}: {
  title: string
  subtitle: string
  children: ReactNode
  aside?: ReactNode
}) {
  return (
    <div className="auth-titan-shell min-h-screen flex">
      <div className="relative z-10 flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <Link href="/" className="flex items-center mb-8" aria-label="TITAN X home">
              <img src="/titan-x-logo.svg" alt="TITAN X — AI · DATA · SPEED · PRECISION" className="h-14 w-auto object-contain drop-shadow-[0_0_18px_rgba(65,135,255,.25)]" />
            </Link>
            <div className="mb-5 h-px bg-gradient-to-r from-cyan-400/30 via-violet-500/20 to-transparent" />
            <h1 className="text-2xl font-bold text-white tracking-tight">{title}</h1>
            <p className="text-gray-500 mt-1">{subtitle}</p>
          </div>
          <div className="relative rounded-2xl border border-cyan-400/10 bg-slate-950/60 backdrop-blur-xl p-5 shadow-[0_25px_80px_rgba(0,0,0,.35)]">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-cyan-400/40 via-blue-500/20 to-transparent" />
            {children}
          </div>
        </div>
      </div>

      <div className="hidden lg:flex relative z-10 flex-1 items-center justify-center p-12 overflow-hidden border-l border-cyan-400/10 bg-slate-950/25">
        <div className="absolute inset-0 opacity-40 bg-[linear-gradient(rgba(56,189,248,.035)_1px,transparent_1px),linear-gradient(90deg,rgba(56,189,248,.035)_1px,transparent_1px)] bg-[size:42px_42px]" />
        <div className="absolute w-[34rem] h-[34rem] rounded-full bg-blue-600/10 blur-3xl" />
        <div className="relative text-center max-w-md rounded-3xl border border-cyan-400/10 bg-slate-950/35 backdrop-blur-md p-10 shadow-[0_30px_100px_rgba(0,0,0,.35)]">
          <div className="mx-auto mb-6 h-px w-32 bg-gradient-to-r from-transparent via-cyan-400/60 to-transparent" />
          {aside}
          <div className="mx-auto mt-8 h-px w-48 bg-gradient-to-r from-transparent via-violet-400/30 to-transparent" />
          <div className="mt-5 flex justify-center gap-2 text-[9px] font-mono tracking-[.18em] text-slate-600">
            <span>AI</span><span>•</span><span>DATA</span><span>•</span><span>SPEED</span><span>•</span><span>PRECISION</span>
          </div>
        </div>
      </div>
    </div>
  )
}