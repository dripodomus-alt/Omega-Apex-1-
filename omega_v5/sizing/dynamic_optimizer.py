#!/usr/bin/env python3
# ==============================================================================
# dynamic_optimizer.py — Legacy Phase-4 sizing (kept for compatibility)
#
# New development MUST go through omega_v5/capital_injector.py
# which owns Bellman-Ford curve + quantum sizing.
# ==============================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from ..capital_injector import compute_optimal_injection
from ..config import (
    MAX_FLASH_PRINCIPAL_USD,
    MIN_FLASH_PRINCIPAL_USD,
    MAX_ROUTE_TVL_FRACTION,
)
from ..flash_loan import FlashSource, Profitability

# Re-exports for monkeypatching
DYNAMIC_SIZE_IMPACT_PENALTY_BPS = Decimal("120")
DYNAMIC_SIZE_OPT_BINS_USD = [Decimal("5000"), Decimal("10000")]
FLASH_ROUTE_TVL_FRACTIONS = [Decimal("0.15"), Decimal("0.25"), Decimal("0.5")]
MAX_FLASH_PRINCIPAL_USD = MAX_FLASH_PRINCIPAL_USD
MIN_FLASH_PRINCIPAL_USD = MIN_FLASH_PRINCIPAL_USD
MAX_ROUTE_TVL_FRACTION = MAX_ROUTE_TVL_FRACTION

def estimate_pool_tvl_usd(pool: dict) -> Decimal:
    try:
        from ..liquidity_registry import _local_tvl_usd
        return Decimal(str(_local_tvl_usd(pool)))
    except Exception:
        return Decimal("0")

def estimate_route_tvl_usd(pool_sequence, live_pools):
    tvls = [estimate_pool_tvl_usd(live_pools.get(p, {})) for p in pool_sequence]
    return min(tvls) if tvls else Decimal("0")

def dynamic_size_optimizer(*args, **kwargs):
    profit_function = kwargs.get("profit_function")
    if profit_function is not None:
        min_principal = Decimal(str(kwargs.get("min_principal", "0")))
        max_principal = Decimal(str(kwargs.get("max_principal", "0")))
        steps = max(1, int(kwargs.get("steps", 10)))
        if max_principal <= min_principal:
            return Decimal("0"), None
        step = (max_principal - min_principal) / Decimal(steps)
        best_principal = Decimal("0")
        best_profit = None
        best_net = Decimal("-Infinity")
        declines = 0
        for i in range(steps + 1):
            principal = min_principal + (step * Decimal(i))
            prof = profit_function(principal)
            if not getattr(prof, "passes_gate", False):
                continue
            net = Decimal(str(getattr(prof, "net_profit_usd", "0")))
            if net > best_net:
                best_principal, best_profit, best_net = principal, prof, net
                declines = 0
            else:
                declines += 1
                if declines >= 3:
                    break
        return best_principal, best_profit

    if "pool_sequence" in kwargs and "pools" in kwargs:
        try:
            res = compute_optimal_injection(
                pool_sequence=kwargs["pool_sequence"],
                pools=kwargs.get("pools", {}),
            )
            return res.optimal_injection_usd, None
        except Exception:
            pass
    return Decimal("10000"), None
def optimize_principal_with_dynamic(*args, **kwargs):
    if "opportunity" in kwargs:
        opportunity = kwargs.get("opportunity")
        live_pools = kwargs.get("live_pools", {})
        quote_function = kwargs.get("quote_function", lambda p: p)
        tvl = estimate_route_tvl_usd(getattr(opportunity, "pool_sequence", []), live_pools)
        fraction = FLASH_ROUTE_TVL_FRACTIONS[0] if FLASH_ROUTE_TVL_FRACTIONS else Decimal("0.15")
        upper = max(MIN_FLASH_PRINCIPAL_USD, min(MAX_FLASH_PRINCIPAL_USD, tvl * fraction))
        best_principal = Decimal("0")
        best_profit = Decimal("0")
        if tvl > 0 and upper >= MIN_FLASH_PRINCIPAL_USD:
            def profit_fn(p: Decimal):
                gross = quote_function(p)
                return evaluate_profitability(
                    gross_amount_out_usd=gross,
                    principal_usd=p,
                    hops=max(1, len(getattr(opportunity, "pool_sequence", []))),
                    flash_source=getattr(opportunity, "flash_source", FlashSource.BALANCER),
                )
            best_principal, best_prof = dynamic_size_optimizer(
                profit_function=profit_fn,
                min_principal=MIN_FLASH_PRINCIPAL_USD,
                max_principal=upper,
                steps=10,
            )
            if best_prof is not None:
                best_profit = Decimal(str(getattr(best_prof, "net_profit_usd", "0")))
        return RouteSizing(
            selected_principal_usd=best_principal,
            max_profit_usd=max(best_profit, Decimal("0")),
            min_pool_tvl_usd=tvl,
            search_upper_bound_usd=upper,
            method="dynamic_optimizer",
        )
    return dynamic_size_optimizer(*args, **kwargs)
class RouteSizing:
    def __init__(self, **kw):
        self.selected_principal_usd = kw.get("selected_principal_usd", Decimal("10000"))
        self.max_profit_usd = kw.get("max_profit_usd", Decimal("0"))
        self.min_pool_tvl_usd = kw.get("min_pool_tvl_usd", Decimal("0"))
        self.minimum_principal_usd = kw.get("minimum_principal_usd", MIN_FLASH_PRINCIPAL_USD)
        self.live_principal_eligible = kw.get("live_principal_eligible", self.selected_principal_usd >= self.minimum_principal_usd)
        self.proof_only_below_minimum = kw.get("proof_only_below_minimum", not self.live_principal_eligible)
        self.search_upper_bound_usd = kw.get("search_upper_bound_usd", Decimal("0"))
        self.search_steps = kw.get("search_steps", 0)
        self.profitability_at_selection = kw.get("profitability_at_selection")
        self.search_space_details = kw.get("search_space_details", {})
        self.metadata = kw.get("metadata", {})
        self.method = kw.get("method", "legacy_fallback")

class DynamicSizeResult:
    def __init__(self, **kw):
        self.best_principal_usd = kw.get("best_principal_usd", Decimal("0"))
        self.best_profitability = kw.get("best_profitability")
        self.best_method = kw.get("best_method", "legacy")

def _apply_impact_penalty(principal, min_tvl, gross):
    return Decimal("0")



