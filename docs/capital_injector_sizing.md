# Capital Injector Sizing (Canonical)

**This is the single source of truth for all flash-loan principal sizing.**

## Core Rules
- CAPITAL_SOURCE_REGISTRY (funding only: BALANCER, AAVE_V3)
- EXECUTION_VENUE_REGISTRY (trading pools only — never funding)
- Hard self-cannibalization guard — any overlap returns size=0 + CRITICAL ERROR
- Exact derivative formula (no approximations):

```
OptimalSize = (sqrt(Rin * Rout * (1 - f_swap) * (1 - f_flash)) - Rin) / (1 - f_swap)
```

Returns 0 when friction makes the expression non-positive.

## Notebook Matrix Setup
The asset matrix + injector simulation lives in `notebooks/omega_v5.ipynb` (Cell 1 extended) and `scripts/ops/simulate_capital_injector.py`.

Example usage in notebook:

```python
from omega_v5.capital_injector import (
    compute_optimal_injection, 
    check_self_cannibalization,
    compute_derivative_optimal_size,
    CAPITAL_SOURCE_REGISTRY
)
from omega_v5.flash_loan import FlashSource
from decimal import Decimal

# Use the ASSET_MATRIX from Cell 1
rin = Decimal("120000")
rout = Decimal("122500")
f_swap = Decimal("0.003")
f_flash = Decimal("0")

size = compute_derivative_optimal_size(rin, rout, f_swap, f_flash)
print("Derivative optimal:", size)

# Full injector with guard
result = compute_optimal_injection(
    pool_sequence=["POOL_A", "POOL_B"],
    pools={...},
    flash_source=FlashSource.BALANCER,
)
print(result.as_sizing_params())
```

## Integration Points
- `route_execution_stager.py`: calls injector before sizing
- `opportunity_ranker.py`: uses `compute_optimal_injection`
- `sizing/__init__.py`: delegates to injector
- `prepare_sizing_for_rust()`: produces dict for Rust engine

## Validation
```bash
python scripts/ops/simulate_capital_injector.py
python scripts/ops/validate_config.py
pytest tests/test_capital_injector.py -q
```

All routes must pass the cannibal guard before any economic calculation.
