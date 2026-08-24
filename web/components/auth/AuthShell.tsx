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
    <div className="min-h-screen flex">
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <Link href="/" className="flex items-center mb-8" aria-label="TITAN X home">
              <img src="/titan-x-logo.svg" alt="TITAN X — AI · DATA · SPEED · PRECISION" className="h-14 w-auto object-contain" />
            </Link>
            <h1 className="text-2xl font-bold text-white">{title}</h1>
            <p className="text-gray-500 mt-1">{subtitle}</p>
          </div>
          {children}
        </div>
      </div>

      <div className="hidden lg:flex flex-1 bg-gradient-to-br from-titan-900 to-titan-950 items-center justify-center p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-titan-600/20 via-transparent to-transparent" />
        <div className="relative text-center max-w-md">
          {aside}
        </div>
      </div>
    </div>
  )
}
