from decimal import Decimal

from omega_v5.math_engine import DeFiEngineMath
from tests.helpers import assert_close


def test_balancer_weighted_80_20_spot_and_slippage() -> None:
    reserves = [Decimal("1000"), Decimal("1000")]
    weights = [Decimal("0.8"), Decimal("0.2")]

    spot = DeFiEngineMath.balancer_weighted_spot_price(reserves, weights, 0, 1)
    amount_out = DeFiEngineMath.query_balancer_weighted(
        reserves,
        weights,
        Decimal("100"),
        0,
        1,
        Decimal("0"),
    )

    assert_close(spot, Decimal("0.25"))
    assert_close(amount_out, Decimal("316.98654463492930810736971518338911276552148077317"))


def test_balancer_weighted_60_40_spot_and_slippage() -> None:
    reserves = [Decimal("1000"), Decimal("1000")]
    weights = [Decimal("0.6"), Decimal("0.4")]

    spot = DeFiEngineMath.balancer_weighted_spot_price(reserves, weights, 0, 1)
    amount_out = DeFiEngineMath.query_balancer_weighted(
        reserves,
        weights,
        Decimal("100"),
        0,
        1,
        Decimal("0"),
    )

    assert_close(spot, Decimal("0.6666666666666666666666666667"))
    assert_close(amount_out, Decimal("133.21582795855244050293098042980363762374226637892"))


def test_balancer_weight_inputs_can_be_percent_values() -> None:
    reserves = [Decimal("1000"), Decimal("1000")]
    fractional = DeFiEngineMath.query_balancer_weighted(
        reserves, [Decimal("0.8"), Decimal("0.2")], Decimal("100"), 0, 1, Decimal("0")
    )
    percent = DeFiEngineMath.query_balancer_weighted(
        reserves, [Decimal("80"), Decimal("20")], Decimal("100"), 0, 1, Decimal("0")
    )

    assert_close(percent, fractional)
