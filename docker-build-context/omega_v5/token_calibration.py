#!/usr/bin/env python3
# ==============================================================================
# token_calibration.py -- base/mid token calibration for route staging.
#
# The calibration report is intentionally read-only. It derives the tokens used by
# the directional quote graph, validates low-risk token metadata through Multicall3
# with Redis TTL caching, and attaches live oracle price/source state.
# ==============================================================================

from __future__ import annotations

import time
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any, Iterable

from web3 import Web3

from . import rpc_layer
from .config import CHAIN_ID, TOKEN_CALIBRATION_CACHE_TTL_SECONDS, TOKEN_CALIBRATION_MAX_MULTICALL_BATCH
from .oracle_layer import PriceUnavailable, TOKEN_USD_SOURCE, refresh_token_prices, token_price_usd
from .redis_cache import get_json, key as redis_key, set_json, status as redis_status
from .rpc_layer import TOKEN_ADDRESSES, TOKEN_DECIMALS


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(v) for v in value]
    return value


def _route_path(route: Any) -> tuple[str, ...]:
    raw = getattr(route, "path", None)
    if raw is None and isinstance(route, dict):
        raw = route.get("path")
    return tuple(str(item) for item in (raw or []) if item)


def _classify_route_tokens(routes: Iterable[Any], rates: dict) -> dict[str, set[str]]:
    base_tokens: set[str] = set()
    mid_tokens: set[str] = set()
    for route in routes:
        path = _route_path(route)
        if len(path) >= 2:
            base_tokens.add(path[0])
        if len(path) > 2:
            mid_tokens.update(path[1:-1])

    all_graph_tokens: set[str] = set()
    for token_in, token_out in rates:
        all_graph_tokens.add(str(token_in))
        all_graph_tokens.add(str(token_out))

    if not base_tokens and not mid_tokens:
        mid_tokens.update(all_graph_tokens)

    return {
        "base_tokens": base_tokens,
        "mid_tokens": mid_tokens - base_tokens,
        "all_graph_tokens": all_graph_tokens,
        "utilized_tokens": base_tokens | mid_tokens,
    }


def _token_pool_exposure(pools: dict[str, dict]) -> dict[str, dict[str, Any]]:
    exposure: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "pool_count": 0,
            "protocols": Counter(),
            "total_pool_liquidity_usd": Decimal("0"),
            "max_pool_liquidity_usd": Decimal("0"),
        }
    )
    for pool in pools.values():
        tokens = [str(item) for item in pool.get("tokens", []) if item]
        if not tokens:
            tokens = [str(pool.get("token0") or ""), str(pool.get("token1") or "")]
            tokens = [item for item in tokens if item]
        liq = _decimal(pool.get("total_executable_liquidity_usd") or pool.get("tvl_usd"))
        protocol = str(pool.get("protocol") or "")
        for token in dict.fromkeys(tokens):
            row = exposure[token]
            row["pool_count"] += 1
            if protocol:
                row["protocols"][protocol] += 1
            if liq > 0:
                row["total_pool_liquidity_usd"] += liq
                row["max_pool_liquidity_usd"] = max(row["max_pool_liquidity_usd"], liq)
    return exposure


def _cached_decimals(address: str) -> int | None:
    cached = get_json(redis_key("token_calibration", "decimals", CHAIN_ID, address.lower()))
    if isinstance(cached, dict):
        try:
            return int(cached.get("decimals"))
        except Exception:
            return None
    return None


def _write_cached_decimals(symbol: str, address: str, decimals: int) -> None:
    set_json(
        redis_key("token_calibration", "decimals", CHAIN_ID, address.lower()),
        {
            "symbol": symbol,
            "address": address.lower(),
            "chain_id": CHAIN_ID,
            "decimals": int(decimals),
            "source": "multicall3_erc20_decimals",
            "updated_at": int(time.time()),
        },
        ttl=TOKEN_CALIBRATION_CACHE_TTL_SECONDS,
    )


def _fetch_live_decimals_multicall(symbols: Iterable[str]) -> dict[str, int]:
    resolved: dict[str, int] = {}
    missing: list[tuple[str, str]] = []
    for symbol in dict.fromkeys(str(item) for item in symbols if item):
        address = TOKEN_ADDRESSES.get(symbol)
        if not address:
            continue
        cached = _cached_decimals(address)
        if cached is not None:
            resolved[symbol] = cached
        else:
            missing.append((symbol, address))

    if not missing or not rpc_layer.RPC_LIVE or rpc_layer.w3 is None:
        return resolved

    batch_size = max(1, int(TOKEN_CALIBRATION_MAX_MULTICALL_BATCH or 96))
    for idx in range(0, len(missing), batch_size):
        chunk = missing[idx : idx + batch_size]
        calls = []
        for _, address in chunk:
            contract = rpc_layer.w3.eth.contract(
                address=Web3.to_checksum_address(address),
                abi=rpc_layer._ABI_ERC20,
            )
            calls.append((address, True, rpc_layer._encode_fn(contract, "decimals")))
        try:
            results = rpc_layer.multicall3_aggregate(calls)
        except Exception:
            continue
        for (symbol, address), (ok, payload) in zip(chunk, results):
            if not ok or not payload:
                continue
            try:
                decimals = int(rpc_layer.w3.codec.decode(["uint8"], payload)[0])
            except Exception:
                continue
            resolved[symbol] = decimals
            _write_cached_decimals(symbol, address, decimals)
    return resolved


