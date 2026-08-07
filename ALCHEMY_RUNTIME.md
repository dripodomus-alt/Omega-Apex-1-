# Apex-Omega Polygon 137 — Alchemy Optimized Runtime

## Architecture

```text
ALCHEMY HTTP
  ├── ordinary JSON-RPC reads
  ├── Multicall3 aggregate3 contract reads
  ├── Token API
  ├── Transfers API
  └── block transaction receipts

ALCHEMY WSS
  ├── newHeads
  └── narrowly filtered logs

PUBLICNODE
  ├── HTTP fallback
  └── WSS fallback
```

Ordinary JSON-RPC reads intentionally use HTTP rather than WSS.

Alchemy recommends using WebSockets for subscriptions and HTTP for standard requests because HTTP requests are load-balanced and provide actionable HTTP status codes.

## Enhanced functionality enabled

- `alchemy_getTokenMetadata`
- `alchemy_getTokenBalances`
- `alchemy_getAssetTransfers`
- `alchemy_getTransactionReceipts`
- `newHeads` WSS subscription
- filtered log WSS subscriptions
- Multicall3 aggregate3 for pool/factory/token reads
- PublicNode fallback transport

## Efficiency rules

1. Multicall protocol-state reads instead of one RPC call per pool.
2. Keep WSS subscription scope narrow.
3. `newHeads` drives immediate block-cycle refresh.
4. Subscribe only to relevant factory/pool/router event addresses/topics.
5. Do not stream all pending transactions unless a specific strategy requires it.
6. Use `alchemy_getTransactionReceipts` for a whole block instead of one receipt request per transaction.
7. Use Token API for token metadata/balance hydration rather than repetitive ERC-20 calls where applicable.
8. Use Transfers API for indexed historical/value-transfer queries instead of rescanning blocks.
9. Retain PublicNode as read/subscription fallback.
10. Never commit Alchemy endpoint credentials.

## Configuration

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure-alchemy.ps1 `
  -AlchemyHttpUrl "<ALCHEMY_POLYGON_HTTP_URL>" `
  -AlchemyWssUrl "<ALCHEMY_POLYGON_WSS_URL>"
```

Then load `.env.alchemy` into your runtime environment and run:

```bash
npx tsx scripts/probe-alchemy-runtime.ts
npx tsx services/market-api.ts
```
