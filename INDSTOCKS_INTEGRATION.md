# Market Data Provider Migration

The previous INDstocks experiment has been retired. Titan-X now uses the
provider-independent market-data gateway with Upstox as the selected primary
market-data adapter.

## Current provider

- Upstox Market Data Feed V3
- Read-only Analytics Token
- WebSocket streaming through `MarketDataStreamerV3`
- Demo execution only; this adapter does not place broker orders

## Environment

```text
UPSTOX_ANALYTICS_TOKEN=<secret>
UPSTOX_API_BASE_URL=https://api.upstox.com/v2
UPSTOX_WS_MODE=ltpc
```

The filename is retained temporarily for repository history compatibility;
no INDstocks code is used by the application.
