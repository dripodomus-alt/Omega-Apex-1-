#!/usr/bin/env python3
# ==============================================================================
# dynamic_optimizer.py — Phase-4 sizing 2.0
#
# Dual-mode capital optimizer:
#   1) profit_function ladder search (optimize_principal_with_dynamic path)
#   2) bin search with impact penalty (legacy / impact tests)
#
# Goals: speed (early exit on decline), accuracy (TVL cap + full P&L),
# profitability (argmax net), productivity (one API for ranker + tests).
# ==============================================================================

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Optional, Sequence

from ..config import (
    DYNAMIC_SIZE_IMPACT_PENALTY_BPS as _CFG_IMPACT_BPS,
    DYNAMIC_SIZE_OPT_BINS_USD as _CFG_BINS,
    FLASH_ROUTE_TVL_FRACTIONS as _CFG_TVL_FRACS,
    MAX_FLASH_PRINCIPAL_USD as _CFG_MAX_FLASH,
    MAX_ROUTE_TVL_FRACTION as _CFG_MAX_TVL_FRAC,
    MIN_FLASH_PRINCIPAL_USD as _CFG_MIN_FLASH,
)
from ..flash_loan import (
    FlashSource,
    FlashLoanParams,
    Profitability,
    evaluate_profitability as _evaluate_profitability_impl,
)
from ..oracle_layer import PriceUnavailable, token_price_usd

ZERO = Decimal("0")
BPS_DENOMINATOR = Decimal("10000")

# Module-level names (also re-exported / patched via omega_v5.sizing)
DYNAMIC_SIZE_IMPACT_PENALTY_BPS = _CFG_IMPACT_BPS
DYNAMIC_SIZE_OPT_BINS_USD = _CFG_BINS
FLASH_ROUTE_TVL_FRACTIONS = _CFG_TVL_FRACS
MAX_FLASH_PRINCIPAL_USD = _CFG_MAX_FLASH
MAX_ROUTE_TVL_FRACTION = _CFG_MAX_TVL_FRAC
MIN_FLASH_PRINCIPAL_USD = _CFG_MIN_FLASH
evaluate_profitability = _evaluate_profitability_impl

__all__ = [
    "RouteSizing",
    "DynamicSizeResult",
    "estimate_pool_tvl_usd",
    "estimate_route_tvl_usd",
    "dynamic_size_optimizer",
    "optimize_principal_with_dynamic",
    "_apply_impact_penalty",
    "MAX_FLASH_PRINCIPAL_USD",
    "MIN_FLASH_PRINCIPAL_USD",
    "MAX_ROUTE_TVL_FRACTION",
    "FLASH_ROUTE_TVL_FRACTIONS",
    "DYNAMIC_SIZE_OPT_BINS_USD",
    "DYNAMIC_SIZE_IMPACT_PENALTY_BPS",
    "evaluate_profitability",
]


def _sizing_pkg():
    """Live package module so monkeypatches on omega_v5.sizing.* are honored."""
    return sys.modules.get("omega_v5.sizing")


def _cfg(name: str, default: Any) -> Any:
    pkg = _sizing_pkg()
    if pkg is not None and hasattr(pkg, name):
        return getattr(pkg, name)
    return globals().get(name, default)


def _eval_profitability(**kwargs: Any) -> Profitability:
    pkg = _sizing_pkg()
    fn = getattr(pkg, "evaluate_profitability", None) if pkg is not None else None
    if fn is None:
        fn = evaluate_profitability
    try:
        return fn(**kwargs)
    except TypeError:
        gross = kwargs.get("gross_amount_out_usd")
        principal = kwargs.get("principal_usd")
        rest = {k: v for k, v in kwargs.items() if k not in {"gross_amount_out_usd", "principal_usd"}}
        return fn(gross, principal, **rest)


@dataclass(frozen=True)
class RouteSizing:
    """Result of optimize_principal_with_dynamic (ranker / payload path)."""

    selected_principal_usd: Decimal
    max_profit_usd: Decimal
    min_pool_tvl_usd: Decimal
    search_upper_bound_usd: Decimal
    search_steps: int
    profitability_at_selection: Profitability | None = None
    search_space_details: dict[str, str] | None = None
    method: str = "dynamic_profit_ladder_v2"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def injection_usd(self) -> Decimal:
        return self.selected_principal_usd

    @property
    def peak_net_profit_usd(self) -> Decimal:
        return self.max_profit_usd
    
    @property
    def live_principal_eligible(self) -> bool:
        return self.profitability_at_selection is not None and self.profitability_at_selection.passes_gate


