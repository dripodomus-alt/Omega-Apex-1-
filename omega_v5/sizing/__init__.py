#!/usr/bin/env python3
# ==============================================================================
# omega_v5/sizing — Phase-4 flash sizing package
#
# Public API used by opportunity_ranker, payload staging, and tests.
# Delegates to the OFFICIAL capital_injector for all injection decisions.
# ==============================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Sequence

from ..config import (
    BELLMAN_CURVE_DECAY_FACTOR,
    DYNAMIC_SIZE_IMPACT_PENALTY_BPS,
    DYNAMIC_SIZE_MAX_SEARCH_STEPS,
    DYNAMIC_SIZE_OPT_BINS_USD,
    ENABLE_DYNAMIC_FLASH_SIZING,
    ENABLE_DYNAMIC_SIZE_OPTIMIZER,
    ENABLE_QUANTUM_SIZING,
    FLASH_ROUTE_TVL_FRACTIONS,
    FLASH_SIZE_LADDER_BPS,
    MAX_FLASH_PRINCIPAL_USD,
    MAX_ROUTE_TVL_FRACTION,
    MIN_FLASH_PRINCIPAL_USD,
)
from ..flash_loan import FlashSource, evaluate_profitability
from ..oracle_layer import token_price_usd

from ..capital_injector import (
    CAPITAL_SOURCE_REGISTRY,
    EXECUTION_VENUE_REGISTRY,
    CapitalInjectionResult,
    RouteMetadata,
    check_self_cannibalization,
    compute_derivative_optimal_size,
    compute_optimal_injection,
    import_metadata_for_route,
    optimal_flash_injection as _official_optimal_flash_injection,
    prepare_sizing_for_rust,
    register_execution_venue,
)

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
    snapshot_route_tvl,
)

optimal_flash_for_route = _official_optimal_flash_injection
compute_optimal_flash_injection = compute_optimal_injection
optimal_flash_injection = _official_optimal_flash_injection


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
    """Stager-facing entry. Uses official capital_injector first (guard + derivative)."""
    requested = Decimal(str(principal_usd or 0))
    pool_ids = [str(p) for p in (pool_sequence or []) if p]

    try:
        inj = compute_optimal_injection(
            pool_sequence=pool_ids,
            pools=pools or {},
            path=path,
            flash_source=flash_source,
            requested_principal_usd=requested if requested > 0 else None,
            base_rate=base_rate if base_rate is not None else Decimal("1.001"),
        )
        # Surface cannibalization as zero-size RouteSizing
        return RouteSizing(
            selected_principal_usd=inj.optimal_injection_usd,
            max_profit_usd=inj.peak_surplus_usd,
            min_pool_tvl_usd=inj.min_tvl_usd,
            search_upper_bound_usd=inj.hard_cap_usd,
            search_steps=steps,
            profitability_at_selection=None,
            search_space_details={
                "method": inj.method,
                "reason": inj.reason,
                "quantum_score": str(inj.quantum_score),
                "cannibalization_detected": inj.cannibalization_detected,
                "version": "capital_injector_official",
            },
            method=f"capital_injector:{inj.method}",
            metadata={
                "flash_principal_raw": 0,
                "live_principal_eligible": inj.live_eligible,
                "proof_only_below_minimum": not inj.live_eligible,
                "minimum_principal_usd": str(MIN_FLASH_PRINCIPAL_USD),
                "bottleneck": inj.bottleneck_pool_id,
                "cannibalization_detected": inj.cannibalization_detected,
                "cannibalization_message": inj.cannibalization_message,
            },
        )
    except Exception:
        pass

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
    "CAPITAL_SOURCE_REGISTRY",
    "EXECUTION_VENUE_REGISTRY",
    "CapitalInjectionResult",
    "RouteMetadata",
    "check_self_cannibalization",
    "compute_derivative_optimal_size",
    "compute_optimal_injection",
    "import_metadata_for_route",
    "prepare_sizing_for_rust",
    "register_execution_venue",
    "optimal_flash_for_route",
    "compute_optimal_flash_injection",
    "optimal_flash_injection",
    "RouteSizing",
    "DynamicSizeResult",
    "dynamic_size_optimizer",
    "optimize_principal_with_dynamic",
    "optimize_route_principal",
    "estimate_route_tvl_usd",
    "_apply_impact_penalty",
    "OptimalFlashSize",
    "RouteTvlSnapshot",
    "SizeSample",
    "apply_injection_to_route_dict",
    "build_size_ladder",
    "estimate_pool_tvl_usd",
    "find_peak_delta_injection",
    "snapshot_route_tvl",
    "evaluate_profitability",
    "token_price_usd",
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
    "BELLMAN_CURVE_DECAY_FACTOR",
    "ENABLE_QUANTUM_SIZING",
    "Decimal",
]
