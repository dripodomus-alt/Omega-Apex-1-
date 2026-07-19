"""Unit tests for hop fee normalization used by route_execution_stager."""

from decimal import Decimal

from omega_v5.route_execution_stager import _estimate_hop_fees_usd, _hop_fee_fraction


def test_hop_fee_fraction_v3_tier_units():
    # Uniswap V3 fee tiers are hundredths of a bip.
    assert _hop_fee_fraction({"fee": 3000}) == Decimal("0.003")
    assert _hop_fee_fraction({"fee_tier": 500}) == Decimal("0.0005")
    assert _hop_fee_fraction({"fee": 10000}) == Decimal("0.01")


def test_hop_fee_fraction_already_fraction():
    assert _hop_fee_fraction({"fee": Decimal("0.003")}) == Decimal("0.003")
    assert _hop_fee_fraction({"fee": "0.0004"}) == Decimal("0.0004")


def test_hop_fee_fraction_compact_bps():
    assert _hop_fee_fraction({"fee_bps": 30}) == Decimal("0.003")
    assert _hop_fee_fraction({"fee": 5}) == Decimal("0.0005")


def test_hop_fee_fraction_defaults_and_pool_fallback():
    # Missing hop fee -> default Uniswap mid tier 3000 = 0.3%
    assert _hop_fee_fraction({}) == Decimal("0.003")
    # Pool metadata fills gaps
    assert _hop_fee_fraction({}, {"fee_tier": 500}) == Decimal("0.0005")
    assert _hop_fee_fraction({}, {"fee": Decimal("0.0025")}) == Decimal("0.0025")


def test_hop_fee_fraction_never_divides_by_zero():
    # Historical bug was Decimal(fee) / Decimal("0.0")
    frac = _hop_fee_fraction({"fee": 3000})
    assert frac > 0
    assert frac == Decimal(str(3000)) / Decimal("1000000")


def test_estimate_hop_fees_usd_uses_safe_fraction(monkeypatch):
    monkeypatch.setattr(
        "omega_v5.route_execution_stager.token_price_usd",
        lambda symbol: Decimal("1"),
    )
    edges = (
        {"pool_id": "P1", "fee": 3000},
        {"pool_id": "P2", "fee_tier": 500},
    )
    breakdown, total = _estimate_hop_fees_usd(
        edges,
        base_amount_in=Decimal("1000"),
        base_token="USDC",
        pools={
            "P1": {"fee_tier": 3000},
            "P2": {"fee_tier": 500},
        },
    )
    # 1000 * 0.003 + 1000 * 0.0005 = 3.5
    assert breakdown == [Decimal("3.0"), Decimal("0.5")]
    assert total == Decimal("3.5")
