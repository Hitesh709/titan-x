# INDstocks integration

Titan-X now contains an INDstocks read-only market-data adapter. It is intentionally not connected to real order placement.

Required Render environment variables:
- `INDSTOCKS_CLIENT_ID`
- `INDSTOCKS_MPIN`
- `INDSTOCKS_TOTP_SECRET`

Alternatively, for temporary testing only:
- `INDSTOCKS_ACCESS_TOKEN`

The TOTP secret must be configured by the account owner in the INDstocks dashboard. Tokens expire after 24 hours; the adapter can generate a fresh token from TOTP. Never commit these secrets.
