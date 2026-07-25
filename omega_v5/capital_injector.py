"""
capital_injector.py — Official Capital Injector Module

Canonical module for optimal flash-loan / capital injection sizes.
MUST run before the Rust engine completes math/ranking.

Implements:
- Segregated CAPITAL_SOURCE_REGISTRY (funding) vs EXECUTION_VENUE_REGISTRY (trading)
- Hard self-cannibalization guard
- Exact derivative OptimalSize formula:
  OptimalSize = (sqrt(Rin * Rout * (1-f_swap)*(1-f_flash)) - Rin) / (1 - f_swap)
- L1 Redis fee cache + L2 Rin/Rout metadata
- Bellman-Ford surplus curve + quantum VQC as fallback
- Friction thresholding (returns 0.0 when unviable)

No ad-hoc injection. All sizing goes through here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from typing import Any, Callable, Iterable, Optional, Sequence

from .config import (
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
from .flash_loan import FlashSource, evaluate_profitability, live_min_net_profit_usd
from .liquidity_registry import _local_tvl_usd
from .oracle_layer import token_price_usd
from .quantum_logic_gate import create_vqc_circuit, simulate_and_measure
from .redis_cache import get_json, key as redis_key

getcontext().prec = 50

ZERO = Decimal("0")
BPS = Decimal("10000")

# ==============================================================================
# 1. ISOLATED REGISTRIES (Segregated Silos — zero implicit state sharing)
# ==============================================================================
CAPITAL_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "BALANCER": {
        "pool_id": "BALANCER_VAULT_POLYGON",
        "address": "0xBA12222222228d8Ba445958a75a0704d566BF2C8",
        "fee_bps": Decimal("0"),
        "type": "flash_funding",
    },
    "AAVE_V3": {
        "pool_id": "AAVE_V3_POOL_POLYGON",
        "address": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        "fee_bps": Decimal("5"),
        "type": "flash_funding",
    },
}

# Trading venues only. Never used as flash funding sources.
EXECUTION_VENUE_REGISTRY: dict[str, dict[str, Any]] = {}


def register_execution_venue(pool_id: str, metadata: dict[str, Any] | None = None) -> None:
    """Register a trading venue (stager / liquidity_registry)."""
    EXECUTION_VENUE_REGISTRY[str(pool_id)] = dict(metadata or {})


def register_execution_venues_from_pools(pools: dict[str, dict]) -> int:
    """Bulk-register live pools into the execution venue silo."""
    n = 0
    for pid, meta in (pools or {}).items():
        if not pid:
            continue
        register_execution_venue(
            str(pid),
            {
                "protocol": meta.get("protocol"),
                "pool_family": meta.get("pool_family") or meta.get("family"),
                "fee": meta.get("fee", meta.get("fee_tier", meta.get("fee_bps"))),
                "type": "execution_venue",
            },
        )
        n += 1
    return n


# ==============================================================================
# 2. HARD OVERLAP GUARD (Cannibalization Prevention)
# ==============================================================================
def check_self_cannibalization(
    funding_source: str,
    pool_sequence: Iterable[str],
    *,
    funding_pool_id_override: str | None = None,
) -> tuple[bool, str]:
    """
    Hard guard: funding pool_id must never appear in the trading route.
    Also blocks if any route pool is registered only as a capital source.
    Returns (is_cannibal, error_message).
    """
    source_key = str(funding_source or "").strip()
    source_info = CAPITAL_SOURCE_REGISTRY.get(source_key, {})
    funding_pool_id = str(
        funding_pool_id_override
        or source_info.get("pool_id")
        or source_key
    )
    funding_address = str(source_info.get("address") or "").lower()

    pool_list = [str(p) for p in pool_sequence if p]
    pool_list_lower = [p.lower() for p in pool_list]

    # Direct pool_id / address overlap
    if funding_pool_id in pool_list or (
        funding_address and funding_address in pool_list_lower
    ):
        msg = (
            "CRITICAL ERROR: SELF-CANNIBALIZATION DETECTED\n"
            f"  Funding source pool '{funding_pool_id}' overlaps with route pools: {pool_list}\n"
            "  This would flash-borrow from the same pool being arbitraged."
        )
        return True, msg

    # Route pool must not be a known capital-source id
    capital_ids = {
        str(v.get("pool_id", "")).lower()
        for v in CAPITAL_SOURCE_REGISTRY.values()
        if v.get("pool_id")
    }
    capital_addrs = {
        str(v.get("address", "")).lower()
        for v in CAPITAL_SOURCE_REGISTRY.values()
        if v.get("address")
    }
    for pid in pool_list:
        pl = pid.lower()
        if pl in capital_ids or pl in capital_addrs:
            msg = (
                "CRITICAL ERROR: SELF-CANNIBALIZATION DETECTED\n"
                f"  Route pool '{pid}' is registered as a capital funding source.\n"
                f"  Route pools: {pool_list}"
            )
            return True, msg

    return False, ""


# ==============================================================================
# 3. EXACT DERIVATIVE OPTIMAL SIZE FORMULA
# ==============================================================================
def _safe_sqrt(value: Decimal) -> Decimal:
    if value <= 0:
        return ZERO
    return Decimal(str(math.sqrt(float(value))))


def compute_derivative_optimal_size(
    rin: Decimal,
    rout: Decimal,
    f_swap: Decimal,
    f_flash: Decimal,
) -> Decimal:
    """
    Exact calculus derivative sizing (no floating shortcuts in the formula shape):

        OptimalSize = (sqrt(Rin * Rout * (1 - f_swap) * (1 - f_flash)) - Rin) / (1 - f_swap)

    Returns 0.0 when friction makes the root non-positive.
    """
    rin = Decimal(str(rin))
    rout = Decimal(str(rout))
    f_swap = Decimal(str(f_swap))
    f_flash = Decimal(str(f_flash))

    if rin <= 0 or rout <= 0:
        return ZERO

    one_minus_fswap = Decimal("1") - f_swap
    one_minus_fflash = Decimal("1") - f_flash
    if one_minus_fswap <= 0 or one_minus_fflash <= 0:
        return ZERO

    inside = rin * rout * one_minus_fswap * one_minus_fflash
    if inside <= 0:
        return ZERO

    sqrt_part = _safe_sqrt(inside)
    if sqrt_part <= rin:
        return ZERO

    optimal = (sqrt_part - rin) / one_minus_fswap
    return max(optimal, ZERO)


def _apply_friction_threshold(
    optimal: Decimal,
    rin: Decimal,
    rout: Decimal,
    f_swap: Decimal,
    f_flash: Decimal,
) -> tuple[Decimal, str]:
    """Cap cleanly at 0.0 when spread cannot beat combined fee friction."""
    if optimal <= 0:
        return ZERO, "friction_threshold_failed"
    combined = f_swap + f_flash
    if rin > 0 and (rout / rin) <= (Decimal("1") + combined):
        return ZERO, "spread_below_friction"
    return optimal, "passed"


# ==============================================================================
# 4. DATA TIER MAPPING (L1 Redis + L2 Metadata)
# ==============================================================================
def _get_fees_from_tiers(
    flash_source: FlashSource,
    pool: dict | None = None,
) -> tuple[Decimal, Decimal]:
    """
    L1 Hot Cache (Redis) for fee rates + registry / pool fallbacks.
    Returns (f_flash, f_swap) as decimals (e.g. 0.003).
    """
    src = flash_source.value if isinstance(flash_source, FlashSource) else str(flash_source)
    f_flash = Decimal(str(CAPITAL_SOURCE_REGISTRY.get(src, {}).get("fee_bps", Decimal("0")))) / BPS

    f_swap = Decimal("0.003")

    # L1 Redis
    try:
        cached = get_json(redis_key("fees", "swap", src))
        if isinstance(cached, dict):
            if "f_swap" in cached:
                f_swap = Decimal(str(cached["f_swap"]))
            if "f_flash" in cached:
                raw_ff = Decimal(str(cached["f_flash"]))
                f_flash = raw_ff / BPS if raw_ff > 1 else raw_ff
        cached_flash = get_json(redis_key("fees", "flash", src))
        if isinstance(cached_flash, dict) and "fee_bps" in cached_flash:
            f_flash = Decimal(str(cached_flash["fee_bps"])) / BPS
    except Exception:
        pass

    # L2 pool metadata
    if pool:
        raw_fee = pool.get("fee", pool.get("fee_tier", pool.get("fee_bps", pool.get("swap_fee"))))
        if raw_fee is not None:
            try:
                fee_val = Decimal(str(raw_fee))
                if fee_val > 100:
                    # bps or millionths style
                    if fee_val >= Decimal("100"):
                        # Uniswap-style 3000 = 0.3%
                        fee_val = fee_val / Decimal("1000000") if fee_val >= Decimal("10000") else fee_val / BPS
                elif fee_val > 1:
                    fee_val = fee_val / BPS
                f_swap = max(fee_val, ZERO)
            except Exception:
                pass

    return f_flash, f_swap


def _get_rin_rout_from_metadata(
    pool_id: str,
    pools: dict,
    base_asset: str = "USDC",
) -> tuple[Decimal, Decimal]:
    """
    L2 State Metadata: Rin / Rout from reserves or TVL bottleneck.
    Prefer real reserves when present; else split TVL 50/50.
    """
    pool = (pools or {}).get(pool_id, {}) or {}
    tokens = list(pool.get("tokens") or pool.get("token_addresses") or [])
    reserves = list(pool.get("reserves") or pool.get("reserve_balances") or [])

    if len(tokens) >= 2 and len(reserves) >= 2:
        try:
            r0 = Decimal(str(reserves[0]))
            r1 = Decimal(str(reserves[1]))
            p0 = token_price_usd(str(tokens[0]))
            p1 = token_price_usd(str(tokens[1]))
            usd0 = r0 * Decimal(str(p0))
            usd1 = r1 * Decimal(str(p1))
            # Treat base-side as Rin when possible
            base = str(base_asset or "").upper()
            t0 = str(tokens[0]).upper()
            t1 = str(tokens[1]).upper()
            if base and base in t0:
                return max(usd0, Decimal("1")), max(usd1, Decimal("1"))
            if base and base in t1:
                return max(usd1, Decimal("1")), max(usd0, Decimal("1"))
            return max(usd0, Decimal("1")), max(usd1, Decimal("1"))
        except Exception:
            pass

    try:
        tvl = Decimal(str(_local_tvl_usd(pool)))
        if tvl > 0:
            half = tvl * Decimal("0.5")
            return max(half, Decimal("1")), max(half, Decimal("1"))
    except Exception:
        pass

    # Conservative fallback so derivative path can still evaluate
    return Decimal("100000"), Decimal("100000")


# ==============================================================================
# Dataclasses
# ==============================================================================
@dataclass(frozen=True)
class RouteMetadata:
    """Imported metadata for pools/assets in the staged route."""

    pool_ids: tuple[str, ...]
    pool_tvls: dict[str, Decimal]
    min_tvl_usd: Decimal
    bottleneck_pool_id: str
    base_asset: str
    hops: int
    protocol_seq: tuple[str, ...]
    total_executable_liquidity: Decimal


@dataclass(frozen=True)
class CapitalInjectionResult:
    """Official result from the capital injector."""

    optimal_injection_usd: Decimal
    peak_surplus_usd: Decimal
    min_tvl_usd: Decimal
    bottleneck_pool_id: str
    route_cap_usd: Decimal
    hard_cap_usd: Decimal
    method: str
    reason: str
    samples: tuple[dict[str, Any], ...] = ()
    quantum_score: Decimal = ZERO
    quantum_adjustment: Decimal = ZERO
    live_eligible: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    cannibalization_detected: bool = False
    cannibalization_message: str = ""

    def as_sizing_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "principal_usd": str(self.optimal_injection_usd),
            "min_tvl_usd": str(self.min_tvl_usd),
            "bottleneck_pool": self.bottleneck_pool_id,
            "peak_surplus_usd": str(self.peak_surplus_usd),
            "sizing_method": self.method,
            "quantum_score": str(self.quantum_score),
            "quantum_adjustment": str(self.quantum_adjustment),
            "cannibalization_detected": bool(self.cannibalization_detected),
        }
        if self.cannibalization_detected:
            params["error"] = self.cannibalization_message
        return params


def import_metadata_for_route(
    pool_sequence: Iterable[str],
    pools: dict[str, dict],
    path: Optional[Sequence[str]] = None,
    protocol_seq: Optional[Sequence[str]] = None,
) -> RouteMetadata:
    """Official importer for pool/asset metadata staged for the route."""
    pool_ids = tuple(str(p) for p in pool_sequence if p)
    if not pool_ids:
        raise ValueError("No pool_sequence provided for metadata import")

    # Keep execution silo updated (never capital sources)
    register_execution_venues_from_pools({pid: (pools or {}).get(pid, {}) for pid in pool_ids})

    tvls: dict[str, Decimal] = {}
    for pid in pool_ids:
        pool = (pools or {}).get(pid, {}) or {}
        tvl = ZERO
        try:
            tvl = Decimal(str(_local_tvl_usd(pool)))
        except Exception:
            tvl = ZERO
        if tvl <= 0:
            tokens = pool.get("tokens", []) or []
            reserves = pool.get("reserves", []) or []
            for tok, res in zip(tokens, reserves):
                try:
                    price = token_price_usd(str(tok))
                    tvl += Decimal(str(res)) * Decimal(str(price))
                except Exception:
                    continue
        # Prefer explicit executable liquidity fields
        for key in ("total_executable_liquidity_usd", "tvl_usd", "liquidity_usd"):
            if tvl > 0:
                break
            raw = pool.get(key)
            if raw is not None:
                try:
                    tvl = Decimal(str(raw))
                except Exception:
                    pass
        tvls[pid] = max(tvl, ZERO)

    min_tvl = min(tvls.values()) if tvls else ZERO
    bottleneck = min(tvls, key=tvls.get) if tvls else pool_ids[0]
    base_asset = str(path[0]) if path else "USDC"
    hops = max(2, len(pool_ids))
    protos = tuple(str(p) for p in (protocol_seq or ()))
    total_liq = sum(tvls.values(), ZERO)

    return RouteMetadata(
        pool_ids=pool_ids,
        pool_tvls=tvls,
        min_tvl_usd=min_tvl,
        bottleneck_pool_id=str(bottleneck),
        base_asset=base_asset,
        hops=hops,
        protocol_seq=protos,
        total_executable_liquidity=total_liq,
    )


# ==============================================================================
# Bellman-Ford curve + quantum (fallback / comparison)
# ==============================================================================
def _bellman_ford_surplus_curve(
    principal: Decimal,
    base_rate: Decimal,
    min_tvl: Decimal,
) -> Decimal:
    if principal <= 0 or base_rate <= 0 or min_tvl <= 0:
        return ZERO
    impact = principal / min_tvl
    decay = impact * (DYNAMIC_SIZE_IMPACT_PENALTY_BPS / BPS)
    decay += impact * impact * Decimal("0.5")
    r_eff = base_rate * (Decimal("1") - decay)
    if r_eff < ZERO:
        r_eff = ZERO
    return principal * r_eff


def _quantum_score_size(
    principal: Decimal,
    min_tvl: Decimal,
    peak_surplus: Decimal,
) -> Decimal:
    if min_tvl <= 0:
        return ZERO
    size_frac = float(min(principal / min_tvl, Decimal("1")))
    surplus_signal = float(min(max(peak_surplus, ZERO) / Decimal("100"), Decimal("5")))
    features = [size_frac, surplus_signal, size_frac * 0.7]
    weights = [0.8, 1.2, 0.5]
    try:
        circuit = create_vqc_circuit(n_features=3, features=features, weights=weights, reps=1)
        result = simulate_and_measure(circuit, shots=64)
        ones = result.get("1", 0)
        return Decimal(ones) / Decimal(64)
    except Exception:
        return Decimal("0.5")


def _build_ladder(hard_cap: Decimal, min_tvl: Decimal) -> list[Decimal]:
    steps = max(6, int(DYNAMIC_SIZE_MAX_SEARCH_STEPS or 12))
    candidates: set[Decimal] = set()
    for b in DYNAMIC_SIZE_OPT_BINS_USD or []:
        try:
            v = Decimal(str(b))
            if 0 < v <= hard_cap:
                candidates.add(v)
        except Exception:
            continue
    for f in FLASH_ROUTE_TVL_FRACTIONS or []:
        try:
            v = min_tvl * Decimal(str(f))
            if 0 < v <= hard_cap:
                candidates.add(v)
        except Exception:
            continue
    for bps in FLASH_SIZE_LADDER_BPS or []:
        try:
            v = min_tvl * Decimal(str(bps)) / BPS
            if 0 < v <= hard_cap:
                candidates.add(v)
        except Exception:
            continue
    seed = max(Decimal("100"), hard_cap / Decimal("20"))
    geo = seed
    for _ in range(steps):
        if geo > hard_cap:
            break
        candidates.add(min(geo, hard_cap))
        geo *= Decimal("1.4")
    if hard_cap > 0:
        candidates.add(hard_cap)
    ladder = sorted(c for c in candidates if c > 0)
    return ladder[: min(len(ladder), steps * 3)]


def _zero_result(
    *,
    method: str,
    reason: str,
    cannibal: bool = False,
    cannibal_msg: str = "",
    bottleneck: str = "",
    min_tvl: Decimal = ZERO,
) -> CapitalInjectionResult:
    return CapitalInjectionResult(
        optimal_injection_usd=ZERO,
        peak_surplus_usd=ZERO,
        min_tvl_usd=min_tvl,
        bottleneck_pool_id=bottleneck,
        route_cap_usd=ZERO,
        hard_cap_usd=ZERO,
        method=method,
        reason=reason,
        live_eligible=False,
        cannibalization_detected=cannibal,
        cannibalization_message=cannibal_msg,
        metadata={"error": cannibal_msg} if cannibal else {},
    )


# ==============================================================================
# MAIN ENTRY
# ==============================================================================
def compute_optimal_injection(
    *,
    pool_sequence: Iterable[str],
    pools: dict,
    path: Optional[Sequence[str]] = None,
    protocol_seq: Optional[Sequence[str]] = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    requested_principal_usd: Optional[Decimal] = None,
    base_rate: Optional[Decimal] = None,
    quote_fn: Optional[Callable[[Decimal], Decimal]] = None,
    funding_pool_id: Optional[str] = None,
) -> CapitalInjectionResult:
    """
    Official entry point.
    1) Hard cannibalization guard
    2) Exact derivative formula (L1/L2 data)
    3) Bellman + quantum fallback
    """
    pool_list = [str(p) for p in (pool_sequence or []) if p]
    src = flash_source if isinstance(flash_source, FlashSource) else FlashSource.BALANCER

    # === HARD CANNIBALIZATION GUARD ===
    is_cannibal, cannibal_msg = check_self_cannibalization(
        src.value,
        pool_list,
        funding_pool_id_override=funding_pool_id,
    )
    if is_cannibal:
        return _zero_result(
            method="cannibalization_blocked",
            reason="self_cannibalization_detected",
            cannibal=True,
            cannibal_msg=cannibal_msg,
        )

    if not (ENABLE_DYNAMIC_FLASH_SIZING or ENABLE_DYNAMIC_SIZE_OPTIMIZER):
        inj = min(
            Decimal(str(requested_principal_usd or MAX_FLASH_PRINCIPAL_USD)),
            MAX_FLASH_PRINCIPAL_USD,
        )
        return CapitalInjectionResult(
            optimal_injection_usd=inj,
            peak_surplus_usd=ZERO,
            min_tvl_usd=ZERO,
            bottleneck_pool_id="",
            route_cap_usd=inj,
            hard_cap_usd=inj,
            method="fixed_disabled",
            reason="dynamic sizing disabled in config",
            live_eligible=inj >= MIN_FLASH_PRINCIPAL_USD,
            metadata={"cannibalization_checked": True},
        )

    try:
        meta = import_metadata_for_route(pool_list, pools or {}, path=path, protocol_seq=protocol_seq)
    except ValueError as exc:
        return _zero_result(method="rejected_no_pools", reason=str(exc))

    if meta.min_tvl_usd <= 0:
        return _zero_result(
            method="rejected_no_tvl",
            reason="no executable TVL in route metadata",
            bottleneck=meta.bottleneck_pool_id,
        )

    # Caps
    frac_list = list(FLASH_ROUTE_TVL_FRACTIONS or [MAX_ROUTE_TVL_FRACTION])
    try:
        frac = max(Decimal(str(f)) for f in frac_list)
    except Exception:
        frac = Decimal(str(MAX_ROUTE_TVL_FRACTION or "0.25"))
    route_cap = meta.min_tvl_usd * frac
    hard_cap = min(route_cap, MAX_FLASH_PRINCIPAL_USD)
    if requested_principal_usd is not None:
        try:
            req = Decimal(str(requested_principal_usd))
            if req > 0:
                hard_cap = min(hard_cap, req)
        except Exception:
            pass

    # === L1 + L2 DATA ===
    bottleneck_pool = (pools or {}).get(meta.bottleneck_pool_id, {}) or {}
    f_flash, f_swap = _get_fees_from_tiers(src, bottleneck_pool)
    rin, rout = _get_rin_rout_from_metadata(
        meta.bottleneck_pool_id, pools or {}, meta.base_asset
    )

    # === EXACT DERIVATIVE FORMULA (preferred) ===
    derivative_size = compute_derivative_optimal_size(rin, rout, f_swap, f_flash)
    derivative_size, deriv_reason = _apply_friction_threshold(
        derivative_size, rin, rout, f_swap, f_flash
    )

    if derivative_size > 0:
        final_size = min(derivative_size, hard_cap)
        if final_size < MIN_FLASH_PRINCIPAL_USD:
            final_size = ZERO
        qscore = _quantum_score_size(final_size, meta.min_tvl_usd, ZERO)
        return CapitalInjectionResult(
            optimal_injection_usd=final_size.quantize(Decimal("0.01")) if final_size > 0 else ZERO,
            peak_surplus_usd=ZERO,
            min_tvl_usd=meta.min_tvl_usd,
            bottleneck_pool_id=meta.bottleneck_pool_id,
            route_cap_usd=route_cap,
            hard_cap_usd=hard_cap,
            method="exact_derivative_formula",
            reason=f"derivative_optimal ({deriv_reason})",
            quantum_score=qscore,
            live_eligible=final_size >= MIN_FLASH_PRINCIPAL_USD,
            metadata={
                "rin": str(rin),
                "rout": str(rout),
                "f_swap": str(f_swap),
                "f_flash": str(f_flash),
                "formula": "OptimalSize=(sqrt(Rin*Rout*(1-fswap)*(1-fflash))-Rin)/(1-fswap)",
                "cannibalization_checked": True,
                "friction": deriv_reason,
            },
        )

    # === FALLBACK: BELLMAN + QUANTUM ===
    if hard_cap < MIN_FLASH_PRINCIPAL_USD:
        hard_cap = MIN_FLASH_PRINCIPAL_USD

    ladder = _build_ladder(hard_cap, meta.min_tvl_usd)
    rate = base_rate if base_rate is not None else Decimal("1.0015")

    best_inj = ZERO
    best_surplus = Decimal("-1e18")
    samples: list[dict[str, Any]] = []
    quantum_scores: list[Decimal] = []

    for x in ladder:
        x = Decimal(str(x))
        if x <= 0:
            continue
        if quote_fn is not None:
            try:
                gross = Decimal(str(quote_fn(x)))
            except Exception:
                gross = _bellman_ford_surplus_curve(x, rate, meta.min_tvl_usd)
        else:
            gross = _bellman_ford_surplus_curve(x, rate, meta.min_tvl_usd)

        try:
            prof = evaluate_profitability(
                gross, x, hops=meta.hops, flash_source=src, asset=meta.base_asset
            )
            net = prof.net_profit_usd
            passes = prof.passes_gate
        except Exception:
            net = gross - x - (x * Decimal("0.0005"))
            try:
                passes = net > live_min_net_profit_usd()
            except Exception:
                passes = net > ZERO

        samples.append(
            {
                "principal_usd": str(x),
                "gross_out_usd": str(gross),
                "net_surplus_usd": str(net),
                "passes": bool(passes),
            }
        )
        if net > best_surplus and passes:
            best_surplus = net
            best_inj = x
        quantum_scores.append(_quantum_score_size(x, meta.min_tvl_usd, net))

    if best_inj <= 0:
        best_inj = ladder[len(ladder) // 2] if ladder else hard_cap
        best_surplus = ZERO
        method = "fallback_mid_ladder"
        reason = "no positive peak on Bellman curve (derivative also failed friction)"
    else:
        method = "bellman_ford_peak_with_quantum"
        reason = f"argmax surplus at {best_inj} on lowest TVL={meta.min_tvl_usd}"

    avg_q = (
        sum(quantum_scores, ZERO) / Decimal(len(quantum_scores))
        if quantum_scores
        else Decimal("0.5")
    )
    quantum_adj = (avg_q - Decimal("0.5")) * Decimal("0.02")
    final_inj = best_inj * (Decimal("1") + quantum_adj)
    final_inj = min(final_inj, hard_cap)
    if final_inj < MIN_FLASH_PRINCIPAL_USD and best_surplus <= 0:
        final_inj = ZERO

    q_final = _quantum_score_size(final_inj, meta.min_tvl_usd, best_surplus)

    return CapitalInjectionResult(
        optimal_injection_usd=final_inj.quantize(Decimal("0.01")) if final_inj > 0 else ZERO,
        peak_surplus_usd=best_surplus if best_surplus > ZERO else ZERO,
        min_tvl_usd=meta.min_tvl_usd,
        bottleneck_pool_id=meta.bottleneck_pool_id,
        route_cap_usd=route_cap,
        hard_cap_usd=hard_cap,
        method=method,
        reason=reason,
        samples=tuple(samples[:32]),
        quantum_score=q_final,
        quantum_adjustment=quantum_adj,
        live_eligible=final_inj >= MIN_FLASH_PRINCIPAL_USD and best_surplus > ZERO,
        metadata={
            "rin": str(rin),
            "rout": str(rout),
            "f_swap": str(f_swap),
            "f_flash": str(f_flash),
            "derivative_attempted": True,
            "derivative_reason": deriv_reason,
            "cannibalization_checked": True,
            "ladder_len": len(ladder),
        },
    )


def prepare_sizing_for_rust(
    pool_sequence: Iterable[str],
    pools: dict,
    *,
    path: Optional[Sequence[str]] = None,
    protocol_seq: Optional[Sequence[str]] = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    requested_principal_usd: Optional[Decimal] = None,
    base_rate: Optional[Decimal] = None,
) -> dict[str, Any]:
    """
    Bridge used by rust_engine / stager: run injector, return sizing_params dict.
    """
    result = compute_optimal_injection(
        pool_sequence=pool_sequence,
        pools=pools or {},
        path=path,
        protocol_seq=protocol_seq,
        flash_source=flash_source,
        requested_principal_usd=requested_principal_usd,
        base_rate=base_rate,
    )
    params = result.as_sizing_params()
    params["live_eligible"] = result.live_eligible
    params["reason"] = result.reason
    return params


def optimal_flash_injection(
    *,
    pool_sequence: Iterable[str],
    pools: dict,
    base_asset: str = "USDC",
    hops: int | None = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    requested_principal_usd: Decimal | None = None,
    base_rate: Decimal | None = None,
    quote_fn: Callable[[Decimal], Decimal] | None = None,
    **kwargs: Any,
) -> CapitalInjectionResult:
    """Public alias used by sizing package and ranker."""
    path = kwargs.get("path") or ([base_asset] if base_asset else None)
    return compute_optimal_injection(
        pool_sequence=pool_sequence,
        pools=pools or {},
        path=path,
        protocol_seq=kwargs.get("protocol_seq"),
        flash_source=flash_source,
        requested_principal_usd=requested_principal_usd,
        base_rate=base_rate,
        quote_fn=quote_fn,
        funding_pool_id=kwargs.get("funding_pool_id"),
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
    "optimal_flash_injection",
    "prepare_sizing_for_rust",
    "register_execution_venue",
    "register_execution_venues_from_pools",
]