@dataclass(frozen=True)
class DynamicSizeResult:
    """Result of bin-search dynamic_size_optimizer mode."""

    best_principal_usd: Decimal
    best_profitability: Profitability
    best_method: str
    samples: tuple[tuple[Decimal, Decimal], ...] = ()

def _apply_impact_penalty(
    principal: Decimal,
    min_tvl: Decimal,
    gross: Decimal,
) -> Decimal:
    """
    Return the conservative liquidity-impact penalty in USD.

    This function returns the penalty amount, not post-penalty profit.

    Linear model:
        impact_ratio = principal / min_tvl

        penalty_usd =
            gross
            * impact_ratio
            * DYNAMIC_SIZE_IMPACT_PENALTY_BPS
            / 10_000

    Safety behavior:
    - Non-positive gross surplus returns zero.
    - Non-positive principal returns zero.
    - Non-positive TVL fails closed by penalizing the full gross surplus.
    - Negative impact-penalty configuration is rejected.
    - The result is clamped between zero and gross.
    - All arithmetic remains Decimal-based.
    """
    try:
        principal = Decimal(principal)
        min_tvl = Decimal(min_tvl)
        gross = Decimal(gross)
        penalty_bps = Decimal(DYNAMIC_SIZE_IMPACT_PENALTY_BPS)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("principal, min_tvl, gross, and impact penalty BPS must be valid Decimal-compatible values") from exc

    if gross <= ZERO:
        return ZERO
    if principal <= ZERO:
        return ZERO
    if min_tvl <= ZERO:
        return gross
    if penalty_bps < ZERO:
        raise ValueError("DYNAMIC_SIZE_IMPACT_PENALTY_BPS cannot be negative")
    if penalty_bps == ZERO:
        return ZERO
    impact_ratio = principal / min_tvl
    raw_penalty_usd = gross * impact_ratio * penalty_bps / BPS_DENOMINATOR
    return min(gross, max(ZERO, raw_penalty_usd))


def estimate_pool_tvl_usd(pool: dict[str, Any]) -> Decimal:
    """Authoritative per-pool TVL for sizing caps."""
    if not isinstance(pool, dict):
        return Decimal("0")

    for key in ("total_executable_liquidity_usd", "tvl_usd", "liquidity_usd"):
        raw = pool.get(key)
        if raw is None:
            continue
        try:
            value = Decimal(str(raw))
            if value > 0:
                return value
        except Exception:
            continue

    tokens = pool.get("tokens") or []
    reserves = pool.get("reserves") or []
    if not tokens or not reserves or len(tokens) != len(reserves):
        return Decimal("0")

    total = Decimal("0")
    for token, reserve in zip(tokens, reserves):
        try:
            price = token_price_usd(str(token))
            if price and price > 0:
                total += Decimal(str(reserve)) * Decimal(str(price))
        except (PriceUnavailable, Exception):
            continue
    return total


def estimate_route_tvl_usd(
    pool_sequence: Sequence[str] | Iterable[str],
    live_pools: dict[str, dict[str, Any]],
) -> Decimal:
    """Bottleneck TVL = min pool TVL on the route."""
    ids = [str(pid) for pid in (pool_sequence or []) if pid]
    if not ids:
        return Decimal("0")

    min_tvl = Decimal("inf")
    for pool_id in ids:
        pool = live_pools.get(pool_id) if live_pools else None
        if not pool:
            return Decimal("0")
        pool_tvl = estimate_pool_tvl_usd(pool)
        if pool_tvl <= 0:
            return Decimal("0")
        if pool_tvl < min_tvl:
            min_tvl = pool_tvl
    return min_tvl if min_tvl.is_finite() else Decimal("0")


def _empty_profitability(principal: Decimal = Decimal("0")) -> Profitability:
    flash = FlashLoanParams(
        source=FlashSource.BALANCER,
        asset="USDC",
        principal_usd=principal,
        fee_bps=Decimal("0"),
        fee_usd=Decimal("0"),
        repayment_usd=principal,
    )
    return Profitability(
        gross_amount_out=Decimal("0"),
        flashloan=flash,
        gas_cost_usd=Decimal("0"),
        relay_tip_usd=Decimal("0"),
        risk_buffer_usd=Decimal("0"),
        net_profit_usd=Decimal("0"),
        profit_to_gas=Decimal("0"),
        passes_gate=False,
    )


