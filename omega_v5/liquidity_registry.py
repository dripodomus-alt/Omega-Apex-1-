#!/usr/bin/env python3
# ==============================================================================
# liquidity_registry.py -- targeted runtime pool registry and promotion states.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any

from .config import ASSET_UNIVERSE
from .oracle_layer import PriceUnavailable, token_price_usd


PROMOTION_STAGES = [
    "DISCOVERED",
    "LIQUIDITY_VERIFIED",
    "MULTI_VENUE",
    "MATH_SUPPORTED",
    "CALLDATA_SUPPORTED",
    "FORK_SIM_PASSED",
    "LIVE_ELIGIBLE",
]

PRODUCTION_ROUTING_SPINE = {
    "USDC.e": ["USDT", "DAI", "WPOL", "WETH", "WBTC", "USDC"],
    "USDC": ["USDC.e", "USDT", "DAI", "WPOL", "WETH"],
    "WETH": ["WBTC", "WPOL", "USDC.e"],
}

# Dynamically build lane definitions from the canonical asset universe.
BASE_ASSETS = set(ASSET_UNIVERSE.base_route_assets)
MID_ASSETS = set(ASSET_UNIVERSE.mid_token_assets)

# Hot lanes: pairs of two base assets, or a base and a major mid-token.
HOT_LANE_PAIRS = {
    tuple(sorted((a, b)))
    for a in BASE_ASSETS
    for b in (BASE_ASSETS | (MID_ASSETS & {"USDT", "DAI", "WBTC"}))
    if a != b
}

# Warm lanes: pairs involving other mid-tokens.
WARM_LANE_PAIRS = {tuple(sorted((a, b))) for a in BASE_ASSETS for b in MID_ASSETS if a != b}

SUPPORTED_CALLDATA_FAMILIES = {
    "V2_CPMM",
    "V3_CLMM",
    "ALGEBRA_CLMM",
    "CURVE_STABLE",
    "BALANCER_WEIGHTED",
}

MATH_ONLY_FAMILIES = set()

DISCOVERY_ONLY_FAMILIES = {
    "UNISWAP_V4_HOOK_AMM",
}

SEED_LIQUIDITY_SURFACES = [
    {
        "pair": "USDC/USDT",
        "protocol": "Uniswap v4",
        "pool_family": "UNISWAP_V4_HOOK_AMM",
        "fee_tier": "dynamic/not confirmed",
        "approx_liquidity_usd": Decimal("7130000"),
        "execution_status": "REJECT_UNTIL_V4_CLASSIFIED",
    },
    {
        "pair": "USDC/USDC.e",
        "protocol": "Uniswap v4",
        "pool_family": "UNISWAP_V4_HOOK_AMM",
        "fee_tier": "0.001%",
        "approx_liquidity_usd": Decimal("4090000"),
        "execution_status": "REJECT_UNTIL_V4_CLASSIFIED",
    },
    {
        "pair": "USDC/DAI",
        "protocol": "Uniswap v4",
        "pool_family": "UNISWAP_V4_HOOK_AMM",
        "fee_tier": "0.005%",
        "approx_liquidity_usd": Decimal("1680000"),
        "execution_status": "REJECT_UNTIL_V4_CLASSIFIED",
    },
    {
        "pair": "DAI/USDT",
        "protocol": "Uniswap v4",
        "pool_family": "UNISWAP_V4_HOOK_AMM",
        "fee_tier": "0.002%",
        "approx_liquidity_usd": Decimal("1560000"),
        "execution_status": "REJECT_UNTIL_V4_CLASSIFIED",
    },
    {
        "pair": "WBTC/WETH",
        "protocol": "QuickSwap v3",
        "pool_family": "ALGEBRA_CLMM",
        "pool_address": "0xac4494e30a85369e332bdb5230d6d694d4259dbc",
        "fee_tier": "0.074%",
        "approx_liquidity_usd": Decimal("412940"),
        "execution_status": "REJECT_UNTIL_ALGEBRA_ADAPTER",
    },
]


@dataclass(frozen=True)
class PoolRegistryRow:
    pair: str
    pool_address: str
    protocol: str
    pool_family: str
    fee_tier: str
    tvl_usd: str
    total_executable_liquidity_usd: str
    volume_24h_usd: str
    token_side_depth_usd: dict[str, str]
    executable_token_depth_usd: dict[str, str]
    liquidity_source: str
    adapter_status: str
    fork_sim_status: str
    execution_status: str
    promotion_stage: str
    pool_id: str = ""
    lane: str = "discovery"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def pool_family(pool: dict) -> str:
    protocol = pool.get("protocol")
    if protocol == "UniswapV2":
        return "V2_CPMM"
    if protocol == "UniswapV3":
        return "V3_CLMM"
    if protocol == "Balancer":
        return "BALANCER_WEIGHTED"
    if protocol == "Curve":
        return "CURVE_STABLE"
    if protocol == "QuickSwapV3":
        return "ALGEBRA_CLMM"
    if protocol == "UniswapV4":
        return "UNISWAP_V4_HOOK_AMM"
    return str(protocol or "UNKNOWN")


