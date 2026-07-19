"""
optimal_flash_sizer.py — TVL-capped flash injection with peak-delta search.

Uses route pool TVL (bottleneck = min pool TVL) to cap flash size, then walks a
size ladder along the size→net-delta curve and stops at peak declination
(marginal net profit turns non-positive). That peak is the payload injection size.

Bellman-Ford connection:
  Graph discovery uses edge weights w = -log(rate). Those rates are infinitesimal
  (size→0). Executable surplus is size-dependent: AMM impact makes effective rate
  r(x) decline in x. Absolute net delta π(x) therefore rises then falls. Optimal
  injection is argmax_x π(x) subject to x ≤ TVL fraction cap — the last size
  before the curve declines past the peak.

Economics (aligned with flash_loan.evaluate_profitability):
  gross_out(x) from quote_fn or impact-adjusted rate model
  π(x) = gross_out - x - flash_fee(x) - gas - relay - risk [- impact_penalty]
  pass ⇔ π ≥ min_net
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional, Sequence

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
from ..flash_loan import (
    FlashSource,
    evaluate_profitability,
    live_min_net_profit_usd,
    live_relay_tip_usd,
    live_risk_buffer_usd,
)

# quote_fn(principal_usd) -> gross_amount_out_usd (minOut-valued preferred)
QuoteFn = Callable[[Decimal], Decimal]


@dataclass(frozen=True)
class RouteTvlSnapshot:
    """Per-route liquidity view used for flash caps."""

    pool_ids: tuple[str, ...]
    pool_tvls_usd: tuple[Decimal, ...]
    min_pool_tvl_usd: Decimal
    bottleneck_pool_id: str
    max_fraction: Decimal
    route_cap_usd: Decimal
    hard_cap_usd: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "pool_ids": list(self.pool_ids),
            "pool_tvls_usd": [str(v) for v in self.pool_tvls_usd],
            "min_pool_tvl_usd": str(self.min_pool_tvl_usd),
            "bottleneck_pool_id": self.bottleneck_pool_id,
            "max_fraction": str(self.max_fraction),
            "route_cap_usd": str(self.route_cap_usd),
            "hard_cap_usd": str(self.hard_cap_usd),
        }


@dataclass(frozen=True)
class SizeSample:
    principal_usd: Decimal
    gross_out_usd: Decimal
    net_profit_usd: Decimal
    marginal_net_usd: Decimal
    passes_gate: bool
    method: str


@dataclass(frozen=True)
class OptimalFlashSize:
    """Authoritative flash injection for payload + ranking."""

    injection_usd: Decimal
    injection_raw_hint: int  # 0 unless base decimals/price supplied
    min_pool_tvl_usd: Decimal
    route_cap_usd: Decimal
    hard_cap_usd: Decimal
    peak_net_profit_usd: Decimal
    peak_index: int
    samples: tuple[SizeSample, ...] = ()
    tvl: Optional[RouteTvlSnapshot] = None
    method: str = "peak_delta_tvl_cap"
    reason: str = ""
    live_principal_eligible: bool = True
    proof_only_below_minimum: bool = False
    flash_source: FlashSource = FlashSource.BALANCER
    base_asset: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_payload_fields(self) -> dict[str, Any]:
        """Fields to merge into staged route / C1 payload DNA."""
        return {
            "flash_principal_usd": str(self.injection_usd),
            "flash_injection_usd": str(self.injection_usd),
            "flash_principal_raw": int(self.injection_raw_hint),
            "sizing_method": self.method,
            "sizing_reason": self.reason,
            "min_pool_tvl_usd": str(self.min_pool_tvl_usd),
            "route_cap_usd": str(self.route_cap_usd),
            "peak_net_profit_usd": str(self.peak_net_profit_usd),
            "live_principal_eligible": self.live_principal_eligible,
            "proof_only_below_minimum": self.proof_only_below_minimum,
            "flash_source": self.flash_source.value if self.flash_source else "",
            "base_asset": self.base_asset,
            "tvl": self.tvl.as_dict() if self.tvl else {},
        }


def estimate_pool_tvl_usd(pool: dict) -> Decimal:
    """Delegate to liquidity_registry canonical TVL order."""
    from ..liquidity_registry import _local_tvl_usd

    try:
        return Decimal(str(_local_tvl_usd(pool)))
    except Exception:
        return Decimal("0")


def snapshot_route_tvl(
    pool_sequence: Iterable[str],
    pools: dict,
    *,
    requested_principal_usd: Decimal | None = None,
    max_fraction: Decimal | None = None,
) -> RouteTvlSnapshot | None:
    """
    Bottleneck TVL = min pool TVL on the route.
    route_cap = min_tvl * max_fraction
    hard_cap = min(route_cap, MAX_FLASH, requested if set)
    """
    ids = [str(pid) for pid in pool_sequence if pid]
    if not ids:
        return None

    tvls: list[Decimal] = []
    for pid in ids:
        pool = pools.get(pid)
        if not isinstance(pool, dict):
            return None
        tvl = estimate_pool_tvl_usd(pool)
        if tvl <= 0:
            return None
        tvls.append(tvl)

    min_tvl = min(tvls)
    bottleneck_idx = tvls.index(min_tvl)
    frac = Decimal(str(max_fraction if max_fraction is not None else MAX_ROUTE_TVL_FRACTION))
    if frac <= 0:
        frac = MAX_ROUTE_TVL_FRACTION
    cfg_fracs = [f for f in FLASH_ROUTE_TVL_FRACTIONS if f > 0]
    if cfg_fracs:
        frac = max(frac, max(cfg_fracs))

    route_cap = min_tvl * frac
    hard = min(route_cap, MAX_FLASH_PRINCIPAL_USD)
    if requested_principal_usd is not None and requested_principal_usd > 0:
        hard = min(hard, Decimal(str(requested_principal_usd)))

    return RouteTvlSnapshot(
        pool_ids=tuple(ids),
        pool_tvls_usd=tuple(tvls),
        min_pool_tvl_usd=min_tvl,
        bottleneck_pool_id=ids[bottleneck_idx],
        max_fraction=frac,
        route_cap_usd=route_cap,
        hard_cap_usd=hard,
    )


def _impact_adjusted_gross(
    principal: Decimal,
    base_rate: Decimal,
    min_tvl: Decimal,
) -> Decimal:
    """
    Size-dependent gross out from infinitesimal BF rate base_rate (>1 for arb).

    r_eff(x) ≈ base_rate * (1 - impact_bps_factor * x/tvl - (x/tvl)^2)
    gross = x * r_eff
    """
    if principal <= 0 or base_rate <= 0:
        return Decimal("0")
    if min_tvl <= 0:
        return Decimal("0")
    impact = principal / min_tvl
    decay = impact * DYNAMIC_SIZE_IMPACT_PENALTY_BPS / Decimal("10000")
    decay = decay + impact * impact
    r_eff = base_rate * (Decimal("1") - decay)
    if r_eff < Decimal("0"):
        r_eff = Decimal("0")
    return principal * r_eff


def build_size_ladder(
    *,
    hard_cap_usd: Decimal,
    min_tvl_usd: Decimal,
    min_principal_usd: Decimal | None = None,
    max_steps: int | None = None,
) -> list[Decimal]:
    """Discrete injection candidates from micro → hard_cap."""
    if hard_cap_usd <= 0:
        return []

    steps = int(max_steps if max_steps is not None else DYNAMIC_SIZE_MAX_SEARCH_STEPS)
    steps = max(4, min(steps, 64))
    floor = Decimal(str(min_principal_usd if min_principal_usd is not None else 0))
    if floor < 0:
        floor = Decimal("0")

    candidates: set[Decimal] = set()

    for b in DYNAMIC_SIZE_OPT_BINS_USD:
        try:
            v = Decimal(str(b))
        except Exception:
            continue
        if v > 0:
            candidates.add(v)

    for frac in FLASH_ROUTE_TVL_FRACTIONS:
        if frac > 0 and min_tvl_usd > 0:
            candidates.add(min_tvl_usd * frac)

    for bps in FLASH_SIZE_LADDER_BPS:
        if bps > 0 and min_tvl_usd > 0:
            candidates.add(min_tvl_usd * bps / Decimal("10000"))

    seed = min(hard_cap_usd, max(Decimal("50"), hard_cap_usd / Decimal("32")))
    if seed > 0:
        candidates.add(seed)
        geo = seed
        for _ in range(steps):
            if geo >= hard_cap_usd:
                break
            candidates.add(min(geo, hard_cap_usd))
            geo = geo * Decimal("1.35")
        candidates.add(hard_cap_usd)

    top_start = hard_cap_usd * Decimal("0.35")
    if top_start > 0 and steps >= 2:
        span = hard_cap_usd - top_start
        n = max(3, steps // 3)
        for i in range(n + 1):
            candidates.add(top_start + span * Decimal(i) / Decimal(n))

    ladder = sorted(
        v for v in candidates if v > 0 and v <= hard_cap_usd + Decimal("0.000001")
    )
    cleaned: list[Decimal] = []
    for v in ladder:
        if v > hard_cap_usd:
            v = hard_cap_usd
        if floor > 0 and v < floor and v < hard_cap_usd:
            if hard_cap_usd >= floor:
                continue
        if not cleaned or v != cleaned[-1]:
            cleaned.append(v)
    if hard_cap_usd not in cleaned and hard_cap_usd > 0:
        cleaned.append(hard_cap_usd)
    return cleaned[: max(steps * 2, 8)]


def _net_at_size(
    principal: Decimal,
    gross_out: Decimal,
    *,
    hops: int,
    flash_source: FlashSource,
    asset: str,
) -> tuple[Decimal, bool]:
    """Full expense stack net via production profitability."""
    try:
        prof = evaluate_profitability(
            gross_out,
            principal,
            hops=hops,
            flash_source=flash_source,
            asset=asset,
        )
        return prof.net_profit_usd, bool(prof.passes_gate)
    except Exception:
        fee_bps = Decimal("0") if flash_source == FlashSource.BALANCER else Decimal("5")
        flash_fee = principal * fee_bps / Decimal("10000")
        gas = Decimal("0.001")
        try:
            relay = live_relay_tip_usd()
            risk = live_risk_buffer_usd()
            min_net = live_min_net_profit_usd()
        except Exception:
            relay, risk, min_net = Decimal("0.001"), Decimal("0.005"), Decimal("0.001")
        net = gross_out - principal - flash_fee - gas - relay - risk
        return net, net >= min_net


def find_peak_delta_injection(
    ladder: Sequence[Decimal],
    *,
    gross_fn: Callable[[Decimal], Decimal],
    hops: int = 2,
    flash_source: FlashSource = FlashSource.BALANCER,
    asset: str = "USDC",
    stop_on_decline: bool = True,
    decline_tolerance: Decimal = Decimal("0.98"),
) -> tuple[Decimal, Decimal, int, tuple[SizeSample, ...]]:
    """
    Walk ladder ascending. Peak = max π(x).
    Stop after sustained declination past the peak (Bellman size curve).
    """
    samples: list[SizeSample] = []
    best_x = Decimal("0")
    best_pi = Decimal("-10") ** 12
    best_i = -1
    prev_net: Decimal | None = None
    decline_streak = 0

    for x in ladder:
        x = Decimal(str(x))
        if x <= 0:
            continue
        try:
            gross = Decimal(str(gross_fn(x)))
        except Exception:
            gross = Decimal("0")
        if gross < 0:
            gross = Decimal("0")

        net, passes = _net_at_size(
            x, gross, hops=hops, flash_source=flash_source, asset=asset
        )
        marginal = net - prev_net if prev_net is not None else net
        samples.append(
            SizeSample(
                principal_usd=x,
                gross_out_usd=gross,
                net_profit_usd=net,
                marginal_net_usd=marginal,
                passes_gate=passes,
                method="ladder_eval",
            )
        )

        if net > best_pi:
            best_pi = net
            best_x = x
            best_i = len(samples) - 1
            decline_streak = 0
        elif stop_on_decline and best_i >= 0 and x > best_x:
            if net <= best_pi * decline_tolerance:
                decline_streak += 1
            else:
                decline_streak = 0
            if decline_streak >= 2 and marginal <= 0:
                break

        prev_net = net

    if best_i < 0:
        return Decimal("0"), Decimal("0"), -1, tuple(samples)
    return best_x, best_pi, best_i, tuple(samples)


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
    base_usd_price: Decimal | None = None,
    base_decimals: int | None = None,
    allow_proof_below_minimum: bool = True,
) -> OptimalFlashSize:
    """
    Main entry: TVL-cap + peak-delta search → flash injection for payload.

    Prefer quote_fn(principal_usd)->gross_out_usd when live quotes exist.
    Else use base_rate (BF infinitesimal round-trip) with impact decay.
    """
    pool_ids = [str(p) for p in pool_sequence if p]
    req = (
        Decimal(str(requested_principal_usd))
        if requested_principal_usd is not None
        else MAX_FLASH_PRINCIPAL_USD
    )
    hop_n = int(hops if hops is not None else max(2, len(pool_ids)))
    asset = str(base_asset or "USDC")

    if not ENABLE_DYNAMIC_FLASH_SIZING and not ENABLE_DYNAMIC_SIZE_OPTIMIZER:
        inj = min(req, MAX_FLASH_PRINCIPAL_USD) if req > 0 else MIN_FLASH_PRINCIPAL_USD
        return OptimalFlashSize(
            injection_usd=inj,
            injection_raw_hint=_usd_to_raw_hint(inj, asset, base_usd_price, base_decimals),
            min_pool_tvl_usd=Decimal("0"),
            route_cap_usd=inj,
            hard_cap_usd=inj,
            peak_net_profit_usd=Decimal("0"),
            peak_index=0,
            method="fixed_no_dynamic",
            reason="dynamic flash sizing disabled",
            live_principal_eligible=inj >= MIN_FLASH_PRINCIPAL_USD,
            flash_source=flash_source,
            base_asset=asset,
        )

    snap = snapshot_route_tvl(
        pool_ids,
        pools,
        requested_principal_usd=req if req > 0 else None,
    )
    if snap is None:
        return OptimalFlashSize(
            injection_usd=Decimal("0"),
            injection_raw_hint=0,
            min_pool_tvl_usd=Decimal("0"),
            route_cap_usd=Decimal("0"),
            hard_cap_usd=Decimal("0"),
            peak_net_profit_usd=Decimal("0"),
            peak_index=-1,
            method="rejected",
            reason="route executable liquidity unavailable",
            live_principal_eligible=False,
            flash_source=flash_source,
            base_asset=asset,
        )

    hard = snap.hard_cap_usd
    if hard <= 0:
        return OptimalFlashSize(
            injection_usd=Decimal("0"),
            injection_raw_hint=0,
            min_pool_tvl_usd=snap.min_pool_tvl_usd,
            route_cap_usd=snap.route_cap_usd,
            hard_cap_usd=hard,
            peak_net_profit_usd=Decimal("0"),
            peak_index=-1,
            tvl=snap,
            method="rejected",
            reason="hard_cap_non_positive",
            live_principal_eligible=False,
            flash_source=flash_source,
            base_asset=asset,
        )

    if hard < MIN_FLASH_PRINCIPAL_USD:
        if not allow_proof_below_minimum:
            return OptimalFlashSize(
                injection_usd=Decimal("0"),
                injection_raw_hint=0,
                min_pool_tvl_usd=snap.min_pool_tvl_usd,
                route_cap_usd=snap.route_cap_usd,
                hard_cap_usd=hard,
                peak_net_profit_usd=Decimal("0"),
                peak_index=-1,
                tvl=snap,
                method="rejected_below_min_flash",
                reason=f"hard_cap_usd={hard}<min={MIN_FLASH_PRINCIPAL_USD}",
                live_principal_eligible=False,
                flash_source=flash_source,
                base_asset=asset,
            )
        ladder = build_size_ladder(
            hard_cap_usd=hard,
            min_tvl_usd=snap.min_pool_tvl_usd,
            min_principal_usd=Decimal("0"),
        )
    else:
        ladder = build_size_ladder(
            hard_cap_usd=hard,
            min_tvl_usd=snap.min_pool_tvl_usd,
            min_principal_usd=MIN_FLASH_PRINCIPAL_USD
            if hard >= MIN_FLASH_PRINCIPAL_USD
            else Decimal("0"),
        )

    if not ladder:
        ladder = [hard]

    rate = Decimal(str(base_rate)) if base_rate is not None else Decimal("1.001")
    if rate <= 0:
        rate = Decimal("1.001")

    def gross_fn(x: Decimal) -> Decimal:
        if quote_fn is not None:
            try:
                g = Decimal(str(quote_fn(x)))
                if g > 0:
                    return g
            except Exception:
                pass
        return _impact_adjusted_gross(x, rate, snap.min_pool_tvl_usd)

    best_x, best_pi, best_i, samples = find_peak_delta_injection(
        ladder,
        gross_fn=gross_fn,
        hops=hop_n,
        flash_source=flash_source,
        asset=asset,
        stop_on_decline=True,
    )

    best_pass_x = best_x
    best_pass_pi = best_pi
    best_pass_i = best_i
    for idx, s in enumerate(samples):
        if s.passes_gate and s.net_profit_usd >= best_pass_pi:
            best_pass_x = s.principal_usd
            best_pass_pi = s.net_profit_usd
            best_pass_i = idx
    if best_pass_x > 0:
        best_x, best_pi, best_i = best_pass_x, best_pass_pi, best_pass_i

    if best_x <= 0:
        best_x = ladder[len(ladder) // 2] if ladder else hard
        best_pi = Decimal("0")
        method = "fallback_mid_ladder_no_peak"
        reason = "no_positive_peak_using_mid_cap"
    else:
        method = "peak_delta_tvl_bellman_curve"
        reason = (
            f"argmax_net at injection_usd={best_x} "
            f"min_tvl={snap.min_pool_tvl_usd} hard_cap={hard}"
        )

    live_ok = best_x >= MIN_FLASH_PRINCIPAL_USD and hard >= MIN_FLASH_PRINCIPAL_USD
    proof_only = (not live_ok) and best_x > 0

    return OptimalFlashSize(
        injection_usd=best_x,
        injection_raw_hint=_usd_to_raw_hint(best_x, asset, base_usd_price, base_decimals),
        min_pool_tvl_usd=snap.min_pool_tvl_usd,
        route_cap_usd=snap.route_cap_usd,
        hard_cap_usd=hard,
        peak_net_profit_usd=best_pi,
        peak_index=best_i,
        samples=samples,
        tvl=snap,
        method=method,
        reason=reason,
        live_principal_eligible=live_ok,
        proof_only_below_minimum=proof_only,
        flash_source=flash_source,
        base_asset=asset,
        metadata={
            "ladder_len": len(ladder),
            "sample_count": len(samples),
            "base_rate": str(rate),
            "used_quote_fn": quote_fn is not None,
            "hops": hop_n,
        },
    )


def _usd_to_raw_hint(
    usd: Decimal,
    asset: str,
    price: Decimal | None,
    decimals: int | None,
) -> int:
    """Best-effort raw principal for payload; 0 if price unknown."""
    if usd <= 0:
        return 0
    try:
        from ..units import usd_expense_to_base_raw, to_raw_units

        if price is not None and price > 0:
            return int(usd_expense_to_base_raw(usd, asset, price))
        try:
            return int(usd_expense_to_base_raw(usd, asset, None))
        except Exception:
            pass
        if decimals is not None and price is not None and price > 0:
            token_amt = usd / price
            return int(token_amt * (Decimal(10) ** int(decimals)))
        if asset.upper() in {"USDC", "USDC.E", "USDT", "DAI", "AUSD", "TUSD"}:
            return int(to_raw_units(asset, usd))
    except Exception:
        return 0
    return 0


def apply_injection_to_route_dict(
    route: dict[str, Any],
    optimal: OptimalFlashSize,
) -> dict[str, Any]:
    """Merge optimal flash size into a route/payload dict (mutates and returns)."""
    fields = optimal.as_payload_fields()
    route.update(fields)
    route["flash_principal_usd"] = str(optimal.injection_usd)
    route["principal_usd"] = str(optimal.injection_usd)
    if optimal.injection_raw_hint > 0:
        route["flash_principal_raw"] = int(optimal.injection_raw_hint)
    route["sizing"] = fields
    return route
