"use client"

import { useEffect, useMemo, useState } from "react"
import { createPortal } from "react-dom"
import { usePublicMarket } from "./MarketTicker"
import NiftyHeatmap from "./NiftyHeatmap"

function LandingLiveOverlay() {
  const { markets, score, regime } = usePublicMarket()
  const [targets, setTargets] = useState<{ sentiment: HTMLElement | null; chart: HTMLElement | null; news: HTMLElement | null }>({ sentiment: null, chart: null, news: null })

  const live = useMemo(() => markets.filter((m: any) => typeof m.change_pct === "number" && Number.isFinite(m.change_pct)), [markets])
  const positive = live.filter((m: any) => Number(m.change_pct) > 0).length
  const negative = live.filter((m: any) => Number(m.change_pct) < 0).length
  const avg = live.length ? live.reduce((s: number, m: any) => s + Number(m.change_pct || 0), 0) / live.length : 0
  const scoreValue = typeof score === "number" ? Math.round(score) : null
  const isBear = String(regime || "").toLowerCase().includes("bear") || (scoreValue != null && scoreValue < 45)
  const isBull = !isBear && (String(regime || "").toLowerCase().includes("bull") || (scoreValue != null && scoreValue > 55))
  const breadth = live.length ? Math.round((positive / live.length) * 100) : null
  const momentum = live.length ? Math.round(Math.max(0, Math.min(100, 50 + avg * 18))) : null
  const volumeProxy = live.length ? Math.round(Math.max(0, Math.min(100, 50 + (positive - negative) * 2.5))) : null
  const technicalProxy = scoreValue != null ? Math.round((scoreValue * 0.7) + (breadth ?? 50) * 0.3) : null

  useEffect(() => {
    const find = () => setTargets({
      sentiment: document.querySelector<HTMLElement>(".ref-sentiment"),
      chart: document.querySelector<HTMLElement>(".prediction .chart"),
      news: document.querySelector<HTMLElement>(".news"),
    })
    find()
    const timer = window.setTimeout(find, 50)
    return () => window.clearTimeout(timer)
  }, [])

  useEffect(() => {
    if (!targets.sentiment || !targets.chart || !targets.news) return
    targets.sentiment.classList.add("tx-live-connected")
    targets.chart.classList.add("tx-live-chart-connected")
    targets.news.classList.add("tx-live-news-connected")
    return () => {
      targets.sentiment?.classList.remove("tx-live-connected")
      targets.chart?.classList.remove("tx-live-chart-connected")
      targets.news?.classList.remove("tx-live-news-connected")
    }
  }, [targets])

  const meter = (label: string, value: number | null) => (
    <div className="tx-live-meter" key={label}>
      <span>{label}</span><i><b style={{ width: `${value == null ? 0 : value}%` }} /></i><em>{value == null ? "—" : `${value}%`}</em>
    </div>
  )

  const chartBars = live.slice(0, 12).map((m: any) => Math.max(8, Math.min(96, 50 + Number(m.change_pct || 0) * 18)))

  return <>
    {targets.sentiment && createPortal(
      <div className="tx-live-sentiment-data" aria-label="Live market sentiment components">
        {meter("Momentum", momentum)}
        {meter("Breadth", breadth)}
        {meter("Flow", volumeProxy)}
        {meter("Technical", technicalProxy)}
        {meter("Overall", scoreValue)}
        <small>{live.length ? `${positive} UP / ${negative} DOWN • ${live.length} LIVE INDICES` : "WAITING FOR LIVE INDEX FEED"}</small>
      </div>,
      targets.sentiment,
    )}
    {targets.chart && createPortal(
      <div className="tx-live-index-chart" aria-label="Live global index momentum">
        <div className="tx-chart-caption"><span>LIVE INDEX MOMENTUM</span><b>{live.length ? `${positive} UP / ${negative} DOWN` : "CONNECTING"}</b></div>
        <div className="tx-chart-bars">
          {chartBars.length ? chartBars.map((height: number, i: number) => <i key={`${i}-${height}`} style={{ height: `${height}%` }} className={Number(live[i]?.change_pct || 0) >= 0 ? "is-up" : "is-down"} />) : <span className="tx-chart-empty">Waiting for live index data…</span>}
        </div>
        <div className="tx-chart-axis"><span>NEGATIVE</span><span>0</span><span>POSITIVE</span></div>
      </div>,
      targets.chart,
    )}
    {targets.news && createPortal(
      <div className="tx-live-intelligence" aria-label="Live market intelligence">
        <div className="tx-intel-row"><b>01</b><span>Market regime</span><strong>{isBear ? "BEARISH" : isBull ? "BULLISH" : "BALANCED"}</strong></div>
        <div className="tx-intel-row"><b>02</b><span>Index breadth</span><strong>{positive} UP / {negative} DOWN</strong></div>
        <div className="tx-intel-row"><b>03</b><span>Average index move</span><strong>{avg >= 0 ? "+" : ""}{avg.toFixed(2)}%</strong></div>
        <div className="tx-intel-row"><b>04</b><span>AI market score</span><strong>{scoreValue == null ? "—" : scoreValue}</strong></div>
      </div>,
      targets.news,
    )}
    <style>{`
      .ref-sentiment.tx-live-connected>.meter{display:none!important}
      .ref-sentiment.tx-live-connected>.tx-live-sentiment-data{display:block}
      .tx-live-sentiment-data{margin-top:8px}.tx-live-sentiment-data small{display:block;margin-top:8px;color:#60758e;font:700 6px 'JetBrains Mono',monospace;letter-spacing:.04em}
      .tx-live-meter{display:grid;grid-template-columns:60px 1fr 30px;align-items:center;gap:7px;font-size:8px;color:#a5b4c9;margin:7px 0}.tx-live-meter i{height:5px;border-radius:10px;background:#17283b;overflow:hidden}.tx-live-meter i b{display:block;height:100%;background:linear-gradient(90deg,#1c9fff,#35e2a0);border-radius:10px;box-shadow:0 0 8px rgba(53,226,160,.3)}.tx-live-meter em{font-style:normal;text-align:right;color:#d2dceb}
      .prediction .chart.tx-live-chart-connected>svg,.prediction .chart.tx-live-chart-connected>.chart-glow{display:none!important}.tx-live-index-chart{position:absolute;inset:0;padding:12px 10px 8px;display:flex;flex-direction:column}.tx-chart-caption{display:flex;justify-content:space-between;color:#6c829b;font:700 7px 'JetBrains Mono',monospace;letter-spacing:.06em}.tx-chart-caption b{color:#39e29c}.tx-chart-bars{flex:1;display:flex;align-items:center;gap:6px;border-bottom:1px solid rgba(80,140,220,.14);margin-top:8px;min-height:0}.tx-chart-bars i{flex:1;min-width:4px;max-width:34px;border-radius:4px 4px 0 0;background:#31d99b;box-shadow:0 0 10px rgba(49,217,155,.22)}.tx-chart-bars i.is-down{background:#ff536b;box-shadow:0 0 10px rgba(255,83,107,.18);align-self:flex-start;margin-top:auto;border-radius:0 0 4px 4px}.tx-chart-axis{display:flex;justify-content:space-between;color:#536a82;font:600 6px 'JetBrains Mono',monospace;padding-top:5px}.tx-chart-empty{margin:auto;color:#60758d;font:700 8px 'JetBrains Mono',monospace}
      .news.tx-live-news-connected>.news-row{display:none!important}.news.tx-live-news-connected>.tx-live-intelligence{display:block}.tx-live-intelligence{margin-top:8px}.tx-intel-row{display:grid;grid-template-columns:25px 1fr auto;gap:7px;align-items:center;padding:12px 0;border-bottom:1px solid rgba(80,140,220,.08);font:700 8px 'JetBrains Mono',monospace}.tx-intel-row:last-child{border-bottom:0}.tx-intel-row>b{color:#4dbaff}.tx-intel-row span{color:#9aaabd}.tx-intel-row strong{color:#3fe2a0;text-align:right}
    `}</style>
  </>
}