def lane_for_pair(tokens: list[str]) -> str:
    key = tuple(sorted(tokens[:2]))
    if key in HOT_LANE_PAIRS:
        return "hot"
    if key in WARM_LANE_PAIRS:
        return "warm"
    if not all(token in BASE_ASSETS or token in MID_ASSETS for token in tokens):
        return "discovery"
    return "warm" if len(tokens) >= 2 else "discovery"


def _token_side_depth(pool: dict) -> dict[str, str]:
    executable_depth = pool.get("executable_token_depth_usd")
    if isinstance(executable_depth, dict) and executable_depth:
        return {str(token): str(value) for token, value in executable_depth.items()}

    tokens = pool.get("tokens", [])
    reserves = pool.get("reserves", [])
    depth: dict[str, str] = {}
    for token, reserve in zip(tokens, reserves):
        try:
            depth[token] = str(Decimal(reserve) * token_price_usd(token))
        except (PriceUnavailable, ArithmeticError):
            depth[token] = "0"
    return depth


def _calculate_tvl_from_reserves(pool: dict) -> Decimal:
    """Authoritative TVL calculation from reserves and live oracle prices."""
    tokens = pool.get("tokens", [])
    reserves = pool.get("reserves", [])
    if not tokens or not reserves or len(tokens) != len(reserves):
        return Decimal("0")

    total = Decimal("0")
    for token, reserve in zip(tokens, reserves):
        try:
            price = token_price_usd(token)
            if price > 0:
                total += Decimal(str(reserve)) * price
        except (PriceUnavailable, ArithmeticError):
            continue
    return total


def _local_tvl_usd(pool: dict) -> Decimal:
    executable_liquidity = pool.get("total_executable_liquidity_usd")
    if executable_liquidity is not None:
        try:
            value = Decimal(str(executable_liquidity))
            if value > 0:
                return value
        except ArithmeticError:
            pass

    if pool.get("tvl_usd") is not None:
        try:
            tvl = Decimal(str(pool.get("tvl_usd")))
            if tvl > 0:
                return tvl
        except ArithmeticError:
            pass
    total = Decimal("0")
    # Fallback to the most accurate method: calculate from reserves and live prices.
    # This is the single source of truth for reserve-based TVL.
    return _calculate_tvl_from_reserves(pool)


def _status_for_family(family: str, tvl_usd: Decimal) -> tuple[str, str, str]:
    if family in SUPPORTED_CALLDATA_FAMILIES:
        if tvl_usd > 0:
            return "CALLDATA_SUPPORTED", "PENDING", "SIM_ELIGIBLE"
        return "CALLDATA_SUPPORTED", "PENDING", "REJECT_DEPTH_UNAVAILABLE"
    if family in MATH_ONLY_FAMILIES:
        return "MATH_ONLY", "PENDING", "REJECT_UNTIL_CALLDATA_ADAPTER"
    if family == "UNISWAP_V4_HOOK_AMM":
        return "DISCOVERY_ONLY", "PENDING", "REJECT_UNTIL_V4_CLASSIFIED"
    return "UNSUPPORTED", "PENDING", "REJECT_UNSUPPORTED_FAMILY"


def build_verified_pool_registry(pools: dict) -> list[PoolRegistryRow]:
    rows: list[PoolRegistryRow] = []
    for pool_id, pool in pools.items():
        tokens = pool.get("tokens", [])
        if len(tokens) < 2:
            continue
        family = pool_family(pool)
        tvl = _local_tvl_usd(pool)
        meta = pool.get("_meta", {}) if isinstance(pool.get("_meta"), dict) else {}
        adapter_status, fork_status, execution_status = _status_for_family(family, tvl)
        stage = "CALLDATA_SUPPORTED" if execution_status == "SIM_ELIGIBLE" else (
            "MATH_SUPPORTED" if adapter_status == "MATH_ONLY" else "DISCOVERED"
        )
        fee = (
            str(pool.get("fee_bps", ""))
            if "fee_bps" in pool
            else str(pool.get("swap_fee", ""))
        )
        rows.append(PoolRegistryRow(
            pair="/".join(tokens[:2]) if len(tokens) == 2 else "/".join(tokens),
            pool_address=str(pool.get("address", "")),
            pool_id=str(pool.get("balancer_pool_id") or pool.get("pool_id") or pool_id),
            protocol=str(pool.get("protocol", "")),
            pool_family=family,
            fee_tier=fee,
            tvl_usd=str(tvl),
            total_executable_liquidity_usd=str(pool.get("total_executable_liquidity_usd", tvl)),
            volume_24h_usd="",
            token_side_depth_usd=_token_side_depth(pool),
            executable_token_depth_usd=_token_side_depth(pool),
            liquidity_source=str(meta.get("total_executable_liquidity_source", "")),
            adapter_status=adapter_status,
            fork_sim_status=fork_status,
            execution_status=execution_status,
            promotion_stage=stage,
            lane=lane_for_pair(tokens),
        ))
    return rows


def registry_summary(rows: list[PoolRegistryRow]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in rows:
        summary[row.execution_status] = summary.get(row.execution_status, 0) + 1
    return summary
