#!/usr/bin/env python3
# ==============================================================================
# polygon_token_list.py -- Polygon token-list discovery candidate importer.
#
# This source expands discovery coverage only. Candidates are promoted into the
# runtime symbol/address map so factory discovery can probe base pairs, but live
# execution still requires pool quality, oracle/quote, adapter, and exact-call
# gates elsewhere in the pipeline.
# ==============================================================================

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from typing import Iterable

import requests

from .config import (
    ENABLE_POLYGON_TOKEN_LIST_DISCOVERY,
    POLYGON_TOKEN_LIST_CACHE_TTL_SECONDS,
    POLYGON_TOKEN_LIST_MAX_CANDIDATES,
)
from .paths import cache_path
from .redis_cache import get_json, key as redis_key, set_json


TOKEN_LIST_BRANCH = "dev"
TOKEN_LIST_FILES = (
    "src/tokens/defaultTokens.json",
    "src/tokens/mappedTokens.json",
)
RAW_BASE = f"https://raw.githubusercontent.com/0xPolygon/polygon-token-list/{TOKEN_LIST_BRANCH}"
ZERO = "0x0000000000000000000000000000000000000000"
POLYGON_NATIVE_SENTINEL = "0x0000000000000000000000000000000000001010"
CACHE_PATH = cache_path("polygon_token_list_candidates.json")
CACHE_VERSION = 2
SAFE_SYMBOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,23}$")


@dataclass(frozen=True)
class PolygonTokenCandidate:
    symbol: str
    name: str
    address: str
    decimals: int
    tags: tuple[str, ...]
    source_file: str
    origin_symbol: str
    discovery_status: str = "POLYGON_TOKEN_LIST_DISCOVERY_CANDIDATE"


def _load_json_file(path: str) -> list[dict]:
    url = f"{RAW_BASE}/{path}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, list) else []


