# Omega Frontend Integration Kit

Use these files to connect an AI Studio or React frontend to the finalized Omega
backend without moving execution logic into the browser.

## Precision Pricing (shared with pipeline)

The canonical pricing logic lives in two places that must stay equivalent:

- TypeScript reference: `precision_pricing.ts`
- Python pipeline: `omega_v5/pricing/precision_pricing.py`

Both implement the exact same rules:
- 18-decimal fixed point (`PRICE_SCALE`)
- Strict oracle validation + deviation checks
- `mulDiv`, `scaleDecimals`, `executablePriceX18`, etc.
- No floating point for money

Frontend code that needs price math for display or simulation should import
from `precision_pricing.ts` and stay in bigint.

## Backend URL

Local PM2 backend:

```text
http://127.0.0.1:8080
```

Remote frontend deployment should call an HTTPS reverse proxy that points to the
same backend:

```text
https://your-omega-api.example.com
```

## Environment Variables

```env
VITE_OMEGA_API_URL=http://127.0.0.1:8080
VITE_OMEGA_API_TOKEN=
```

Only set `VITE_OMEGA_API_TOKEN` if the backend has:

```env
API_FRONTEND_TOKEN_REQUIRED=true
API_TOKEN=<same-token>
```

## Files

- `omegaApiClient.ts`: stable typed client for the backend API.
- `useOmegaRuntime.tsx`: polling React hook for status/PnL/traces/proofs.
- `OmegaRuntimePanel.tsx`: operator panel wired to runtime, pool discovery,
  oracle, liquidation, PnL, trace, and validation endpoints.
- `ExecutionManager.ts`: frontend-safe manager facade for AI Studio or React
  actions. It calls backend.
- `precision_pricing.ts`: exact port of the pipeline pricing engine.

## Usage example (precision math in frontend)

```ts
import { PrecisionPricingEngine, ... } from "./precision_pricing";

const engine = new PrecisionPricingEngine(tokens, policies, sources);
const price = await engine.getUsdPrice(tokenAddr, context);
const atomicUsd = engine.tokenAtomicToUsdX18(amount, token, price.priceUsdX18);
```

This guarantees that any number shown to the operator matches what the
Python execution pipeline will use for sizing, gates, and P&L.
