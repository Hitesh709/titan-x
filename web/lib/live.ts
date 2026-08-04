"use client"

import { useEffect, useRef } from "react"

export const LIVE_REFRESH_MS = 5_000
export const LIVE_REFRESH_EVENT = "titanx:live-refresh"

export function startLiveTicker(): () => void {
  if (typeof window === "undefined") return () => undefined
  const timer = window.setInterval(() => {
    window.dispatchEvent(new Event(LIVE_REFRESH_EVENT))
  }, LIVE_REFRESH_MS)
  return () => window.clearInterval(timer)
}

export function useLiveRefresh(callback: () => void, deps: unknown[]) {
  const cb = useRef(callback)
  cb.current = callback

  useEffect(() => {
    const run = () => cb.current()
    run()
    if (typeof window === "undefined") return
    window.addEventListener(LIVE_REFRESH_EVENT, run)
    return () => window.removeEventListener(LIVE_REFRESH_EVENT, run)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
