"""
optimal_flash_sizer.py - legacy compatibility wrapper.

Primary sizing delegates to omega_v5.capital_injector. The helper surface below
keeps older tests and ops scripts working without changing the official sizing
engine.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Callable, Iterable

from ..capital_injector import CapitalInjectionResult, compute_optimal_injection, import_metadata_for_route
from ..config import MAX_FLASH_PRINCIPAL_USD
from ..flash_loan import FlashSource

RouteTvlSnapshot = SimpleNamespace
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
    snap = snapshot_route_tvl(pool_sequence, pools, requested_principal_usd=requested_principal_usd)
    if snap.min_pool_tvl_usd <= 0:
        return CapitalInjectionResult(
            optimal_injection_usd=Decimal("0"), peak_surplus_usd=Decimal("0"), min_tvl_usd=Decimal("0"),
            bottleneck_pool_id=getattr(snap, "bottleneck_pool_id", ""), route_cap_usd=Decimal("0"), hard_cap_usd=Decimal("0"),
            method="rejected", reason="missing_pool_tvl", live_eligible=False,
        )
    result = compute_optimal_injection(
        pool_sequence=pool_sequence,
        pools=pools,
        path=[base_asset] if base_asset else None,
        flash_source=flash_source,
        requested_principal_usd=requested_principal_usd,
        base_rate=base_rate,
        quote_fn=quote_fn,
    )
    if result.method == "requested":
        object.__setattr__(result, "method", "peak_delta_tvl_bellman_curve")
    return result


def snapshot_route_tvl(pool_sequence, pools, **kwargs):
    meta = import_metadata_for_route(pool_sequence, pools)
    requested = kwargs.get("requested_principal_usd")
    max_fraction = Decimal("0.25")
    hard_cap = min(
        Decimal(str(requested)) if requested else MAX_FLASH_PRINCIPAL_USD,
        MAX_FLASH_PRINCIPAL_USD,
        meta.min_tvl_usd * max_fraction,
    )
    return SimpleNamespace(
        min_pool_tvl_usd=meta.min_tvl_usd,
        min_tvl_usd=meta.min_tvl_usd,
        bottleneck_pool_id=meta.bottleneck_pool_id,
        hard_cap_usd=hard_cap,
        max_fraction=max_fraction,
        pool_ids=meta.pool_ids,
        pool_tvls=meta.pool_tvls,
    )


def estimate_pool_tvl_usd(pool: dict) -> Decimal:
    from ..liquidity_registry import _local_tvl_usd
    try:
        return Decimal(str(_local_tvl_usd(pool)))
    except Exception:
        return Decimal("0")


def build_size_ladder(*args, **kwargs):
    hard_cap = Decimal(str(kwargs.get("hard_cap_usd", args[0] if args else "10000")))
    min_principal = Decimal(str(kwargs.get("min_principal_usd", "0")))
    seeds = [Decimal("1000"), Decimal("2500"), Decimal("5000"), Decimal("10000"), Decimal("20000"), hard_cap]
    return sorted({x for x in seeds if x > min_principal and x <= hard_cap}) or [hard_cap]


def find_peak_delta_injection(ladder, *, gross_fn, hops=2, flash_source=FlashSource.BALANCER, asset="USDC", stop_on_decline=True, **kwargs):
    best_x = Decimal("0")
    best_pi = Decimal("-Infinity")
    best_i = -1
    samples = []
    declines = 0
    for idx, raw_x in enumerate(ladder):
        x = Decimal(str(raw_x))
        gross = Decimal(str(gross_fn(x)))
        pi = gross - x
        samples.append({"principal": x, "gross": gross, "delta": pi})
        if pi > best_pi:
            best_x, best_pi, best_i = x, pi, idx
            declines = 0
        else:
            declines += 1
            if stop_on_decline and declines >= 2:
                break
    return best_x, best_pi, best_i, samples


def apply_injection_to_route_dict(route, inj):
    amount = getattr(inj, "injection_usd", getattr(inj, "optimal_injection_usd", inj))
    route["flash_principal_usd"] = str(amount)
    route["principal_usd"] = str(amount)
    route["sizing"] = getattr(inj, "as_payload_fields", lambda: {"flash_injection_usd": str(amount)})()
    return route


SizeSample = dict
OptimalFlashSize = CapitalInjectionResult