def build_token_calibration_report(
    *,
    rates: dict,
    pools: dict[str, dict],
    routes: Iterable[Any],
) -> dict[str, Any]:
    """
    Calibrate every base/mid token actually used by the route graph.

    Price truth stays dynamic through the existing oracle stack. Decimals are
    metadata, so Redis TTL caching is used to reduce duplicate RPC calls while
    Multicall3 keeps uncached validation batched.
    """
    refresh_token_prices(force=False)
    scope = _classify_route_tokens(routes, rates)
    exposure = _token_pool_exposure(pools)
    edges_out: Counter[str] = Counter()
    edges_in: Counter[str] = Counter()
    for (token_in, token_out), entries in rates.items():
        edges_out[str(token_in)] += len(entries)
        edges_in[str(token_out)] += len(entries)

    live_decimals = _fetch_live_decimals_multicall(scope["utilized_tokens"])
    redis_ok, redis_detail = redis_status()

    rows: list[dict[str, Any]] = []
    issue_counts: Counter[str] = Counter()
    for symbol in sorted(scope["utilized_tokens"]):
        address = TOKEN_ADDRESSES.get(symbol, "")
        registry_decimals = TOKEN_DECIMALS.get(symbol)
        onchain_decimals = live_decimals.get(symbol)
        token_exposure = exposure.get(symbol, {})
        roles = []
        if symbol in scope["base_tokens"]:
            roles.append("base")
        if symbol in scope["mid_tokens"]:
            roles.append("mid")

        issues: list[str] = []
        if not address:
            issues.append("missing_registry_address")
        if registry_decimals is None:
            issues.append("missing_registry_decimals")
        if address and onchain_decimals is None:
            issues.append("missing_live_decimals")
        if registry_decimals is not None and onchain_decimals is not None and int(registry_decimals) != int(onchain_decimals):
            issues.append("decimals_mismatch")

        try:
            price = token_price_usd(symbol)
            price_source = TOKEN_USD_SOURCE.get(symbol, "oracle_layer")
        except PriceUnavailable:
            price = Decimal("0")
            price_source = ""
            issues.append("missing_live_oracle_price")

        for issue in issues:
            issue_counts[issue] += 1

        rows.append({
            "symbol": symbol,
            "roles": roles,
            "address": address,
            "registry_decimals": registry_decimals,
            "live_decimals": onchain_decimals,
            "decimals_status": "pass" if not any(item.startswith("missing") or item == "decimals_mismatch" for item in issues) else "review",
            "oracle_price_usd": price,
            "oracle_source": price_source,
            "oracle_status": "pass" if price > 0 else "review",
            "directional_edges_out": edges_out.get(symbol, 0),
            "directional_edges_in": edges_in.get(symbol, 0),
            "pool_count": int(token_exposure.get("pool_count", 0) or 0),
            "protocols": dict(sorted((token_exposure.get("protocols") or Counter()).items())),
            "total_pool_liquidity_usd": token_exposure.get("total_pool_liquidity_usd", Decimal("0")),
            "max_pool_liquidity_usd": token_exposure.get("max_pool_liquidity_usd", Decimal("0")),
            "issues": issues,
        })

    return _json_ready({
        "schema_version": "omega_v5.token_calibration.v1",
        "chain_id": CHAIN_ID,
        "block": rpc_layer.BLOCK,
        "calibrated_at": int(time.time()),
        "scope": {
            "base_token_count": len(scope["base_tokens"]),
            "mid_token_count": len(scope["mid_tokens"]),
            "utilized_token_count": len(scope["utilized_tokens"]),
            "graph_token_count": len(scope["all_graph_tokens"]),
            "base_tokens": sorted(scope["base_tokens"]),
            "mid_tokens": sorted(scope["mid_tokens"]),
        },
        "runtime": {
            "oracle_policy": "live oracle stack only; no hardcoded USD fallback admitted into route scoring",
            "multicall_policy": "ERC20 decimals validated in Multicall3 batches before route reports are trusted",
            "redis_metadata_cache": {
                "enabled": redis_ok,
                "detail": redis_detail,
                "ttl_seconds": TOKEN_CALIBRATION_CACHE_TTL_SECONDS,
            },
            "max_multicall_batch": TOKEN_CALIBRATION_MAX_MULTICALL_BATCH,
        },
        "issue_counts": dict(sorted(issue_counts.items())),
        "all_clear": not issue_counts,
        "tokens": rows,
    })

def calibrate_tokens(tokens: Iterable[str]) -> dict[str, Any]:
    """Compatibility API for callers that only have a token list.

    Direct callers get the same oracle/Multicall3/Redis validation rows as the
    route-aware staging report. Tokens are marked as requested because there is
    no route graph to distinguish base from mid roles.
    """
    unique_tokens = sorted(dict.fromkeys(str(item) for item in tokens if item))
    synthetic_rates = {(token, token): [] for token in unique_tokens}
    synthetic_routes = [{"path": [token, token]} for token in unique_tokens]
    report = build_token_calibration_report(
        rates=synthetic_rates,
        pools={},
        routes=synthetic_routes,
    )
    report["scope"]["mode"] = "direct_token_list"
    report["scope"]["requested_tokens"] = unique_tokens
    for row in report.get("tokens", []):
        row["roles"] = ["requested"]
    return report