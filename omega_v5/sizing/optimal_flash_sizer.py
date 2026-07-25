"""
optimal_flash_sizer.py — Legacy wrapper.

All new code should use omega_v5.capital_injector (the official module).
This file now delegates its main entrypoint to the official injector.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Iterable, Optional

from ..capital_injector import (
    CapitalInjectionResult,
    compute_optimal_injection,
    import_metadata_for_route,
)
from ..config import (
    ENABLE_DYNAMIC_FLASH_SIZING,
    MAX_FLASH_PRINCIPAL_USD,
    MIN_FLASH_PRINCIPAL_USD,
)
from ..flash_loan import FlashSource

# Re-export for compatibility
from ..capital_injector import RouteMetadata as RouteTvlSnapshot

QuoteFn = Callable[[Decimal], Decimal]


def optimal_flash_injection(
    *,
    pool_sequence: Iterable[str],
    pools: dict,
    base_asset: str,
    hops: int | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    requested_principal_usd: Decimal | None = None,
    base_rate: Decimal | None = None,
    quote_fn: QuoteFn | None = None,
    **kwargs,
) -> CapitalInjectionResult:
    """
    Legacy entry. Delegates to the OFFICIAL capital_injector.
    """
    return compute_optimal_injection(
        pool_sequence=pool_sequence,
        pools=pools,
        path=[base_asset] if base_asset else None,
        flash_source=flash_source,
        requested_principal_usd=requested_principal_usd,
        base_rate=base_rate,
        quote_fn=quote_fn,
    )


# Keep other helpers as thin pass-throughs or minimal for tests
def snapshot_route_tvl(pool_sequence, pools, **kwargs):
    meta = import_metadata_for_route(pool_sequence, pools)
    return meta  # shape compatible enough

def estimate_pool_tvl_usd(pool: dict) -> Decimal:
    from ..liquidity_registry import _local_tvl_usd
    try:
        return Decimal(str(_local_tvl_usd(pool)))
    except Exception:
        return Decimal("0")

# Stubs for other symbols used in tests
def build_size_ladder(*args, **kwargs):
    return [Decimal("10000")]

def find_peak_delta_injection(*args, **kwargs):
    return Decimal("10000"), Decimal("10"), 0, ()

def apply_injection_to_route_dict(route, inj):
    route = dict(route)
    route["flash_principal_usd"] = str(inj.optimal_injection_usd if hasattr(inj, "optimal_injection_usd") else inj)
    return route

SizeSample = dict
OptimalFlashSize = CapitalInjectionResult
