#!/usr/bin/env python3
# ==============================================================================
# curve_pool_registry.py -- official Curve Polygon pool metadata importer.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import requests
from web3 import Web3


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@dataclass(frozen=True)
class CurvePoolImportResult:
    registry: dict[str, dict[str, Any]]
    stats: dict[str, Any]


def _decimal_or_zero(value: Any) -> Decimal:
    try:
        dec = Decimal(str(value))
        return dec if dec > 0 else Decimal("0")
    except Exception:
        return Decimal("0")


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clean_symbol(value: Any) -> str:
    symbol = str(value or "").strip()
    if symbol in {"MATIC", "WMATIC", "POL"}:
        return "WPOL"
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in symbol)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "UNKNOWN"


def _coin_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    coins = row.get("coins")
    if isinstance(coins, list) and coins:
        return [coin for coin in coins if isinstance(coin, dict)]

    addresses = row.get("coinsAddresses") if isinstance(row.get("coinsAddresses"), list) else []
    decimals = row.get("decimals") if isinstance(row.get("decimals"), list) else []
    result: list[dict[str, Any]] = []
    for idx, address in enumerate(addresses):
        result.append({
            "address": address,
            "symbol": f"COIN{idx}",
            "decimals": decimals[idx] if idx < len(decimals) else 18,
        })
    return result


def _register_or_resolve_symbol(
    *,
    address: str,
    api_symbol: str,
    decimals: int,
    address_to_symbol: dict[str, str],
    token_addresses: dict[str, str],
    token_decimals: dict[str, int],
    token_discovery_status: dict[str, str],
) -> str:
    address_l = address.lower()
    existing = address_to_symbol.get(address_l)
    if existing:
        return existing

    base_symbol = _clean_symbol(api_symbol)
    if base_symbol not in token_addresses:
        symbol = base_symbol
    else:
        symbol = f"CURVE_{base_symbol}_{address_l[2:8].upper()}"

    token_addresses[symbol] = Web3.to_checksum_address(address)
    token_decimals[symbol] = decimals
    token_discovery_status[symbol] = "CURVE_API_DISCOVERY_ONLY_LIVE_RPC_REQUIRED"
    address_to_symbol[address_l] = symbol
    return symbol


def load_curve_pool_registry(
    *,
    api_base_url: str,
    families: list[str],
    address_to_symbol: dict[str, str],
    token_addresses: dict[str, str],
    token_decimals: dict[str, int],
    token_discovery_status: dict[str, str],
    known_pool_addresses: set[str],
    max_pools: int,
    min_usd_tvl: Decimal,
    timeout_seconds: float = 12.0,
) -> CurvePoolImportResult:
    registry: dict[str, dict[str, Any]] = {}
    stats: dict[str, Any] = {
        "enabled": True,
        "source": "curve_official_api",
        "api_base_url": api_base_url,
        "families": families,
        "rows": 0,
        "promoted": 0,
        "skipped": {},
        "by_family": {},
        "tokens_added": 0,
        "min_usd_tvl": str(min_usd_tvl),
    }
    skipped: dict[str, int] = {}
    by_family: dict[str, int] = {}
    token_count_before = len(token_addresses)

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    rows: list[tuple[str, dict[str, Any]]] = []
    for family in families:
        family = family.strip()
        if not family:
            continue
        try:
            response = requests.get(
                f"{api_base_url.rstrip('/')}/getPools/polygon/{family}",
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            pool_rows = payload.get("data", {}).get("poolData", [])
            if not isinstance(pool_rows, list):
                skip(f"{family}_bad_payload")
                continue
            stats["rows"] += len(pool_rows)
            for row in pool_rows:
                if isinstance(row, dict):
                    rows.append((family, row))
        except Exception as exc:
            stats.setdefault("errors", {})[family] = f"{type(exc).__name__}: {exc}"

    rows.sort(key=lambda item: _decimal_or_zero(item[1].get("usdTotal")), reverse=True)
    unbounded = int(max_pools or 0) <= 0
    for family, row in rows:
        if not unbounded and len(registry) >= max_pools:
            skip("max_pools_reached")
            break

        address = str(row.get("address", "")).strip()
        if not Web3.is_address(address) or address.lower() == ZERO_ADDRESS:
            skip("bad_pool_address")
            continue
        if address.lower() in known_pool_addresses:
            skip("duplicate_pool_address")
            continue

        usd_total = _decimal_or_zero(row.get("usdTotal"))
        if usd_total < min_usd_tvl:
            skip("below_min_tvl")
            continue

        coins: list[str] = []
        coin_addresses: list[str] = []
        coin_decimals: list[int] = []
        for coin in _coin_rows(row):
            coin_addr = str(coin.get("address", "")).strip()
            if not Web3.is_address(coin_addr) or coin_addr.lower() == ZERO_ADDRESS:
                continue
            dec = _int_or_default(coin.get("decimals"), 18)
            symbol = _register_or_resolve_symbol(
                address=coin_addr,
                api_symbol=str(coin.get("symbol", "")),
                decimals=dec,
                address_to_symbol=address_to_symbol,
                token_addresses=token_addresses,
                token_decimals=token_decimals,
                token_discovery_status=token_discovery_status,
            )
            coins.append(symbol)
            coin_addresses.append(Web3.to_checksum_address(coin_addr))
            coin_decimals.append(dec)

        if len(coins) < 2:
            skip("lt_two_supported_coins")
            continue
        if len(set(addr.lower() for addr in coin_addresses)) != len(coin_addresses):
            skip("duplicate_coin_address")
            continue

        try:
            amp = Decimal(str(row.get("amplificationCoefficient") or "100"))
        except Exception:
            amp = Decimal("100")
        fee_bps = Decimal("4")
        fee_raw = row.get("fee")
        if fee_raw not in {None, ""}:
            try:
                fee_bps = Decimal(str(fee_raw))
                if fee_bps > 10000:
                    fee_bps = fee_bps / Decimal("1e6")
            except Exception:
                fee_bps = Decimal("4")

        pool_id = (
            f"CURVE_{family}_{row.get('id', '')}_{coins[0]}_{coins[1]}_{address[-6:]}"
            .replace(".", "_")
            .replace("-", "_")
        )
        registry[pool_id] = {
            "protocol": "Curve",
            "token0": coins[0],
            "token1": coins[1],
            "tokens": coins,
            "token_addresses": coin_addresses,
            "token_decimals": coin_decimals,
            "address": Web3.to_checksum_address(address),
            "A": amp,
            "fee_bps": fee_bps,
            "tvl_usd": usd_total,
            "pool_family": "curve_stable" if family != "factory-crypto" else "curve_crypto",
            "_meta": {
                "discovery_source": "curve_official_api",
                "curve_family": family,
                "curve_id": str(row.get("id", "")),
                "curve_name": str(row.get("name", "")),
                "curve_symbol": str(row.get("symbol", "")),
                "asset_type": str(row.get("assetTypeName", "")),
                "implementation": str(row.get("implementation", "")),
                "lp_token_address": str(row.get("lpTokenAddress", "")),
                "gauge_address": str(row.get("gaugeAddress", "")),
                "api_usd_total": str(usd_total),
                "execution_policy": "curve_api_metadata_live_rpc_state_required",
            },
        }
        known_pool_addresses.add(address.lower())
        by_family[family] = by_family.get(family, 0) + 1

    stats["promoted"] = len(registry)
    stats["unbounded"] = unbounded
    stats["skipped"] = skipped
    stats["by_family"] = by_family
    stats["tokens_added"] = len(token_addresses) - token_count_before
    return CurvePoolImportResult(registry, stats)
