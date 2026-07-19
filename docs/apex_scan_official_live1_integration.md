# Apex Scan Official Live1 Integration

`apex-scan-official-live1.zip` was reviewed as a design source only. Runtime
code from the archive was not executed or imported directly.

## Accepted Concepts

- 32-lane operating grid, mapped to `omega_v5.transport_lanes.LANES`.
- C1/C2 execution visibility, mapped to execution traces, receipts, and PnL.
- Normalized quote accounting, mapped to `normalized_quote` metadata.
- Liquidation monitor concept, mapped to the existing fail-closed liquidation scanner.
- Runtime control panel concept, mapped to `omega_v5.runtime_control`.
- Oracle/RPC health telemetry, mapped to sourced layers and transport lanes.

## Rejected Surfaces

The following were intentionally excluded:

- Fake transaction hash generation.
- Dummy pool generation.
- Fallback reserve-based opportunities.
- Random PnL, random route IDs, and random chart data.
- Placeholder Balancer math.
- `/api/arbitrage/simulate` archive endpoint.
- Archive `config.json` sample addresses and malformed RPC entries.

## Production Rule

The system may use the archive for interface layout and operator workflow ideas,
but all runtime values must come from:

- live Polygon RPC reads,
- verified oracle reads,
- normalized quote metadata,
- route-kind adapter checks,
- exact `eth_call` proof,
- real transaction receipts and trace hashes.

No mock opportunity, synthetic reserve, fake hash, or random PnL value is
admitted into discovery, ranking, payload construction, or the dashboard.