def _profit_ladder_search(
    profit_function: Callable[[Decimal], Profitability],
    min_principal: Decimal,
    max_principal: Decimal,
    steps: int = 12,
) -> tuple[Decimal, Profitability | None]:
    """Uniform sample + early exit after sustained peak decline."""
    min_principal = Decimal(str(min_principal))
    max_principal = Decimal(str(max_principal))
    steps = max(2, int(steps))

    if max_principal < min_principal:
        max_principal = min_principal
    if max_principal <= 0:
        return Decimal("0"), None

    best_principal = Decimal("0")
    best_profitability: Profitability | None = None
    decline_streak = 0

    span = max_principal - min_principal
    for i in range(steps):
        if steps == 1:
            principal = min_principal
        else:
            principal = min_principal + span * (Decimal(i) / Decimal(steps - 1))

        try:
            profitability = profit_function(principal)
        except Exception:
            continue

        net = Decimal(str(getattr(profitability, "net_profit_usd", 0) or 0))
        passes = bool(getattr(profitability, "passes_gate", False))

        if passes:
            if best_profitability is None or net > Decimal(
                str(best_profitability.net_profit_usd or 0)
            ):
                best_principal = principal
                best_profitability = profitability
                decline_streak = 0
            elif best_profitability is not None:
                peak = Decimal(str(best_profitability.net_profit_usd or 0))
                if peak > 0 and net < peak * Decimal("0.9"):
                    decline_streak += 1
                    if decline_streak >= 2:
                        break
        elif best_profitability is not None:
            decline_streak += 1
            if decline_streak >= 2:
                break

    return best_principal, best_profitability


def _impact_penalty_fn(principal: Decimal, min_tvl: Decimal, gross: Decimal) -> Decimal:
    """Resolve patched _apply_impact_penalty from package when present."""
    pkg = _sizing_pkg()
    fn = getattr(pkg, "_apply_impact_penalty", None) if pkg is not None else None
    if fn is None:
        fn = _apply_impact_penalty
    return fn(principal, min_tvl, gross)


def _bin_search_optimizer(
    *,
    gross_amount_out_usd: Decimal,
    min_tvl_usd: Decimal,
    gross_rate: Decimal | None = None,
    base_gas_cost_usd: Decimal | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    asset: str = "USDC",
    hops: int = 2,
) -> DynamicSizeResult:
    """Impact-aware bin search over DYNAMIC_SIZE_OPT_BINS_USD."""
    min_tvl = Decimal(str(min_tvl_usd or 0))
    if min_tvl <= 0:
        return DynamicSizeResult(
            best_principal_usd=Decimal("0"),
            best_profitability=_empty_profitability(),
            best_method="rejected_no_tvl",
        )

    rate = Decimal(str(gross_rate)) if gross_rate is not None else Decimal("1.005")
    if rate <= 0:
        rate = Decimal("1.005")

    max_frac = Decimal(str(_cfg("MAX_ROUTE_TVL_FRACTION", Decimal("0.15")) or "0.15"))
    max_flash = Decimal(str(_cfg("MAX_FLASH_PRINCIPAL_USD", Decimal("100000")) or "100000"))
    bins_cfg = list(_cfg("DYNAMIC_SIZE_OPT_BINS_USD", []) or [])

    tvl_cap = min_tvl * max_frac
    hard_cap = min(max_flash, tvl_cap)
    if hard_cap <= 0:
        return DynamicSizeResult(
            best_principal_usd=Decimal("0"),
            best_profitability=_empty_profitability(),
            best_method="rejected_no_tvl",
        )

    bins: list[Decimal] = []
    for b in bins_cfg:
        try:
            v = Decimal(str(b))
        except Exception:
            continue
        if v > 0 and v <= hard_cap:
            bins.append(v)
    if not bins:
        bins = [min(hard_cap, Decimal("10000"))]
    if hard_cap not in bins:
        bins.append(hard_cap)
    bins = sorted(set(bins))

    gas = Decimal(str(base_gas_cost_usd or 0))
    best_p = Decimal("0")
    best_prof: Profitability | None = None
    samples: list[tuple[Decimal, Decimal]] = []

    for principal in bins:
        gross = principal * rate
        edge = gross - principal
        if edge < 0:
            edge = Decimal("0")
        penalty = _impact_penalty_fn(principal, min_tvl, edge if edge > 0 else gross)
        net = gross - principal - gas - penalty

        flash = FlashLoanParams(
            source=flash_source,
            asset=asset,
            principal_usd=principal,
            fee_bps=Decimal("0"),
            fee_usd=Decimal("0"),
            repayment_usd=principal,
        )
        prof = Profitability(
            gross_amount_out=gross - penalty,
            flashloan=flash,
            gas_cost_usd=gas,
            relay_tip_usd=Decimal("0"),
            risk_buffer_usd=Decimal("0"),
            net_profit_usd=net,
            profit_to_gas=(net / gas) if gas > 0 else Decimal("999"),
            passes_gate=net > 0,
        )

        samples.append((principal, net))
        if prof.passes_gate and (
            best_prof is None or net > Decimal(str(best_prof.net_profit_usd))
        ):
            best_p = principal
            best_prof = prof

    if best_prof is None:
        return DynamicSizeResult(
            best_principal_usd=Decimal("0"),
            best_profitability=_empty_profitability(),
            best_method="rejected_no_profitable_bin",
            samples=tuple(samples),
        )

    return DynamicSizeResult(
        best_principal_usd=best_p,
        best_profitability=best_prof,
        best_method="dynamic_bin_search_with_impact",
        samples=tuple(samples),
    )


