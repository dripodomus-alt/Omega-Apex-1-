from decimal import Decimal

from omega_v5.flash_loan import calculate_route_economics


def test_canonical_arb_equation_min_profit_is_threshold_not_expense():
    result = calculate_route_economics(
        flash_principal_usd=Decimal("10000"),
        gross_sell_out_usd=Decimal("10066.666667"),
        min_tvl_usd=Decimal("10000000"),
        flash_fee_usd=Decimal("0"),
        gas_cost_usd=Decimal("1.25"),
        relay_tip_usd=Decimal("0.50"),
        builder_fee_usd=Decimal("0.25"),
        risk_buffer_usd=Decimal("2.00"),
        minimum_profit_usd=Decimal("1.00"),
    )

    assert result.gross_surplus_usd == Decimal("66.666667")
    assert result.economic_net_profit_usd < result.gross_surplus_usd
    assert result.headroom_usd == result.economic_net_profit_usd - Decimal("1.00")
    assert result.economic_net_profit_usd == (
        result.gross_surplus_usd
        - result.flash_fee_usd
        - result.gas_cost_usd
        - result.relay_tip_usd
        - result.builder_fee_usd
        - result.risk_buffer_usd
        - result.impact_penalty_usd
    )
    assert result.passes_gate is True
