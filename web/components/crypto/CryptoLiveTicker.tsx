"use client"

import { useEffect, useRef, useState } from "react"

type Tick = {
  symbol: string
  price: number
  changePercent: number
  eventTime: number
}

const COINS = [
  "BTCUSDT",
  "ETHUSDT",
  "SOLUSDT",
  "BNBUSDT",
  "XRPUSDT",
  "DOGEUSDT",
  "ADAUSDT",
  "AVAXUSDT",
]

const STREAM_RENEW_MS = 23 * 60 * 60 * 1000 + 50 * 60 * 1000
const MAX_RETRY_MS = 30_000

function buildStreamUrl() {
  const streams = COINS.map((s) => s.toLowerCase() + "@miniTicker").join("/")
  return "wss://stream.binance.com:9443/stream?streams=" + streams
}

function parseTick(payload: MessageEvent) {
  try {
    const j = JSON.parse(payload.data).data
    if (!j?.s) return null

    const open = Number(j.o)
    const close = Number(j.c)

    return {
      symbol: j.s,
      price: close,
      changePercent: open ? ((close - open) / open) * 100 : 0,
      eventTime: Number(j.E) || Date.now(),
    } satisfies Tick
  } catch {
    return null
  }
}

export function useCryptoLivePrices() {
  const [prices, setPrices] = useState<Record<string, Tick>>({})
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let dead = false
    let retry = 1000
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let renewalTimer: number | null = null

    const clearTimers = () => {
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      if (renewalTimer !== null) window.clearTimeout(renewalTimer)
      reconnectTimer = null
      renewalTimer = null
    }

    const connect = () => {
      if (dead) return

      socket = new WebSocket(buildStreamUrl())

      socket.onopen = () => {
        retry = 1000
        setConnected(true)

        // Binance market-stream connections are valid for 24 hours.
        // Reconnect proactively before the hard 24-hour disconnect.
        renewalTimer = window.setTimeout(() => {
          if (!dead && socket) socket.close()
        }, STREAM_RENEW_MS)
      }

      socket.onmessage = (event) => {
        const tick = parseTick(event)
        if (!tick) return
        setPrices((current) => ({ ...current, [tick.symbol]: tick }))
      }

      socket.onerror = () => {
        socket?.close()
      }

      socket.onclose = () => {
        if (renewalTimer !== null) {
          window.clearTimeout(renewalTimer)
          renewalTimer = null
        }

        setConnected(false)

        if (!dead) {
          const delay = Math.min(retry, MAX_RETRY_MS)
          reconnectTimer = window.setTimeout(connect, delay)
          retry = Math.min(retry * 2, MAX_RETRY_MS)
        }
      }
    }

    connect()

    return () => {
      dead = true
      clearTimers()
      socket?.close()
    }
  }, [])

  return { prices, connected }
}

export default function CryptoLiveTicker({
  onTick,
}: {
  onTick?: (tick: Tick) => void
}) {
  const [prices, setPrices] = useState<Record<string, Tick>>({})
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  const onTickRef = useRef(onTick)

  useEffect(() => {
    onTickRef.current = onTick
  }, [onTick])

  useEffect(() => {
    let dead = false
    let retry = 1000
    let reconnectTimer: number | null = null
    let renewalTimer: number | null = null

    const clearTimers = () => {
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      if (renewalTimer !== null) window.clearTimeout(renewalTimer)
      reconnectTimer = null
      renewalTimer = null
    }

    const connect = () => {
      if (dead) return

      const socket = new WebSocket(buildStreamUrl())
      socketRef.current = socket

      socket.onopen = () => {
        retry = 1000
        setConnected(true)

        renewalTimer = window.setTimeout(() => {
          if (!dead && socket.readyState === WebSocket.OPEN) socket.close()
        }, STREAM_RENEW_MS)
      }

      socket.onmessage = (event) => {
        const tick = parseTick(event)
        if (!tick) return

        setPrices((current) => ({ ...current, [tick.symbol]: tick }))
        onTickRef.current?.(tick)
      }

      socket.onerror = () => socket.close()

      socket.onclose = () => {
        if (renewalTimer !== null) {
          window.clearTimeout(renewalTimer)
          renewalTimer = null
        }

        if (socketRef.current === socket) socketRef.current = null
        setConnected(false)

        if (!dead) {
          const delay = Math.min(retry, MAX_RETRY_MS)
          reconnectTimer = window.setTimeout(connect, delay)
          retry = Math.min(retry * 2, MAX_RETRY_MS)
        }
      }
    }

    connect()

    return () => {
      dead = true
      clearTimers()
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [])

  return (
    <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider">
      <span
        className={
          "w-1.5 h-1.5 rounded-full " +
          (connected ? "bg-emerald-400" : "bg-amber-400")
        }
      />
      <span className={connected ? "text-emerald-300" : "text-amber-300"}>
        {connected ? "LIVE STREAM" : "RECONNECTING"}
      </span>
      <span className="text-slate-600">
        {Object.keys(prices).length}/{COINS.length}
      </span>
    </div>
  )
}