def dynamic_size_optimizer(
    *args: Any,
    profit_function: Callable[[Decimal], Profitability] | None = None,
    min_principal: Decimal | None = None,
    max_principal: Decimal | None = None,
    steps: int = 12,
    gross_amount_out_usd: Decimal | None = None,
    min_tvl_usd: Decimal | None = None,
    gross_rate: Decimal | None = None,
    base_gas_cost_usd: Decimal | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    asset: str = "USDC",
    hops: int = 2,
    **kwargs: Any,
) -> Any:
    """
    Dual-mode optimizer.

    Mode A — profit ladder:
        dynamic_size_optimizer(profit_function=..., min_principal=..., max_principal=..., steps=N)
        -> (best_principal, best_profitability | None)

    Mode B — impact bins:
        dynamic_size_optimizer(gross_amount_out_usd=..., min_tvl_usd=..., ...)
        -> DynamicSizeResult
    """
    if args:
        if callable(args[0]):
            profit_function = args[0]
            if len(args) > 1:
                min_principal = args[1]
            if len(args) > 2:
                max_principal = args[2]
            if len(args) > 3:
                steps = int(args[3])
        else:
            if gross_amount_out_usd is None:
                gross_amount_out_usd = args[0]
            if len(args) > 1 and min_tvl_usd is None:
                min_tvl_usd = args[1]

    if profit_function is None and "profit_function" in kwargs:
        profit_function = kwargs["profit_function"]
    if min_tvl_usd is None and "min_tvl_usd" in kwargs:
        min_tvl_usd = kwargs["min_tvl_usd"]
    if gross_amount_out_usd is None and "gross_amount_out_usd" in kwargs:
        gross_amount_out_usd = kwargs["gross_amount_out_usd"]
    if gross_rate is None and "gross_rate" in kwargs:
        gross_rate = kwargs["gross_rate"]
    if base_gas_cost_usd is None and "base_gas_cost_usd" in kwargs:
        base_gas_cost_usd = kwargs["base_gas_cost_usd"]

    if profit_function is not None:
        min_p = Decimal(
            str(
                min_principal
                if min_principal is not None
                else _cfg("MIN_FLASH_PRINCIPAL_USD", Decimal("1000"))
            )
        )
        max_p = Decimal(
            str(
                max_principal
                if max_principal is not None
                else _cfg("MAX_FLASH_PRINCIPAL_USD", Decimal("100000"))
            )
        )
        return _profit_ladder_search(
            profit_function=profit_function,
            min_principal=min_p,
            max_principal=max_p,
            steps=int(steps),
        )

    return _bin_search_optimizer(
        gross_amount_out_usd=Decimal(str(gross_amount_out_usd or 0)),
        min_tvl_usd=Decimal(str(min_tvl_usd or 0)),
        gross_rate=Decimal(str(gross_rate)) if gross_rate is not None else None,
        base_gas_cost_usd=Decimal(str(base_gas_cost_usd))
        if base_gas_cost_usd is not None
        else None,
        flash_source=flash_source,
        asset=asset,
        hops=hops,
    )


