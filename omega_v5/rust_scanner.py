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
    from omega_v5.rust_scanner import RustScanner, Candidate
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import List, Optional, Tuple, Dict, Any

try:
    import omega_scanner  # The compiled PyO3 module
except ImportError:
    omega_scanner = None
    print("WARNING: omega_scanner Rust extension not found. Falling back to pure Python stub.")

CHAIN_ID = 137
MIN_POOL_TVL_USD = Decimal("50000")


@dataclass
class Candidate:
    """Python mirror of Rust Candidate. DNA/metadata preserved but never selects legs."""
    chain_id: int
    pool_id: str
    protocol: str
    buy_price_executable_usd_per_base: Decimal
    sell_price_executable_usd_per_base: Decimal
    pool_tvl_usd: Decimal
    has_live_quote: bool
    destination: str
    pool_address: str
    metadata: Dict[str, Any] = None  # DNA

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @classmethod
    def from_dict(cls, d: dict) -> "Candidate":
        return cls(
            chain_id=d.get("chain_id", CHAIN_ID),
            pool_id=d["pool_id"],
            protocol=d["protocol"],
            buy_price_executable_usd_per_base=Decimal(str(d["buy_price_executable_usd_per_base"])),
            sell_price_executable_usd_per_base=Decimal(str(d["sell_price_executable_usd_per_base"])),
            pool_tvl_usd=Decimal(str(d.get("pool_tvl_usd", 0))),
            has_live_quote=bool(d.get("has_live_quote", True)),
            destination=d.get("destination", ""),
            pool_address=d.get("pool_address", ""),
            metadata=d.get("metadata", {}),
        )


class RustScanner:
    """Wrapper around the Rust scanner_core."""

    def __init__(self):
        self._rust = omega_scanner if omega_scanner else None
        self._use_rust = self._rust is not None

    def validate(self, cand: Candidate) -> Tuple[bool, str]:
        if self._use_rust:
            v = self._rust.validate_candidate(
                cand.chain_id,
                cand.pool_id,
                cand.protocol,
                float(cand.buy_price_executable_usd_per_base),
                float(cand.sell_price_executable_usd_per_base),
                float(cand.pool_tvl_usd),
                cand.has_live_quote,
                cand.destination,
                cand.pool_address,
            )
            # Note: in real PyO3 the call would return the ValidatedCandidate object
            return v.passes, v.reason
        # Pure Python fallback (for Colab/dev)
        if cand.chain_id != CHAIN_ID:
            return False, "chain_id_must_be_137"
        if cand.pool_tvl_usd < MIN_POOL_TVL_USD:
            return False, "tvl_below_50000"
        if not cand.has_live_quote:
            return False, "no_live_executable_quote"
        return True, "gate_passed"

    def find_best_legs(self, candidates: List[Candidate]) -> Tuple[Optional[Candidate], Optional[Candidate]]:
        """Final scanner selection law (locked):
        best_buy = min by executable buy price
        best_sell = max by executable sell price
        """
        if self._use_rust:
            # Convert and call Rust
            rust_cands = []
            for c in candidates:
                rust_cands.append((
                    c.chain_id, c.pool_id, c.protocol,
                    float(c.buy_price_executable_usd_per_base),
                    float(c.sell_price_executable_usd_per_base),
                    float(c.pool_tvl_usd),
                    c.has_live_quote, c.destination, c.pool_address
                ))
            buy, sell = self._rust.find_best_legs(rust_cands)
            if buy is None or sell is None:
                return None, None
            return Candidate.from_dict(buy), Candidate.from_dict(sell)

        # Python reference implementation (must match Rust exactly)
        valid = [c for c in candidates if self.validate(c)[0]]
        if len(valid) < 2:
            return None, None

        # Executable price ONLY chooses the leg
        best_buy = min(valid, key=lambda r: r.buy_price_executable_usd_per_base)
        best_sell = max(valid, key=lambda r: r.sell_price_executable_usd_per_base)

        if best_buy.destination == best_sell.destination or best_buy.pool_address == best_sell.pool_address:
            return None, None
        if best_buy.buy_price_executable_usd_per_base >= best_sell.sell_price_executable_usd_per_base:
            return None, None

        return best_buy, best_sell

    def quote_v3(self, pool_data: dict) -> Decimal:
        if self._use_rust:
            return Decimal(str(self._rust.quote_uniswap_v3(pool_data)))
        # stub
        return Decimal(str(pool_data.get("sqrt_price_x96", 1))) / Decimal("1e18")

    def quote_algebra(self, pool_data: dict) -> Decimal:
        if self._use_rust:
            return Decimal(str(self._rust.quote_algebra(pool_data)))
        return Decimal(str(pool_data.get("global_state", 1))) / Decimal("1e18")

    def fixed_point(self, price: float) -> str:
        if self._use_rust:
            return self._rust.fixed_point_price(price)
        return str(Decimal(str(price)))


# Convenience for notebooks / Colab
def build_candidate_from_row(row: dict) -> Candidate:
    return Candidate.from_dict(row)


if __name__ == "__main__":
    # Quick self-test
    scanner = RustScanner()
    c1 = Candidate(137, "POOL1", "UniswapV3", Decimal("1.0"), Decimal("1.05"), Decimal("60000"), True, "USDC", "0xabc")
    c2 = Candidate(137, "POOL2", "Algebra", Decimal("0.99"), Decimal("1.06"), Decimal("70000"), True, "USDT", "0xdef")
    print(scanner.find_best_legs([c1, c2]))
    print("Rust scanner wrapper ready.")
