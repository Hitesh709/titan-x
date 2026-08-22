import React, { useState } from "react";

export type ScreenerBacktestBridgeProps = {
  screenId: string;
  symbol: string;
  apiBaseUrl?: string;
};

/**
 * Small, self-contained bridge from an existing Screener result to the
 * canonical Screener -> Backtest API. It deliberately contains no backtest
 * engine logic and can be embedded by the existing Screener page.
 */
export default function ScreenerBacktestBridge({
  screenId,
  symbol,
  apiBaseUrl = "",
}: ScreenerBacktestBridgeProps) {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [initialCapital, setInitialCapital] = useState("100000");
  const [strategyType, setStrategyType] = useState("screener");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<unknown>(null);

  async function runBacktest(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      const response = await fetch(
        `${apiBaseUrl}/screener/screens/${encodeURIComponent(screenId)}/backtest`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol,
            start_date: startDate,
            end_date: endDate,
            initial_capital: Number(initialCapital),
            strategy_type: strategyType,
            strategy_params: {},
          }),
        },
      );

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail ?? "Unable to start backtest");
      }
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start backtest");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={runBacktest} aria-label={`Backtest ${symbol}`}>
      <h3>Backtest {symbol}</h3>
      <label>
        Start date
        <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
      </label>
      <label>
        End date
        <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} required />
      </label>
      <label>
        Initial capital
        <input type="number" min="1" step="1" value={initialCapital} onChange={(e) => setInitialCapital(e.target.value)} required />
      </label>
      <label>
        Strategy
        <input value={strategyType} onChange={(e) => setStrategyType(e.target.value)} required />
      </label>
      <button type="submit" disabled={loading}>
        {loading ? "Starting…" : "Run Backtest"}
      </button>
      {error && <p role="alert">{error}</p>}
      {result && <pre>{JSON.stringify(result, null, 2)}</pre>}
    </form>
  );
}