/** Live homepage market visual. No synthetic fallback score is displayed. */
export default function MarketBattle({ className = "" }: { className?: string }) {
  const { score, markets, ok, timestamp } = usePublicMarket()
  const [heatmapHost, setHeatmapHost] = useState<HTMLElement | null>(null)
  const value = typeof score === "number" ? Math.round(score) : null
  const live = markets.filter((m: any) => m.price != null).length
  const positive = markets.filter((m: any) => typeof m.change_pct === "number" && m.change_pct > 0).length
  const negative = markets.filter((m: any) => typeof m.change_pct === "number" && m.change_pct < 0).length
  const liveLabel = ok && live > 0 ? "LIVE" : "CONNECTING"
  const updated = timestamp ? new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"

  useEffect(() => {
    const host = document.querySelector<HTMLElement>(".map-panel .map-visual")
    if (!host) return
    host.classList.add("nifty-heatmap-host")
    setHeatmapHost(host)
    return () => {
      host.classList.remove("nifty-heatmap-host")
      setHeatmapHost(null)
    }
  }, [])

  return (
    <>
      <div className={`titan-market-engine ${className}`} aria-label="TITAN X live market intelligence">
        <div className="tme-grid" />
        <div className="tme-head"><span>LIVE MARKET ENGINE</span><b>{liveLabel}</b></div>
        <div className="tme-core">
          <div className="tme-orbit orbit-a" /><div className="tme-orbit orbit-b" />
          <div className="tme-ring"><strong>{value ?? "—"}</strong><span>{value == null ? "WAITING FOR LIVE FEED" : "AI MARKET SCORE"}</span></div>
          <div className="tme-pulse pulse-a" /><div className="tme-pulse pulse-b" />
        </div>
        <div className="tme-bars" aria-hidden="true">
          {[32,48,39,64,55,76,61,86,70,92,78,96].map((height, i) => <i key={i} style={{height:`${height}%`}} />)}
        </div>
        <div className="tme-footer"><span><i className="up-dot"/> UP <b>{positive}</b></span><span><i className="down-dot"/> DOWN <b>{negative}</b></span><span><i className="live-dot"/> LIVE <b>{live}</b></span><span>UPDATED <b>{updated}</b></span></div>
        <style jsx>{`
          .titan-market-engine{position:relative;min-height:430px;height:clamp(430px,34vw,560px);overflow:hidden;border:1px solid rgba(83,169,255,.24);border-radius:18px;background:radial-gradient(circle at 50% 50%,rgba(19,105,220,.16),transparent 42%),linear-gradient(180deg,#020711,#030a17);box-shadow:inset 0 0 70px rgba(35,128,255,.08),0 20px 70px rgba(0,0,0,.4)}
          .tme-grid{position:absolute;inset:0;opacity:.32;background-image:linear-gradient(rgba(60,145,255,.08) 1px,transparent 1px),linear-gradient(90deg,rgba(60,145,255,.08) 1px,transparent 1px);background-size:34px 34px;mask-image:linear-gradient(transparent,black 20%,black 80%,transparent)}
          .tme-head{position:absolute;left:16px;right:16px;top:15px;display:flex;justify-content:space-between;color:#7790ab;font:700 8px 'JetBrains Mono',monospace;letter-spacing:.13em;z-index:2}.tme-head b{color:#3fe2a0}
          .tme-core{position:absolute;left:50%;top:49%;width:245px;height:245px;transform:translate(-50%,-50%);display:grid;place-items:center}.tme-orbit{position:absolute;border:1px solid rgba(71,178,255,.32);border-radius:50%;transform:rotate(-16deg)}.orbit-a{width:230px;height:86px}.orbit-b{width:175px;height:175px;border-color:rgba(48,226,164,.2);transform:rotate(35deg)}
          .tme-ring{width:122px;height:122px;border-radius:50%;display:grid;place-items:center;align-content:center;border:1px solid rgba(73,187,255,.5);background:radial-gradient(circle,rgba(13,76,145,.65),rgba(2,9,20,.92));box-shadow:0 0 35px rgba(24,147,255,.25),inset 0 0 25px rgba(25,164,255,.12);z-index:2}.tme-ring strong{font:800 35px 'JetBrains Mono',monospace;color:#eff8ff}.tme-ring span{margin-top:5px;color:#6f91b0;font:700 7px 'JetBrains Mono',monospace;letter-spacing:.08em;text-align:center}.tme-pulse{position:absolute;width:7px;height:7px;border-radius:50%;background:#43d9ff;box-shadow:0 0 18px 5px rgba(50,199,255,.5);animation:tmePulse 2.8s ease-in-out infinite}.pulse-a{left:18%;top:52%}.pulse-b{right:15%;top:34%;background:#39e2a0;box-shadow:0 0 18px 5px rgba(57,226,160,.4);animation-delay:1s}
          .tme-bars{position:absolute;left:12%;right:12%;bottom:68px;height:95px;display:flex;align-items:flex-end;gap:7px;border-bottom:1px solid rgba(90,155,230,.2);z-index:2}.tme-bars i{flex:1;min-width:4px;border-radius:4px 4px 0 0;background:linear-gradient(180deg,#42d9ff,#245fff);box-shadow:0 0 10px rgba(45,145,255,.22);opacity:.8}
          .tme-footer{position:absolute;left:16px;right:16px;bottom:17px;display:flex;justify-content:space-between;color:#71869f;font:700 7px 'JetBrains Mono',monospace;letter-spacing:.08em;z-index:2;gap:10px}.tme-footer span{display:flex;gap:5px;align-items:center;white-space:nowrap}.tme-footer b{color:#dbe9f8}.tme-footer i{width:6px;height:6px;border-radius:50%;display:inline-block}.up-dot{background:#31e29a;box-shadow:0 0 8px #31e29a}.down-dot{background:#ff526b;box-shadow:0 0 8px #ff526b}.live-dot{background:#4dbaff;box-shadow:0 0 8px #4dbaff}
          @keyframes tmePulse{0%,100%{transform:scale(.7);opacity:.5}50%{transform:scale(1.5);opacity:1}}
          @media(max-width:600px){.titan-market-engine{min-height:390px;height:390px;border-radius:14px}.tme-core{transform:translate(-50%,-50%) scale(.82)}.tme-bars{left:9%;right:9%;gap:4px}.tme-footer{font-size:6px;gap:6px;overflow:hidden}.tme-footer span:nth-child(4){display:none}}
          @media(prefers-reduced-motion:reduce){.tme-pulse{animation:none}}
        `}</style>
      </div>
      {heatmapHost ? createPortal(<NiftyHeatmap />, heatmapHost) : null}
      <LandingLiveOverlay />
      <style>{`
        .map-panel .nifty-heatmap-host{position:relative;overflow:hidden;}
        .map-panel .nifty-heatmap-host > .map-dot,
        .map-panel .nifty-heatmap-host > .map-route,
        .map-panel .nifty-heatmap-host > .map-orb{display:none!important;}
        .map-panel .nifty-heatmap-host .nifty-heatmap-wrap{position:absolute;inset:0;padding:14px;box-sizing:border-box;overflow:hidden;}
      `}</style>
    </>
  )
}