def _cache_payload(candidates: list[PolygonTokenCandidate], stats: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": time.time(),
        "cache_version": CACHE_VERSION,
        "source": "0xPolygon/polygon-token-list",
        "branch": TOKEN_LIST_BRANCH,
        "stats": stats,
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    set_json(
        redis_key("polygon_token_list", "candidates"),
        payload,
        ttl=POLYGON_TOKEN_LIST_CACHE_TTL_SECONDS,
    )


def _load_cached_payload() -> tuple[list[PolygonTokenCandidate], dict] | None:
    payload = get_json(redis_key("polygon_token_list", "candidates"))
    if not isinstance(payload, dict) and CACHE_PATH.exists():
        try:
            payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            payload = None
    if not isinstance(payload, dict):
        return None
    fetched_at = float(payload.get("fetched_at") or 0)
    if int(payload.get("cache_version") or 0) != CACHE_VERSION:
        return None
    if time.time() - fetched_at > POLYGON_TOKEN_LIST_CACHE_TTL_SECONDS:
        return None
    rows = payload.get("candidates") or []
    candidates = [
        PolygonTokenCandidate(
            symbol=str(row["symbol"]),
            name=str(row.get("name") or row["symbol"]),
            address=str(row["address"]),
            decimals=int(row["decimals"]),
            tags=tuple(row.get("tags") or ()),
            source_file=str(row.get("source_file") or ""),
            origin_symbol=str(row.get("origin_symbol") or row["symbol"]),
            discovery_status=str(row.get("discovery_status") or "POLYGON_TOKEN_LIST_DISCOVERY_CANDIDATE"),
        )
        for row in rows
        if isinstance(row, dict)
        and row.get("symbol")
        and row.get("address")
        and SAFE_SYMBOL_RE.match(str(row.get("symbol")))
    ]
    return candidates, dict(payload.get("stats") or {})


def _candidate_priority(candidate: PolygonTokenCandidate) -> tuple[int, int, str]:
    tags = set(candidate.tags)
    stable = 0 if "stablecoin" in tags or candidate.symbol.upper() in {"USDC", "USDT", "DAI", "FRAX"} else 1
    pos = 0 if "pos" in tags else 1
    return stable, pos, candidate.symbol.upper()


def fetch_polygon_pos_candidates(
    *,
    known_addresses: Iterable[str],
    known_symbols: Iterable[str],
    max_candidates: int = POLYGON_TOKEN_LIST_MAX_CANDIDATES,
    force_refresh: bool = False,
) -> tuple[list[PolygonTokenCandidate], dict]:
    """
    Returns Polygon PoS token-list candidates that do not collide with the
    existing runtime registry.

    Only wrappedNetworkId == -1 entries are used. The repo's own examples map
    WETH and USDC.e to this network id, so it is the Polygon PoS wrapped-token
    lane for the current token-list format.
    """
    if not ENABLE_POLYGON_TOKEN_LIST_DISCOVERY:
        return [], {"enabled": False}

    unbounded = int(max_candidates or 0) <= 0
    known_addr_set = {str(address).lower() for address in known_addresses if address}
    known_symbol_set = {str(symbol).upper() for symbol in known_symbols if symbol}
    if not force_refresh:
        cached = _load_cached_payload()
        if cached:
            cached_candidates, cached_stats = cached
            filtered = [
                candidate
                for candidate in cached_candidates
                if candidate.address.lower() not in known_addr_set
                and candidate.symbol.upper() not in known_symbol_set
            ]
            if not unbounded:
                filtered = filtered[:max_candidates]
            stats = dict(cached_stats)
            stats.update({"cache": "hit", "returned": len(filtered), "unbounded": unbounded})
            return filtered, stats

    all_candidates: dict[str, PolygonTokenCandidate] = {}
    seen_rows = 0
    skipped = {
        "known_address": 0,
        "symbol_conflict": 0,
        "zero_or_native_sentinel": 0,
        "non_pos": 0,
        "blocked_bridge_tags": 0,
        "bad_symbol": 0,
        "bad_shape": 0,
    }

    for source_file in TOKEN_LIST_FILES:
        rows = _load_json_file(source_file)
        for row in rows:
            if not isinstance(row, dict):
                skipped["bad_shape"] += 1
                continue
            for wrapped in row.get("wrappedTokens") or []:
                if not isinstance(wrapped, dict):
                    skipped["bad_shape"] += 1
                    continue
                if wrapped.get("wrappedNetworkId") != -1:
                    continue
                address = str(wrapped.get("wrappedTokenAddress") or "").strip()
                if not address:
                    skipped["bad_shape"] += 1
                    continue
                addr_l = address.lower()
                if addr_l in {ZERO, POLYGON_NATIVE_SENTINEL}:
                    skipped["zero_or_native_sentinel"] += 1
                    continue
                tags = tuple(
                    sorted({
                        str(tag)
                        for source in (row.get("tags") or [], wrapped.get("tags") or [])
                        for tag in (source if isinstance(source, list) else [source])
                        if tag is not None
                    })
                )
                if "pos" not in tags:
                    skipped["non_pos"] += 1
                    continue
                if "noDeposit" in tags or "noWithdraw" in tags:
                    skipped["blocked_bridge_tags"] += 1
                    continue
                symbol = str(wrapped.get("symbol") or row.get("symbol") or "").strip()
                if not symbol:
                    skipped["bad_shape"] += 1
                    continue
                if not SAFE_SYMBOL_RE.match(symbol):
                    skipped["bad_symbol"] += 1
                    continue
                if addr_l in known_addr_set:
                    skipped["known_address"] += 1
                    continue
                if symbol.upper() in known_symbol_set:
                    skipped["symbol_conflict"] += 1
                    continue
                try:
                    decimals = int(wrapped.get("decimals") or row.get("decimals"))
                except Exception:
                    skipped["bad_shape"] += 1
                    continue
                if decimals < 0 or decimals > 36:
                    skipped["bad_shape"] += 1
                    continue
                seen_rows += 1
                all_candidates[addr_l] = PolygonTokenCandidate(
                    symbol=symbol,
                    name=str(wrapped.get("name") or row.get("name") or symbol),
                    address=address,
                    decimals=decimals,
                    tags=tags,
                    source_file=source_file,
                    origin_symbol=str(row.get("symbol") or symbol),
                )

    ordered = sorted(all_candidates.values(), key=_candidate_priority)
    selected = ordered if unbounded else ordered[:max_candidates]
    stats = {
        "enabled": True,
        "source": "0xPolygon/polygon-token-list",
        "branch": TOKEN_LIST_BRANCH,
        "wrapped_pos_seen": seen_rows,
        "unique_candidates": len(all_candidates),
        "returned": len(selected),
        "max_candidates": max_candidates,
        "unbounded": unbounded,
        "skipped": skipped,
        "cache": "refresh",
    }
    _cache_payload(ordered, stats)
    return selected, stats
