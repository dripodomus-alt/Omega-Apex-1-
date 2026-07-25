# Capital Injector & Derivative Sizing

## Role

`omega_v5/capital_injector.py` is the **official** sizing module. It runs **before** Rust Bellman-Ford ranking/math and before payload staging.

All flash principal decisions must go through:

- `compute_optimal_injection(...)`
- or `prepare_sizing_for_rust(...)` / `optimal_flash_injection(...)`

## Isolated registries

| Registry | Purpose |
|---|---|
| `CAPITAL_SOURCE_REGISTRY` | Funding only (Balancer vault, Aave V3 pool) |
| `EXECUTION_VENUE_REGISTRY` | Trading pools only (discovery / live venues) |

No implicit state sharing. Execution venues are registered via `register_execution_venue` / bulk import from live pools.

## Self-cannibalization guard

Before any calculus:

1. Resolve funding `pool_id` / address from `CAPITAL_SOURCE_REGISTRY`.
2. Compare against every id in the route `pool_sequence`.
3. On overlap → **halt**, set  
   `CRITICAL ERROR: SELF-CANNIBALIZATION DETECTED`,  
   return `optimal_injection_usd = 0.0`.

## Exact derivative formula

\[
\text{OptimalSize} = \frac{\sqrt{R_{in} \cdot R_{out} \cdot (1 - f_{swap}) \cdot (1 - f_{flash})} - R_{in}}{1 - f_{swap}}
\]

Friction rules:

- If \(\sqrt{\ldots} \le R_{in}\) → size `0.0`
- If spread cannot beat \(f_{swap} + f_{flash}\) → size `0.0`

## Data tiers

- **L1 (Redis):** optional cached `f_swap` / `f_flash` via `redis_cache`
- **L2 (metadata):** `Rin` / `Rout` from reserves × oracle prices, else TVL split on bottleneck pool

## Fallback

If the derivative path fails friction, the injector falls back to:

1. Bellman-Ford style surplus curve \(\pi(x)\) with impact decay  
2. Discrete ladder search  
3. Quantum VQC stability score adjustment  

## Call graph

```
stager / ranker / sizing package
        │
        ▼
capital_injector.compute_optimal_injection
        │
        ├── cannibalization guard
        ├── derivative OptimalSize
        └── Bellman + quantum fallback
        │
        ▼
as_sizing_params() → rust_engine / payload
```

## Validation

```powershell
python scripts/ops/validate_config.py
pytest tests/test_capital_injector.py -q
```

## Simulation helper

```powershell
python scripts/ops/simulate_capital_injector.py
```
