# Xecaps Demo Data Provider

## Purpose

Use Yahoo Finance as the current secondary/reference market-data provider while Angel One static-IP access is unavailable.

## Provider policy

- Yahoo Finance is a reference/fallback source, not an assertion of exchange-authoritative data.
- Existing provider implementations remain available.
- When Angel One becomes available, configure Angel One as the primary source and retain Yahoo for reference/fallback where appropriate.
- Every downstream prediction should retain source/timestamp provenance.

## Deployment configuration

Set the existing market-data provider configuration to `yahoo` in the Render environment for the demo deployment. Do not add an Angel API key or static IP workaround.

## Demo validation

Before the funder demo, verify:

1. API health endpoint is healthy.
2. Market-data provider resolves to Yahoo.
3. A representative NSE symbol such as `RELIANCE.NS` returns current/reference quote data.
4. Historical OHLCV returns non-empty data.
5. Dashboard charts receive normalized data.
6. Provider failures surface a controlled error and do not crash the API.
7. Source and timestamp are preserved in downstream records where supported.

## Important

Yahoo Finance availability and terms can change. Do not present Yahoo data as a guaranteed real-time exchange feed. For production trading execution and exchange-authoritative data, integrate a properly licensed/authorized provider such as Angel One when its static-IP requirements are satisfied.
