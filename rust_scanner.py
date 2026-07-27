#!/usr/bin/env python3
# ==============================================================================
# rust_scanner.py — Python wrapper for Apex-Omega Rust scanner core (PyO3)
# ==============================================================================
"""
Canonical Python interface to the locked Rust scanner.

Matches the locked canon:
- PRICE = ranking authority (executable price only)
- DNA = proof, validation, audit, downstream context (metadata preserved)
- Strict gates enforced in Rust
- Separate V3 / Algebra paths
- No asset blacklist, no protocol priority

Usage (after `maturin develop` or cargo build --release):
    from rust_scanner import RustScanner, Candidate
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import List, Optional, Tuple, Dict, Any

try:
    from scanner_core import GateConfig, scan_opportunities as rust_scan, Candidate as RustCandidate
    RUST_SCANNER_AVAILABLE = True
except ImportError:
    RUST_SCANNER_AVAILABLE = False
    RustCandidate = None
    rust_scan = None

from omega_v5.config import MIN_TVL_USD


@dataclass
class ScannedLeg:
    """Python representation of a price-chosen leg."""
    pool_address: str
    protocol: str
    executable_price: Decimal
    tvl_usd: Decimal


@dataclass
class RustScanResult:
    """Result from the Rust scanner."""
    token_in: str
    token_mid: str
    buy_leg: ScannedLeg
    sell_leg: ScannedLeg
    net_spread: Decimal


class RustScanner:
    """
    High-performance price-driven scanner backed by Rust (when available).
    Falls back to pure Python if the extension is not built.
    """

    def __init__(self, min_tvl_usd: str = str(MIN_TVL_USD), chain_id: int = 137):
        self.min_tvl_usd = min_tvl_usd
        self.chain_id = chain_id
        self.gate_config = None
        if RUST_SCANNER_AVAILABLE:
            self.gate_config = GateConfig(min_tvl_usd=min_tvl_usd, chain_id=chain_id)

    def is_available(self) -> bool:
        return RUST_SCANNER_AVAILABLE

    def scan(self, pools: Dict[str, Dict[str, Any]]) -> List[RustScanResult]:
        """
        Run the price-driven scan.
        pools: dict of pool_id -> pool dict with 'protocol', 'address', 'tokens', 'total_executable_liquidity_usd', 'executable_price'
        """
        if not RUST_SCANNER_AVAILABLE or self.gate_config is None:
            return self._python_fallback_scan(pools)

        # Convert to the format expected by Rust
        pools_for_rust = {}
        for pid, p in pools.items():
            if len(p.get("tokens", [])) != 2:
                continue
            pools_for_rust[pid] = {
                "protocol": p.get("protocol", "Unknown"),
                "address": p.get("address", ""),
                "tokens": p["tokens"],
                "total_executable_liquidity_usd": str(p.get("total_executable_liquidity_usd", "0")),
                "executable_price": str(p.get("executable_price", "0")),
            }

        pools_json = json.dumps(pools_for_rust)
        try:
            raw_candidates = rust_scan(pools_json, self.gate_config)
        except Exception as e:
            # Fall back on error
            return self._python_fallback_scan(pools)

        results = []
        for cand in raw_candidates:
            try:
                buy_leg = ScannedLeg(
                    pool_address=cand.buy_pool_address,
                    protocol=cand.buy_pool_protocol,
                    executable_price=Decimal(cand.executable_buy_price),
                    tvl_usd=Decimal(cand.buy_pool_tvl_usd),
                )
                sell_leg = ScannedLeg(
                    pool_address=cand.sell_pool_address,
                    protocol=cand.sell_pool_protocol,
                    executable_price=Decimal(cand.executable_sell_price),
                    tvl_usd=Decimal("0"),
                )
                spread = Decimal(cand.executable_sell_price) - Decimal(cand.executable_buy_price)
                results.append(RustScanResult(
                    token_in=cand.token_in,
                    token_mid=cand.token_mid,
                    buy_leg=buy_leg,
                    sell_leg=sell_leg,
                    net_spread=spread,
                ))
            except Exception:
                continue

        return results

    def _python_fallback_scan(self, pools: Dict[str, Dict[str, Any]]) -> List[RustScanResult]:
        """Pure Python fallback that follows the exact same price-driven rules."""
        from collections import defaultdict
        pair_pools = defaultdict(list)
        for pid, p in pools.items():
            if len(p.get("tokens", [])) != 2:
                continue
            t0, t1 = p["tokens"]
            pair_pools[(t0, t1)].append(p)

        results = []
        tokens = set()
        for p in pools.values():
            for t in p.get("tokens", []):
                tokens.add(t)
        tokens = list(tokens)

        for ta in tokens:
            for tb in tokens:
                if ta == tb:
                    continue
                ab_pools = pair_pools.get((ta, tb), [])
                ba_pools = pair_pools.get((tb, ta), [])

                if not ab_pools or not ba_pools:
                    continue

                best_buy = min(ab_pools, key=lambda p: Decimal(str(p.get("executable_price", "0"))))
                best_sell = max(ba_pools, key=lambda p: Decimal(str(p.get("executable_price", "0"))))

                buy_price = Decimal(str(best_buy.get("executable_price", "0")))
                sell_price = Decimal(str(best_sell.get("executable_price", "0")))

                if buy_price >= sell_price:
                    continue

                buy_tvl = Decimal(str(best_buy.get("total_executable_liquidity_usd", "0")))
                if buy_tvl < Decimal(self.min_tvl_usd):
                    continue

                if best_buy.get("address") == best_sell.get("address"):
                    continue

                buy_leg = ScannedLeg(
                    pool_address=best_buy.get("address", ""),
                    protocol=best_buy.get("protocol", ""),
                    executable_price=buy_price,
                    tvl_usd=buy_tvl,
                )
                sell_leg = ScannedLeg(
                    pool_address=best_sell.get("address", ""),
                    protocol=best_sell.get("protocol", ""),
                    executable_price=sell_price,
                    tvl_usd=Decimal(str(best_sell.get("total_executable_liquidity_usd", "0"))),
                )

                results.append(RustScanResult(
                    token_in=ta,
                    token_mid=tb,
                    buy_leg=buy_leg,
                    sell_leg=sell_leg,
                    net_spread=sell_price - buy_price,
                ))

        return results


# Convenience function
def find_best_legs_with_rust(pools: Dict[str, Dict[str, Any]], min_tvl: str = str(MIN_TVL_USD)) -> List[RustScanResult]:
    scanner = RustScanner(min_tvl_usd=min_tvl)
    return scanner.scan(pools)
