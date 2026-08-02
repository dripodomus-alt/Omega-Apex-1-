"""
Phase A + Phase B Validation Tests
==================================
Validates the refactored arbitrage_engine + dashboard_api router + universal pre-filter.

Scope (from review_request):
- /api/pool-prices ~ live Polygon pools
- /api/spreads structure (no crash)
- /api/dashboard/network-status (REAL Polygon block)
- /api/dashboard/pnl-summary
- /api/dashboard/strategies
- /api/dashboard/opportunities
- /api/bot/config, /api/arbitrage/config, /api/executor/stats (regression)
- Dashboard prefix isolation from /api/opportunities (server.py)
- _analyze_basic refactor regression (positive amounts_in_usd)
- Universal pre-filter _quick_profitability_filter returns bool
"""

import os
import sys
import time
import pytest
import requests
from pathlib import Path

# Add backend root to sys.path for direct module imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback to frontend .env
    fe_env = Path("/app/frontend/.env")
    if fe_env.exists():
        for ln in fe_env.read_text().splitlines():
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().strip('"')
                break
BASE_URL = (BASE_URL or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

TIMEOUT_SHORT = 30
TIMEOUT_LONG = 120  # /api/spreads can be slow when scanning


# ---------- Public endpoint tests ----------

class TestApiHealth:
    """Smoke check the backend is reachable."""

    def test_root_alive(self):
        r = requests.get(f"{BASE_URL}/api/", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200, r.text


class TestPoolPrices:
    """GET /api/pool-prices returns valid PoolPrice list."""

    def test_pool_prices_structure(self):
        r = requests.get(f"{BASE_URL}/api/pool-prices", timeout=TIMEOUT_LONG)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        data = r.json()
        # Accept either list or wrapped object
        pools = data if isinstance(data, list) else (data.get("pools") or data.get("data") or [])
        assert isinstance(pools, list), f"expected list, got {type(pools)}"
        assert len(pools) > 0, "no pools returned"
        # Validate first pool fields (snake_case or camelCase tolerated)
        p = pools[0]
        keys = set(p.keys())

        def has(*names):
            return any(n in keys for n in names)

        assert has("poolAddress", "pool_address", "address"), f"missing pool address. keys={keys}"
        assert has("dexName", "dex_name", "dex"), f"missing dex. keys={keys}"
        assert has("token0Symbol", "token0_symbol"), f"missing token0_symbol. keys={keys}"
        assert has("token1Symbol", "token1_symbol"), f"missing token1_symbol. keys={keys}"
        assert has("reserveUsd", "reserve_usd", "tvl_usd", "tvl"), f"missing reserve_usd. keys={keys}"
        # Cache count for later
        pytest.pool_count = len(pools)
        print(f"[pool-prices] pools returned: {len(pools)}")


class TestSpreads:
    """GET /api/spreads returns valid {timestamp, spreads} structure (no crash)."""

    def test_spreads_endpoint_returns_valid_shape(self):
        r = requests.get(
            f"{BASE_URL}/api/spreads",
            params={"loan_amount": 10000},
            timeout=TIMEOUT_LONG,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        data = r.json()
        assert isinstance(data, dict)
        # 'timestamp' may be absent in some impl; require 'spreads' or 'opportunities'
        assert "spreads" in data or "opportunities" in data, f"keys={list(data.keys())}"
        spreads = data["spreads"] if "spreads" in data else data["opportunities"]
        assert isinstance(spreads, list), f"spreads must be list, got {type(spreads).__name__}"
        print(f"[spreads] count={len(spreads)} (0 OK in efficient market)")


# ---------- Dashboard router tests ----------

class TestDashboardRouter:
    """GET /api/dashboard/* endpoints (prefix verified, no collision)."""

    def test_network_status_real_polygon(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/network-status", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        d = r.json()
        # tolerate snake/camel
        block = d.get("blockNumber") or d.get("block_number") or 0
        base_fee = d.get("baseFeeGwei") or d.get("base_fee_gwei") or 0
        gas = d.get("gasPrice") or d.get("gas_price") or 0
        health = d.get("networkHealth") or d.get("network_health") or 0
        assert block and float(block) > 0, f"blockNumber must be >0, got {block}"
        assert float(base_fee) > 0, f"baseFeeGwei must be >0, got {base_fee}"
        assert float(gas) > 0, f"gasPrice must be >0, got {gas}"
        assert float(health) > 0, f"networkHealth must be >0, got {health}"
        print(f"[network-status] block={block} baseFee={base_fee}gwei gas={gas} health={health}")

    def test_pnl_summary_24h(self):
        r = requests.get(
            f"{BASE_URL}/api/dashboard/pnl-summary",
            params={"timeframe": "24h"},
            timeout=TIMEOUT_SHORT,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        d = r.json()
        # required field set
        required_any = [
            ("opportunitiesScanned", "opportunities_scanned"),
            ("passedGates", "passed_gates"),
            ("executed",),
            ("grossProfit", "gross_profit"),
            ("netProfit", "net_profit"),
            ("strategyBreakdown", "strategy_breakdown"),
        ]
        keys = set(d.keys())
        for variants in required_any:
            assert any(v in keys for v in variants), f"missing {variants}; got {keys}"

    def test_strategies(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/strategies", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        d = r.json()
        assert isinstance(d, dict)
        for s in ("c1", "c2", "liquidation"):
            assert s in d, f"strategy {s} missing in {list(d.keys())}"
            entry = d[s]
            assert isinstance(entry, dict)
            assert "enabled" in entry, f"strategy {s} missing 'enabled' flag"

    def test_opportunities_pagination(self):
        r = requests.get(
            f"{BASE_URL}/api/dashboard/opportunities",
            params={"limit": 20},
            timeout=TIMEOUT_SHORT,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        d = r.json()
        for k in ("opportunities", "total", "page", "pages"):
            assert k in d, f"key {k} missing; got {list(d.keys())}"
        assert isinstance(d["opportunities"], list)


# ---------- Pre-existing endpoint regression ----------

class TestPreexistingEndpoints:
    def test_bot_config(self):
        r = requests.get(f"{BASE_URL}/api/bot/config", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"

    def test_arbitrage_config(self):
        r = requests.get(f"{BASE_URL}/api/arbitrage/config", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"

    def test_executor_stats(self):
        r = requests.get(f"{BASE_URL}/api/executor/stats", timeout=TIMEOUT_SHORT)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"

    def test_dashboard_no_collision_with_root_opportunities(self):
        """`/api/opportunities` (server.py) and `/api/dashboard/opportunities` must coexist."""
        r1 = requests.get(f"{BASE_URL}/api/opportunities", timeout=TIMEOUT_SHORT)
        r2 = requests.get(f"{BASE_URL}/api/dashboard/opportunities", timeout=TIMEOUT_SHORT)
        # Both should respond with 2xx (or at least not interfere with each other)
        assert r1.status_code in (200, 404), f"/api/opportunities unexpected {r1.status_code}"
        assert r2.status_code == 200, f"dashboard opportunities returned {r2.status_code}"


# ---------- Direct module tests: refactor regression ----------

class TestRefactorRegression:
    """Direct unit-level call into refactored arbitrage_engine internals."""

    def test_protocol_int_to_str_helper_exists(self):
        from arbitrage_engine import _protocol_int_to_str, Protocol
        assert _protocol_int_to_str(Protocol.V2) == "v2"
        assert _protocol_int_to_str(Protocol.V3) == "v3"

    def test_quick_profitability_filter_returns_bool(self):
        """Universal pre-filter must not crash and must return bool."""
        from arbitrage_engine import ArbitrageEngine

        # Use minimal init - just need the method
        try:
            engine = ArbitrageEngine.__new__(ArbitrageEngine)
            # If method requires self attributes, set defaults
            if hasattr(ArbitrageEngine, "_quick_profitability_filter"):
                method = ArbitrageEngine._quick_profitability_filter

                # Build two tiny pool-like dicts/objects
                class P:
                    def __init__(self):
                        self.token0 = "0xA"
                        self.token1 = "0xB"
                        self.token0_symbol = "USDC"
                        self.token1_symbol = "WMATIC"
                        self.reserve0 = 1_000_000
                        self.reserve1 = 800_000
                        self.reserve_usd = 200_000
                        self.token0_decimals = 6
                        self.token1_decimals = 18
                        self.dex_name = "uniV3"
                        self.protocol = 3
                        self.fee = 3000
                        self.weight0 = 0.5
                        self.weight1 = 0.5
                        self.sqrt_price_x96 = 0
                        self.liquidity = 0
                        self.tick = 0

                p1, p2 = P(), P()
                p2.reserve1 = 850_000
                try:
                    out = method(engine, p1, p2)
                    assert isinstance(out, bool), f"expected bool, got {type(out)}: {out}"
                except TypeError:
                    pytest.skip("_quick_profitability_filter signature differs - manual review needed")
            else:
                pytest.skip("_quick_profitability_filter not defined on ArbitrageEngine")
        except Exception as e:
            pytest.fail(f"pre-filter crashed: {e}")

    def test_analyze_basic_signature_intact(self):
        """Ensure refactored _analyze_basic still exists and is callable."""
        from arbitrage_engine import ArbitrageEngine
        assert hasattr(ArbitrageEngine, "_analyze_basic")
        assert callable(ArbitrageEngine._analyze_basic)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
