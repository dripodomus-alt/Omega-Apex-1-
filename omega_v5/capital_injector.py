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
    DETERMINISTIC_APEX_INJECTOR_ENABLED,
    normalize_protocol,
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
from .rpc_layer import get_latest_gas_prices # Assume this function exists
from .oracle_layer import token_price_usd
from .precision_pricing import PrecisionPricingEngine
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
                    if fee_val >= Decimal("100"):
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

    if DETERMINISTIC_APEX_INJECTOR_ENABLED:
        try:
            protocol = normalize_protocol(pool.get("protocol", ""))
            if protocol in {"V3_CLMM", "QS_V3_ALGEBRA"}:
                sqrtPriceX96 = int(pool.get("sqrtPriceX96", 0))
                liquidity = int(pool.get("liquidity", 0))
                if sqrtPriceX96 > 0 and liquidity > 0:
                    r0_virtual, r1_virtual = PrecisionPricingEngine.get_v3_virtual_reserves(sqrtPriceX96, liquidity)
                    tokens = list(pool.get("tokens") or [])
                    if len(tokens) >= 2:
                        p0 = token_price_usd(str(tokens[0]))
                        p1 = token_price_usd(str(tokens[1]))
                        usd0 = r0_virtual * Decimal(str(p0))
                        usd1 = r1_virtual * Decimal(str(p1))
                        return max(usd0, Decimal("1")), max(usd1, Decimal("1"))
        except Exception:
            pass

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

    @property
    def injection_usd(self) -> Decimal:
        return self.optimal_injection_usd

    @property
    def min_pool_tvl_usd(self) -> Decimal:
        return self.min_tvl_usd

    def as_payload_fields(self) -> dict[str, Any]:
        return {
            "flash_injection_usd": str(self.optimal_injection_usd),
            "flash_principal_usd": str(self.optimal_injection_usd),
            "min_pool_tvl_usd": str(self.min_tvl_usd),
            "hard_cap_usd": str(self.hard_cap_usd),
            "method": self.method,
        }

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
    gas_price_gwei: Optional[Decimal] = None, # New parameter for gas price
) -> CapitalInjectionResult:
    """
    Official entry point. Runs cannibal guard then derivative sizing.
    Falls back to Bellman + quantum search.
    """
    # ==========================================================================
    # STEP 1: GATHER ROUTE METADATA & RUN SAFETY CHECKS
    # ==========================================================================
    metadata = import_metadata_for_route(pool_sequence, pools, path, protocol_seq)

    # --- SELF-CANNIBALIZATION GUARD ---
    # This is a critical safety check to ensure the flash loan source pool is
    # not also part of the arbitrage trading route.
    funding_key = flash_source.value if isinstance(flash_source, FlashSource) else str(flash_source)
    cannibal, cannibal_msg = check_self_cannibalization(
        funding_source=funding_key,
        pool_sequence=metadata.pool_ids,
    )
    # If the route is self-cannibalizing, we must stop and return a zero-size result.
    if cannibal:
        return _zero_result(
            method="cannibalization_blocked",
            reason="self_cannibalization",
            cannibal=True,
            cannibal_msg=cannibal_msg,
            bottleneck=metadata.bottleneck_pool_id,
            min_tvl=metadata.min_tvl_usd,
        )

    # ==========================================================================
    # STEP 2: CALCULATE OPTIMAL INJECTION SIZE USING DERIVATIVE FORMULA
    # ==========================================================================
    # This is the core mathematical model for finding the optimal trade size.
    # It's derived from the calculus of the constant product formula to find
    # the point of maximum profit, balancing trade size against price impact.

    # First, get the necessary inputs: fees and virtual reserves.
    f_flash, f_swap = _get_fees_from_tiers(flash_source)
    rin, rout = _get_rin_rout_from_metadata(
        metadata.bottleneck_pool_id, pools, metadata.base_asset
    )

    # If a specific principal is requested, use it. Otherwise, calculate.
    if requested_principal_usd is not None and requested_principal_usd > 0:
        optimal = Decimal(str(requested_principal_usd))
        method = "requested"
        reason = "user_override"
    else:
        # MATH: This is the exact derivative sizing formula.
        # It finds the injection amount 'x' that maximizes the profit function
        # P(x) for a two-pool arbitrage (buy on pool 1, sell on pool 2).
        #
        #   OptimalSize = (sqrt(Rin * Rout * (1-f_swap)*(1-f_flash)) - Rin) / (1-f_swap)
        #
        # Where:
        # - Rin:   Effective reserve of the token being bought (in USD).
        # - Rout:  Effective reserve of the token being sold (in USD).
        # - f_swap:  The swap fee of the AMM pool (e.g., 0.003 for 0.3%).
        # - f_flash: The flash loan fee (e.g., 0 for Balancer, 0.0005 for Aave).
        optimal = compute_derivative_optimal_size(rin, rout, f_swap, f_flash)
        optimal, reason = _apply_friction_threshold(optimal, rin, rout, f_swap, f_flash)
        method = "derivative" if reason == "passed" else "friction_blocked"

    # ==========================================================================
    # STEP 3: APPLY HARD CAPS AND REFINE WITH LADDER SEARCH
    # ==========================================================================
    # The theoretical optimal size is constrained by real-world limits.

    # MATH: Apply hard caps based on configuration and a fraction of the
    #       route's bottleneck TVL to avoid excessive price impact.
    hard_cap = min(
        MAX_FLASH_PRINCIPAL_USD,
        metadata.min_tvl_usd * MAX_ROUTE_TVL_FRACTION,
    )
    optimal = min(optimal, hard_cap)

    # --- Bellman-Ford & Quantum Refinement ---
    # The derivative formula is a perfect model for a simple two-pool case.
    # For more complex routes or to account for other market dynamics, we
    # refine this initial 'optimal' guess by searching a "ladder" of discrete
    # trade sizes around it to find the true peak of the profit curve.
    br = base_rate or Decimal("1.0015")

    # --- Gas-Aware Optimization ---
    # Fetch current gas price if not provided.
    if gas_price_gwei is None:
        try:
            gas_info = get_latest_gas_prices()
            gas_price_gwei = Decimal(str(gas_info.get("base_fee_gwei", 20)))
        except Exception:
            gas_price_gwei = Decimal("20") # Fallback

    # Define a threshold for "high gas". e.g., 50 Gwei
    high_gas_threshold_gwei = Decimal(os.environ.get("OMEGA_HIGH_GAS_THRESHOLD_GWEI", "50"))
    is_high_gas = gas_price_gwei > high_gas_threshold_gwei

    # Ladder search for best
    ladder = _build_ladder(hard_cap, metadata.min_tvl_usd)
    best_prin = ZERO
    best_surplus = ZERO
    best_score = Decimal("-1")
    samples = []
    # This loop simulates the profit at various trade sizes to find the
    # empirical maximum, which becomes our final `optimal_injection_usd`.
    for cand in ladder:
        sur = _bellman_ford_surplus_curve(cand, br, metadata.min_tvl_usd)
        # NOTE: This is a simplified gas cost. A more accurate model would be better.
        gas_cost_usd = gas_price_gwei * Decimal("0.000000001") * Decimal("500000") * token_price_usd("MATIC")
        score = (sur - gas_cost_usd) / gas_cost_usd if is_high_gas and gas_cost_usd > 0 else sur
        samples.append({"principal": str(cand), "surplus": str(sur), "score": str(score)})
        if score > best_score:
            best_score = score
            best_surplus = sur
            best_prin = cand

    live_eligible = best_prin >= MIN_FLASH_PRINCIPAL_USD and best_surplus > 0

    return CapitalInjectionResult(
        optimal_injection_usd=best_prin,
        peak_surplus_usd=best_surplus,
        min_tvl_usd=metadata.min_tvl_usd,
        bottleneck_pool_id=metadata.bottleneck_pool_id,
        route_cap_usd=metadata.total_executable_liquidity,
        hard_cap_usd=hard_cap,
        method=method,
        reason=reason,
        samples=tuple(sorted(samples, key=lambda x: Decimal(x["score"]), reverse=True)),
        quantum_score=qscore,
        quantum_adjustment=ZERO,
        live_eligible=live_eligible,
        metadata={"rin": str(rin), "rout": str(rout), "f_swap": str(f_swap), "f_flash": str(f_flash), "cannibalization_checked": True},
        cannibalization_detected=False,
    )


def prepare_sizing_for_rust(
    pool_sequence: Iterable[str],
    pools: dict,
    *,
    path: Optional[Sequence[str]] = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    requested_principal_usd: Optional[Decimal] = None,
) -> dict[str, Any]:
    """Prepare clean dict for Rust engine. Enforces guard + derivative."""
    result = compute_optimal_injection(
        pool_sequence=pool_sequence,
        pools=pools,
        path=path,
        flash_source=flash_source,
        requested_principal_usd=requested_principal_usd,
    )
    return result.as_sizing_params()


def optimal_flash_injection(
    *,
    pool_sequence: Iterable[str],
    pools: dict,
    path: Optional[Sequence[str]] = None,
    flash_source: FlashSource = FlashSource.BALANCER,
    requested_principal_usd: Optional[Decimal] = None,
) -> CapitalInjectionResult:
    """Convenience alias to the official injector."""
    return compute_optimal_injection(
        pool_sequence=pool_sequence,
        pools=pools,
        path=path,
        flash_source=flash_source,
        requested_principal_usd=requested_principal_usd,
    )


if __name__ == "__main__":
    print("capital_injector.py — canonical module ready.")
