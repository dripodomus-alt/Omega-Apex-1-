# omega_v6/capital_allocator.py
# Conservative capital allocator using dynamic size optimizer + adapter checks
# Updated to use new bin + equation optimizer from V5

from decimal import Decimal
from typing import Optional, Dict, Any

from omega_v5.flash_loan import FlashSource, evaluate_profitability_for_sources
from omega_v5.sizing import optimize_principal_with_dynamic, RouteSizing
from omega_v5.adapter_registry import resolve_capital_source_adapter
from omega_v5.config import V6_CAPITAL_ALLOCATION_ENABLED, ENABLE_DYNAMIC_SIZE_OPTIMIZER

def allocate_capital_for_route(
    gross_usd: Decimal,
    pool_sequence: list[str],
    pools: dict,
    hops: int = 2,
    asset: str = "USDC",
) -> Dict[str, Any]:
    """V6 allocator: prefers sources with valid adapters + dynamic size opt."""
    if not V6_CAPITAL_ALLOCATION_ENABLED:
        return {"source": "BALANCER", "principal": str(gross_usd), "method": "v6_disabled"}

    # Use dynamic optimizer
    sizing: RouteSizing = optimize_principal_with_dynamic(
        gross_usd, pool_sequence, pools, hops=hops
    )

    # Check adapters for sources
    best_source = FlashSource.BALANCER
    for src in [FlashSource.BALANCER, FlashSource.AAVE]:
        res = resolve_capital_source_adapter(src)
        if res.ok and res.executable:
            best_source = src
            break

    return {
        "source": best_source.value,
        "principal_usd": str(sizing.selected_principal_usd),
        "net_profit_usd": str(sizing.optimized_net_profit_usd),
        "method": sizing.method,
        "adapter_ok": True,
        "bin_sizing": ENABLE_DYNAMIC_SIZE_OPTIMIZER,
    }
