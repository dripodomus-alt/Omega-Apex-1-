#!/usr/bin/env python3
# ==============================================================================
# subgraph_intel.py -- optional V3 pool discovery hints from GraphQL endpoints.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import requests

from .config import (
    ENABLE_SUBGRAPH_POOL_INTEL,
    QUICKSWAP_V3_SUBGRAPH_URL,
    SUBGRAPH_POOL_INTEL_LIMIT,
    SUBGRAPH_TIMEOUT_SECONDS,
    UNISWAP_V3_POLYGON_SUBGRAPH_URL,
)


@dataclass(frozen=True)
class SubgraphPoolCandidate:
    source: str
    protocol: str
    address: str
    token0_symbol: str
    token1_symbol: str
    token0_address: str
    token1_address: str
    fee_tier: int
    liquidity_usd: Decimal
    volume_usd: Decimal


QUERY = """
query TopPools($limit: Int!) {
  pools(
    first: $limit
    orderBy: totalValueLockedUSD
    orderDirection: desc
  ) {
    id
    feeTier
    liquidity
    totalValueLockedUSD
    volumeUSD
    token0 { id symbol decimals }
    token1 { id symbol decimals }
  }
}
"""


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0")


def _query(url: str, limit: int) -> list[dict[str, Any]]:
    if not url:
        return []
    response = requests.post(
        url,
        json={"query": QUERY, "variables": {"limit": int(limit)}},
        timeout=float(SUBGRAPH_TIMEOUT_SECONDS),
        headers={"content-type": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"])[:240])
    return list(payload.get("data", {}).get("pools", []) or [])


def discover_subgraph_v3_candidates(limit: int | None = None) -> tuple[list[SubgraphPoolCandidate], dict[str, Any]]:
    if not ENABLE_SUBGRAPH_POOL_INTEL:
        return [], {"enabled": False}

    cap = int(limit or SUBGRAPH_POOL_INTEL_LIMIT)
    sources = [
        ("uniswap_v3_polygon_subgraph", "UniswapV3", UNISWAP_V3_POLYGON_SUBGRAPH_URL),
        ("quickswap_v3_subgraph", "QuickSwapV3", QUICKSWAP_V3_SUBGRAPH_URL),
    ]
    candidates: list[SubgraphPoolCandidate] = []
    errors: dict[str, str] = {}

    for name, protocol, url in sources:
        try:
            rows = _query(url, cap)
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}: {exc}"
            continue
        for row in rows:
            token0 = row.get("token0") or {}
            token1 = row.get("token1") or {}
            address = str(row.get("id", "")).lower()
            if not address.startswith("0x") or len(address) != 42:
                continue
            try:
                fee_tier = int(row.get("feeTier") or 0)
            except Exception:
                fee_tier = 0
            candidates.append(SubgraphPoolCandidate(
                source=name,
                protocol=protocol,
                address=address,
                token0_symbol=str(token0.get("symbol", "")),
                token1_symbol=str(token1.get("symbol", "")),
                token0_address=str(token0.get("id", "")).lower(),
                token1_address=str(token1.get("id", "")).lower(),
                fee_tier=fee_tier,
                liquidity_usd=_decimal(row.get("totalValueLockedUSD")),
                volume_usd=_decimal(row.get("volumeUSD")),
            ))

    return candidates, {
        "enabled": True,
        "candidate_count": len(candidates),
        "errors": errors,
        "limit_per_source": cap,
        "execution_policy": "discovery_hints_only_rpc_verification_required",
    }
