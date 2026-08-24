"use client"

import { usePublicMarket } from "./MarketTicker"

/** Neutral homepage market visual; the previous 3D animal scene has been removed. */
export default function MarketBattle({ className = "" }: { className?: string }) {
  const { score, markets } = usePublicMarket()
  const value = typeof score === "number" ? Math.round(score) : 50
  const live = markets.filter((m: any) => m.price != null).length
  const positive = markets.filter((m: any) => typeof m.change_pct === "number" && m.change_pct > 0).length
  const negative = markets.filter((m: any) => typeof m.change_pct === "number" && m.change_pct < 0).length

  return (
    <div className={`titan-market-engine ${className}`} aria-label="TITAN X live market intelligence">
      <div className="tme-grid" />
      <div className="tme-head"><span>LIVE MARKET ENGINE</span><b>INDEX BREADTH</b></div>
      <div className="tme-core">
        <div className="tme-orbit orbit-a" /><div className="tme-orbit orbit-b" />
        <div className="tme-ring"><strong>{value}</strong><span>AI MARKET SCORE</span></div>
        <div className="tme-pulse pulse-a" /><div className="tme-pulse pulse-b" />
      </div>
      <div className="tme-bars" aria-hidden="true">
        {[32,48,39,64,55,76,61,86,70,92,78,96].map((height, i) => <i key={i} style={{height:`${height}%`}} />)}
      </div>
      <div className="tme-footer"><span><i className="up-dot"/> UP <b>{positive}</b></span><span><i className="down-dot"/> DOWN <b>{negative}</b></span><span><i className="live-dot"/> LIVE <b>{live}</b></span></div>
      <style jsx>{`
        .titan-market-engine{position:relative;min-height:430px;height:clamp(430px,34vw,560px);overflow:hidden;border:1px solid rgba(83,169,255,.24);border-radius:18px;background:radial-gradient(circle at 50% 50%,rgba(19,105,220,.16),transparent 42%),linear-gradient(180deg,#020711,#030a17);box-shadow:inset 0 0 70px rgba(35,128,255,.08),0 20px 70px rgba(0,0,0,.4)}
        .tme-grid{position:absolute;inset:0;opacity:.32;background-image:linear-gradient(rgba(60,145,255,.08) 1px,transparent 1px),linear-gradient(90deg,rgba(60,145,255,.08) 1px,transparent 1px);background-size:34px 34px;mask-image:linear-gradient(transparent,black 20%,black 80%,transparent)}
        .tme-head{position:absolute;left:16px;right:16px;top:15px;display:flex;justify-content:space-between;color:#7790ab;font:700 8px 'JetBrains Mono',monospace;letter-spacing:.13em;z-index:2}.tme-head b{color:#3fe2a0}
        .tme-core{position:absolute;left:50%;top:49%;width:245px;height:245px;transform:translate(-50%,-50%);display:grid;place-items:center}.tme-orbit{position:absolute;border:1px solid rgba(71,178,255,.32);border-radius:50%;transform:rotate(-16deg)}.orbit-a{width:230px;height:86px}.orbit-b{width:175px;height:175px;border-color:rgba(48,226,164,.2);transform:rotate(35deg)}
        .tme-ring{width:122px;height:122px;border-radius:50%;display:grid;place-items:center;align-content:center;border:1px solid rgba(73,187,255,.5);background:radial-gradient(circle,rgba(13,76,145,.65),rgba(2,9,20,.92));box-shadow:0 0 35px rgba(24,147,255,.25),inset 0 0 25px rgba(25,164,255,.12);z-index:2}.tme-ring strong{font:800 35px 'JetBrains Mono',monospace;color:#eff8ff}.tme-ring span{margin-top:5px;color:#6f91b0;font:700 7px 'JetBrains Mono',monospace;letter-spacing:.08em}
        .tme-pulse{position:absolute;width:7px;height:7px;border-radius:50%;background:#43d9ff;box-shadow:0 0 18px 5px rgba(50,199,255,.5);animation:tmePulse 2.8s ease-in-out infinite}.pulse-a{left:18%;top:52%}.pulse-b{right:15%;top:34%;background:#39e2a0;box-shadow:0 0 18px 5px rgba(57,226,160,.4);animation-delay:1s}
        .tme-bars{position:absolute;left:12%;right:12%;bottom:68px;height:95px;display:flex;align-items:flex-end;gap:7px;border-bottom:1px solid rgba(90,155,230,.2);z-index:2}.tme-bars i{flex:1;min-width:4px;border-radius:4px 4px 0 0;background:linear-gradient(180deg,#42d9ff,#245fff);box-shadow:0 0 10px rgba(45,145,255,.22);opacity:.8}
        .tme-footer{position:absolute;left:16px;right:16px;bottom:17px;display:flex;justify-content:space-between;color:#71869f;font:700 7px 'JetBrains Mono',monospace;letter-spacing:.08em;z-index:2}.tme-footer span{display:flex;gap:5px;align-items:center}.tme-footer b{color:#dbe9f8}.tme-footer i{width:6px;height:6px;border-radius:50%;display:inline-block}.up-dot{background:#31e29a;box-shadow:0 0 8px #31e29a}.down-dot{background:#ff526b;box-shadow:0 0 8px #ff526b}.live-dot{background:#4dbaff;box-shadow:0 0 8px #4dbaff}
        @keyframes tmePulse{0%,100%{transform:scale(.7);opacity:.5}50%{transform:scale(1.5);opacity:1}}
        @media(max-width:600px){.titan-market-engine{min-height:390px;height:390px;border-radius:14px}.tme-core{transform:translate(-50%,-50%) scale(.82)}.tme-bars{left:9%;right:9%;gap:4px}.tme-footer{font-size:6px}}
        @media(prefers-reduced-motion:reduce){.tme-pulse{animation:none}}
      `}</style>
    </div>
  )
}