def optimize_principal_with_dynamic(
    opportunity: Any = None,
    live_pools: dict[str, dict[str, Any]] | None = None,
    quote_function: Callable[[Decimal], Decimal] | None = None,
    *,
    pool_sequence: Sequence[str] | None = None,
    path: Sequence[str] | None = None,
    flash_source: FlashSource | None = None,
    hops: int | None = None,
    steps: int = 12,
    requested_principal_usd: Decimal | None = None,
) -> RouteSizing:
    """
    Phase-4 2.0 entry: TVL-capped dynamic principal search for a route.

    Accepts either a duck-typed opportunity (path/pool_sequence/flash_source)
    or explicit kwargs. quote_function(principal_usd) -> gross_out_usd.
    """
    live_pools = live_pools or {}

    if opportunity is not None:
        pool_sequence = list(
            pool_sequence
            if pool_sequence is not None
            else getattr(opportunity, "pool_sequence", None)
            or []
        )
        path = list(path if path is not None else getattr(opportunity, "path", None) or [])
        if flash_source is None:
            flash_source = getattr(opportunity, "flash_source", None) or FlashSource.BALANCER
    else:
        pool_sequence = list(pool_sequence or [])
        path = list(path or [])

    if flash_source is None:
        flash_source = FlashSource.BALANCER

    asset = str(path[0]) if path else "USDC"
    hop_n = int(
        hops
        if hops is not None
        else max(1, (len(path) - 1) if path else len(pool_sequence) or 2)
    )

    # Honor monkeypatch on omega_v5.sizing.estimate_route_tvl_usd
    pkg = _sizing_pkg()
    est_tvl = getattr(pkg, "estimate_route_tvl_usd", None) if pkg is not None else None
    if est_tvl is None:
        est_tvl = estimate_route_tvl_usd
    min_route_tvl = est_tvl(pool_sequence, live_pools)

    fracs = list(_cfg("FLASH_ROUTE_TVL_FRACTIONS", []) or [])
    try:
        frac = max(fracs) if fracs else Decimal(
            str(_cfg("MAX_ROUTE_TVL_FRACTION", Decimal("0.15")) or "0.15")
        )
    except Exception:
        frac = Decimal(str(_cfg("MAX_ROUTE_TVL_FRACTION", Decimal("0.15")) or "0.15"))
    if frac <= 0:
        frac = Decimal("0.15")

    max_flash = Decimal(str(_cfg("MAX_FLASH_PRINCIPAL_USD", Decimal("100000")) or "100000"))
    min_flash = Decimal(str(_cfg("MIN_FLASH_PRINCIPAL_USD", Decimal("1000")) or "1000"))

    tvl_cap = min_route_tvl * frac if min_route_tvl > 0 else Decimal("0")
    upper_bound = min(max_flash, tvl_cap) if tvl_cap > 0 else min_flash
    if requested_principal_usd is not None and Decimal(str(requested_principal_usd)) > 0:
        upper_bound = min(upper_bound, Decimal(str(requested_principal_usd)))

    min_bound = min_flash
    if upper_bound < min_bound:
        upper_bound = min_bound

    def _quote(principal_usd: Decimal) -> Decimal:
        if quote_function is None:
            return Decimal("0")
        try:
            return Decimal(str(quote_function(principal_usd)))
        except Exception:
            return Decimal("0")

    def get_profitability(principal_usd: Decimal) -> Profitability:
        gross_out_usd = _quote(principal_usd)
        return _eval_profitability(
            gross_amount_out_usd=gross_out_usd,
            principal_usd=principal_usd,
            hops=hop_n,
            flash_source=flash_source,
            asset=asset,
        )

    best_principal, best_profitability = _profit_ladder_search(
        profit_function=get_profitability,
        min_principal=min_bound,
        max_principal=upper_bound,
        steps=int(steps),
    )

    return RouteSizing(
        selected_principal_usd=best_principal,
        max_profit_usd=(
            Decimal(str(best_profitability.net_profit_usd))
            if best_profitability is not None
            else Decimal("0")
        ),
        min_pool_tvl_usd=min_route_tvl,
        search_upper_bound_usd=upper_bound,
        search_steps=int(steps),
        profitability_at_selection=best_profitability,
        search_space_details={
            "min_bound": str(min_bound),
            "upper_bound": str(upper_bound),
            "tvl_fraction": str(frac),
            "source": "min(MAX_FLASH_PRINCIPAL_USD, min_route_tvl * TVL_FRACTION)",
            "version": "2.0",
        },
        method="optimize_principal_with_dynamic_v2",
        metadata={
            "path": list(path),
            "pool_sequence": list(pool_sequence),
            "flash_source": flash_source.value
            if hasattr(flash_source, "value")
            else str(flash_source),
            "hops": hop_n,
        },
    )
