"use client";

import { useMemo, useState } from "react";

type Analytics = {
  summary: { initial_equity: number; final_equity: number; total_return_pct: number; max_drawdown_pct: number };
  risk: { sharpe: number; sortino: number; profit_factor: number };
  trades: { count: number; win_rate_pct: number; best_trade: number | null; worst_trade: number | null };
  benchmark: { return_pct: number | null; alpha_pct: number | null };
  equity_curve: number[];
  drawdown_curve: number[];
};

const demo: Analytics = {
  summary: { initial_equity: 100000, final_equity: 108500, total_return_pct: 8.5, max_drawdown_pct: -3.2 },
  risk: { sharpe: 1.42, sortino: 1.91, profit_factor: 1.84 },
  trades: { count: 24, win_rate_pct: 62.5, best_trade: 4200, worst_trade: -1900 },
  benchmark: { return_pct: 6.1, alpha_pct: 2.4 },
  equity_curve: [100000, 101200, 100700, 103100, 102500, 105800, 104900, 108500],
  drawdown_curve: [0, 0, -0.49, 0, -0.58, 0, -0.85, 0],
};

function Sparkline({ values }: { values: number[] }) {
  const points = useMemo(() => {
    const min = Math.min(...values), max = Math.max(...values), range = max - min || 1;
    return values.map((v, i) => `${(i / Math.max(values.length - 1, 1)) * 100},${100 - ((v - min) / range) * 90 - 5}`).join(" ");
  }, [values]);
  return <svg viewBox="0 0 100 100" className="h-64 w-full" preserveAspectRatio="none"><polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" /></svg>;
}

function Card({ title, value, subtitle }: { title: string; value: string; subtitle?: string }) {
  return <div className="rounded-xl border bg-card p-5 shadow-sm"><div className="text-sm text-muted-foreground">{title}</div><div className="mt-2 text-2xl font-semibold">{value}</div>{subtitle && <div className="mt-1 text-xs text-muted-foreground">{subtitle}</div>}</div>;
}

export default function AnalyticsDashboard() {
  const [data, setData] = useState<Analytics>(demo);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadAnalytics() {
    setLoading(true); setError(null);
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "";
      const response = await fetch(`${base}/api/v1/analytics/dashboard`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ equity: data.equity_curve, trades: [], benchmark_return_pct: data.benchmark.return_pct }),
      });
      if (!response.ok) throw new Error(`Analytics API returned ${response.status}`);
      setData(await response.json());
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to load analytics"); }
    finally { setLoading(false); }
  }

  return <main className="space-y-6 p-6">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div><h1 className="text-3xl font-bold">Advanced Analytics</h1><p className="text-sm text-muted-foreground">Performance, risk, trades and benchmark intelligence</p></div>
      <button onClick={loadAnalytics} disabled={loading} className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-muted disabled:opacity-50">{loading ? "Loading…" : "Refresh Analytics"}</button>
    </div>
    {error && <div className="rounded-lg border border-destructive/40 p-3 text-sm text-destructive">{error}</div>}
    <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card title="Total Return" value={`${data.summary.total_return_pct.toFixed(2)}%`} />
      <Card title="Max Drawdown" value={`${data.summary.max_drawdown_pct.toFixed(2)}%`} />
      <Card title="Sharpe Ratio" value={data.risk.sharpe.toFixed(2)} />
      <Card title="Win Rate" value={`${data.trades.win_rate_pct.toFixed(1)}%`} />
      <Card title="Sortino Ratio" value={data.risk.sortino.toFixed(2)} />
      <Card title="Profit Factor" value={Number.isFinite(data.risk.profit_factor) ? data.risk.profit_factor.toFixed(2) : "∞"} />
      <Card title="Trades" value={String(data.trades.count)} />
      <Card title="Alpha vs Benchmark" value={data.benchmark.alpha_pct == null ? "—" : `${data.benchmark.alpha_pct.toFixed(2)}%`} />
    </section>
    <section className="grid gap-6 lg:grid-cols-2">
      <div className="rounded-xl border bg-card p-5"><div className="mb-3 font-semibold">Equity Curve</div><Sparkline values={data.equity_curve} /></div>
      <div className="rounded-xl border bg-card p-5"><div className="mb-3 font-semibold">Drawdown</div><Sparkline values={data.drawdown_curve} /></div>
    </section>
    <section className="grid gap-6 md:grid-cols-3">
      <Card title="Initial Equity" value={data.summary.initial_equity.toLocaleString()} />
      <Card title="Final Equity" value={data.summary.final_equity.toLocaleString()} />
      <Card title="Benchmark Return" value={data.benchmark.return_pct == null ? "—" : `${data.benchmark.return_pct.toFixed(2)}%`} />
    </section>
  </main>;
}
