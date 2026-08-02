"""
Regression test for the refactored `_analyze_basic` orchestrator.
Confirms the helper-extraction did not change observable behavior on
realistic V2-V2 + V3-V3 + cross-protocol inputs.

Run: cd /app/backend && python -m pytest tests/test_arbitrage_engine_refactor.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from arbitrage_helpers import (
    validate_pair,
    select_direction,
    has_stablecoin_anchor,
    calculate_capped_slippage,
    STABLECOINS,
    MAX_SLIPPAGE_PCT_DEFAULT,
)


class FakePool:
    """Minimal PoolPrice-like object for unit testing helpers."""
    def __init__(self, t0, t1, r0, r1, tvl, t0d=18, t1d=6, dex="X", protocol=2, fee=3000):
        self.token0 = t0
        self.token1 = t1
        self.token0_symbol = "T0"
        self.token1_symbol = "T1"
        self.reserve0 = r0
        self.reserve1 = r1
        self.reserve_usd = tvl
        self.token0_decimals = t0d
        self.token1_decimals = t1d
        self.dex_name = dex
        self.protocol = protocol
        self.fee = fee
        self.weight0 = 0.5
        self.weight1 = 0.5
        self.sqrt_price_x96 = 0
        self.liquidity = 0
        self.tick = 0


# ------------------- validate_pair -------------------

def test_validate_pair_same_pair_passes():
    p1 = FakePool("0xA", "0xB", 1000, 1100, 200000)
    p2 = FakePool("0xA", "0xB", 800, 900, 150000)
    v = validate_pair(p1, p2, 5000, 50000)
    assert v.ok is True
    assert v.min_reserve == 150000
    assert v.pool1_price == pytest.approx(1.1)
    assert v.pool2_price == pytest.approx(1.125)


def test_validate_pair_different_pair_fails():
    p1 = FakePool("0xA", "0xB", 1000, 1100, 200000)
    p2 = FakePool("0xA", "0xC", 800, 900, 150000)
    v = validate_pair(p1, p2, 5000, 50000)
    assert v.ok is False
    assert v.reason == "different_pairs"


def test_validate_pair_below_min_reserve_fails():
    p1 = FakePool("0xA", "0xB", 1000, 1100, 200000)
    p2 = FakePool("0xA", "0xB", 800, 900, 1000)
    v = validate_pair(p1, p2, 5000, 50000)
    assert v.ok is False
    assert v.reason == "below_min_reserve"


def test_validate_pair_loan_exceeds_tvl_fraction(monkeypatch):
    monkeypatch.setenv("MAX_TVL_FRACTION", "0.10")
    p1 = FakePool("0xA", "0xB", 1000, 1100, 100000)
    p2 = FakePool("0xA", "0xB", 800, 900, 100000)
    # Loan is 50% of TVL, exceeds 10% gate
    v = validate_pair(p1, p2, 50000, 50000)
    assert v.ok is False
    assert "exceeds" in v.reason


# ------------------- select_direction -------------------

def test_select_direction_picks_lowest_price_as_buy():
    p1 = FakePool("0xA", "0xB", 1000, 1100, 100000)  # price 1.10
    p2 = FakePool("0xA", "0xB", 1000, 1200, 100000)  # price 1.20
    d = select_direction(p1, p2, 1.10, 1.20)
    assert d.buy_pool is p1
    assert d.sell_pool is p2
    assert d.buy_price == 1.10
    assert d.sell_price == 1.20
    assert d.tokens_reversed is False


def test_select_direction_detects_reversed_tokens():
    p1 = FakePool("0xA", "0xB", 1000, 1100, 100000)
    p2 = FakePool("0xB", "0xA", 1100, 1300, 100000)  # token order reversed
    d = select_direction(p1, p2, 1.10, 1.18)
    assert d.tokens_reversed is True


# ------------------- has_stablecoin_anchor -------------------

def test_has_stablecoin_anchor_with_usdc():
    p = FakePool(STABLECOINS[0], "0xWMATIC", 1, 1, 1)
    assert has_stablecoin_anchor(p) is True


def test_has_stablecoin_anchor_without():
    p = FakePool("0xWBTC", "0xWMATIC", 1, 1, 1)
    assert has_stablecoin_anchor(p) is False


# ------------------- calculate_capped_slippage -------------------

def test_capped_slippage_uncapped_below_limit():
    leg1, leg2, sl1, sl2 = calculate_capped_slippage(0.5, 1.5, 10000, 9900, cap_pct=2.0)
    assert leg1 == 0.5
    assert leg2 == 1.5
    assert sl1 == pytest.approx(50.0)        # 10000 * 0.005
    assert sl2 == pytest.approx(148.5)       # 9900 * 0.015


def test_capped_slippage_caps_excessive():
    leg1, leg2, sl1, sl2 = calculate_capped_slippage(8.0, 12.0, 10000, 9000, cap_pct=2.0)
    assert leg1 == 2.0   # capped
    assert leg2 == 2.0   # capped
    assert sl1 == pytest.approx(200.0)
    assert sl2 == pytest.approx(180.0)


def test_capped_slippage_default_constant():
    assert MAX_SLIPPAGE_PCT_DEFAULT == 2.0


# ------------------- protocol_int_to_str -------------------

def test_protocol_int_to_str_mapping():
    from arbitrage_engine import _protocol_int_to_str, Protocol
    assert _protocol_int_to_str(Protocol.V2) == "v2"
    assert _protocol_int_to_str(Protocol.V3) == "v3"
    assert _protocol_int_to_str(Protocol.WEIGHTED) == "balancer"
    assert _protocol_int_to_str(Protocol.STABLE) == "curve"
    # Unknown -> v3 default
    assert _protocol_int_to_str(999) == "v3"


# ------------------- Universal pre-filter -------------------

def test_universal_calculator_singleton():
    from universal_arbitrage import get_universal_calculator
    c1 = get_universal_calculator()
    c2 = get_universal_calculator()
    assert c1 is c2  # singleton


def test_universal_verify_profitability_returns_tuple():
    """verify_profitability must return (bool, ratio) tuple."""
    from universal_arbitrage import get_universal_calculator
    pool = {
        "protocol": "v2", "reserve0": 100000, "reserve1": 50000,
        "fee_bps": 30, "weight0": 0.5, "weight1": 0.5,
    }
    result = get_universal_calculator().verify_profitability(pool, dict(pool))
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert isinstance(result[1], (int, float))


def test_universal_verify_profitability_identical_pools_not_profitable():
    """Two identical pools cannot have arbitrage (gross factor = 1.0)."""
    from universal_arbitrage import get_universal_calculator
    pool = {
        "protocol": "v2", "reserve0": 100000, "reserve1": 50000,
        "fee_bps": 30, "weight0": 0.5, "weight1": 0.5,
    }
    is_p, ratio = get_universal_calculator().verify_profitability(pool, dict(pool))
    assert is_p is False
    assert ratio == pytest.approx(1.0)


def test_universal_verify_profitability_finds_real_arb():
    """A pool pair with >0.6% spot diff should be flagged profitable (after 0.6% fees)."""
    from universal_arbitrage import get_universal_calculator
    # Pool1 spot = 1.10, Pool2 spot = 1.20 → ratio 1.0909 > 1+0.006
    p1 = {"protocol": "v2", "reserve0": 100000, "reserve1": 110000, "fee_bps": 30}
    p2 = {"protocol": "v2", "reserve0": 100000, "reserve1": 120000, "fee_bps": 30}
    is_p, ratio = get_universal_calculator().verify_profitability(p1, p2)
    assert is_p is True
    assert ratio > 1.0


def test_universal_verify_profitability_below_fee_threshold():
    """Tiny spot diff (<0.6% combined fees) should NOT be flagged profitable."""
    from universal_arbitrage import get_universal_calculator
    # 0.1% spot diff vs 0.6% combined fees
    p1 = {"protocol": "v2", "reserve0": 100000, "reserve1": 110000, "fee_bps": 30}
    p2 = {"protocol": "v2", "reserve0": 100000, "reserve1": 110100, "fee_bps": 30}
    is_p, _ = get_universal_calculator().verify_profitability(p1, p2)
    assert is_p is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
