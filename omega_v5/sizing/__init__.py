#!/usr/bin/env python3
# ==============================================================================
# omega_v5/sizing — Phase-4 flash sizing package (2.0)
#
# Public API used by opportunity_ranker, payload staging, and tests.
# ==============================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Sequence

# Config symbols re-exported so tests can monkeypatch omega_v5.sizing.X
from ..config import (
    DYNAMIC_SIZE_IMPACT_PENALTY_BPS,
    DYNAMIC_SIZE_MAX_SEARCH_STEPS,
    DYNAMIC_SIZE_OPT_BINS_USD,
    ENABLE_DYNAMIC_FLASH_SIZING,
    ENABLE_DYNAMIC_SIZE_OPTIMIZER,
    FLASH_ROUTE_TVL_FRACTIONS,
    FLASH_SIZE_LADDER_BPS,
    MAX_FLASH_PRINCIPAL_USD,
    MAX_ROUTE_TVL_FRACTION,
    MIN_FLASH_PRINCIPAL_USD,
)
from ..flash_loan import FlashSource, evaluate_profitability

from .dynamic_optimizer import (
    DynamicSizeResult,
    RouteSizing,
    _apply_impact_penalty,
    dynamic_size_optimizer,
    estimate_pool_tvl_usd as estimate_pool_tvl_usd_dynamic,
    estimate_route_tvl_usd,
    optimize_principal_with_dynamic,
)
from .optimal_flash_sizer import (
    OptimalFlashSize,
    RouteTvlSnapshot,
    SizeSample,
    apply_injection_to_route_dict,
    build_size_ladder,
    estimate_pool_tvl_usd,
    find_peak_delta_injection,
    optimal_flash_injection,
    snapshot_route_tvl,
)

# Canonical aliases
optimal_flash_for_route = optimal_flash_injection


def optimize_route_principal(
    principal_usd: Decimal | float | int | str,
    pool_sequence: Sequence[str] | Iterable[str],
    pools: dict[str, Any],
    *,
    path: Sequence[str] | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    base_rate: Decimal | None = None,
    steps: int = 12,
) -> RouteSizing:
    """
    Stager-facing entry used by route_execution_stager.stage_pre_ranked_route.

    Caps requested principal by route TVL and runs optimize_principal_with_dynamic.
    """
    requested = Decimal(str(principal_usd or 0))
    pool_ids = [str(p) for p in (pool_sequence or []) if p]

    # Prefer peak-delta injection when TVL is known; bridge to RouteSizing.
    try:
        opt = optimal_flash_injection(
            pool_sequence=pool_ids, # type: ignore
            pools=pools or {},
            base_asset=(path[0] if path else "USDC"),
            hops=max(2, len(pool_ids)),
            flash_source=flash_source,
            requested_principal_usd=requested if requested > 0 else None,
            base_rate=base_rate if base_rate is not None else Decimal("1.001"),
        )
        if opt.injection_usd > 0:
            return RouteSizing(
                selected_principal_usd=opt.injection_usd,
                max_profit_usd=opt.peak_net_profit_usd,
                min_pool_tvl_usd=opt.min_pool_tvl_usd,
                search_upper_bound_usd=opt.hard_cap_usd,
                search_steps=int(getattr(opt, "peak_index", 0) or 0),
                profitability_at_selection=None,
                search_space_details={
                    "method": opt.method,
                    "reason": opt.reason,
                    "version": "2.0",
                },
                method=f"optimize_route_principal:{opt.method}",
                metadata={
                    "flash_principal_raw": int(opt.injection_raw_hint or 0),
                    "live_principal_eligible": opt.live_principal_eligible,
                    "proof_only_below_minimum": opt.proof_only_below_minimum,
                },
            )
    except Exception:
        pass

    # Fallback: pure TVL-capped dynamic ladder without live quote
    def _quote(p: Decimal) -> Decimal:
        rate = base_rate if base_rate is not None else Decimal("1.001")
        return p * rate

    return optimize_principal_with_dynamic(
        live_pools=pools or {},
        quote_function=_quote,
        pool_sequence=pool_ids,
        path=list(path) if path else (["USDC", "WETH", "USDC"] if pool_ids else ["USDC"]),
        flash_source=flash_source,
        hops=max(2, len(pool_ids)),
        steps=steps,
        requested_principal_usd=requested if requested > 0 else None,
    )



__all__ = [
    # 2.0 dynamic optimizer
    "RouteSizing",
    "DynamicSizeResult",
    "dynamic_size_optimizer",
    "optimize_principal_with_dynamic",
    "optimize_route_principal",
    "estimate_route_tvl_usd",
    "_apply_impact_penalty",
    # peak-delta / TVL injection
    "OptimalFlashSize",
    "RouteTvlSnapshot",
    "SizeSample",
    "apply_injection_to_route_dict",
    "build_size_ladder",
    "estimate_pool_tvl_usd",
    "find_peak_delta_injection",
    "optimal_flash_injection",
    "optimal_flash_for_route",
    "snapshot_route_tvl",
    # patch targets
    "evaluate_profitability",
    "MAX_FLASH_PRINCIPAL_USD",
    "MIN_FLASH_PRINCIPAL_USD",
    "MAX_ROUTE_TVL_FRACTION",
    "FLASH_ROUTE_TVL_FRACTIONS",
    "DYNAMIC_SIZE_OPT_BINS_USD",
    "DYNAMIC_SIZE_IMPACT_PENALTY_BPS",
    "DYNAMIC_SIZE_MAX_SEARCH_STEPS",
    "ENABLE_DYNAMIC_FLASH_SIZING",
    "ENABLE_DYNAMIC_SIZE_OPTIMIZER",
    "FLASH_SIZE_LADDER_BPS",
    "Decimal",
]
