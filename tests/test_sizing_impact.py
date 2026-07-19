from decimal import Decimal

import pytest

from omega_v5.sizing import dynamic_optimizer as target_module
from omega_v5.flash_loan import calculate_route_economics


def test_zero_tvl_penalizes_full_gross(monkeypatch) -> None:
    monkeypatch.setattr(
        target_module,
        "DYNAMIC_SIZE_IMPACT_PENALTY_BPS",
        Decimal("100"),
    )

    assert target_module._apply_impact_penalty(
        principal=Decimal("1000"),
        min_tvl=Decimal("0"),
        gross=Decimal("100"),
    ) == Decimal("100")


def test_negative_tvl_penalizes_full_gross(monkeypatch) -> None:
    monkeypatch.setattr(
        target_module,
        "DYNAMIC_SIZE_IMPACT_PENALTY_BPS",
        Decimal("100"),
    )

    assert target_module._apply_impact_penalty(
        principal=Decimal("1000"),
        min_tvl=Decimal("-1"),
        gross=Decimal("100"),
    ) == Decimal("100")


def test_zero_principal_has_zero_penalty(monkeypatch) -> None:
    monkeypatch.setattr(
        target_module,
        "DYNAMIC_SIZE_IMPACT_PENALTY_BPS",
        Decimal("100"),
    )

    assert target_module._apply_impact_penalty(
        principal=Decimal("0"),
        min_tvl=Decimal("100000"),
        gross=Decimal("100"),
    ) == Decimal("0")


def test_negative_gross_has_zero_penalty(monkeypatch) -> None:
    monkeypatch.setattr(
        target_module,
        "DYNAMIC_SIZE_IMPACT_PENALTY_BPS",
        Decimal("100"),
    )

    assert target_module._apply_impact_penalty(
        principal=Decimal("1000"),
        min_tvl=Decimal("100000"),
        gross=Decimal("-100"),
    ) == Decimal("0")


def test_linear_impact_penalty(monkeypatch) -> None:
    monkeypatch.setattr(
        target_module,
        "DYNAMIC_SIZE_IMPACT_PENALTY_BPS",
        Decimal("100"),
    )

    # impact ratio = 10,000 / 100,000 = 0.10
    # BPS factor = 100 / 10,000 = 0.01
    # penalty = 100 × 0.10 × 0.01 = 0.10
    result = target_module._apply_impact_penalty(
        principal=Decimal("10000"),
        min_tvl=Decimal("100000"),
        gross=Decimal("100"),
    )

    assert result == Decimal("0.10")


def test_penalty_cannot_exceed_gross(monkeypatch) -> None:
    monkeypatch.setattr(
        target_module,
        "DYNAMIC_SIZE_IMPACT_PENALTY_BPS",
        Decimal("50000"),
    )

    result = target_module._apply_impact_penalty(
        principal=Decimal("1000000"),
        min_tvl=Decimal("100"),
        gross=Decimal("100"),
    )

    assert result == Decimal("100")


def test_negative_penalty_configuration_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        target_module,
        "DYNAMIC_SIZE_IMPACT_PENALTY_BPS",
        Decimal("-1"),
    )

    with pytest.raises(ValueError):
        target_module._apply_impact_penalty(
            principal=Decimal("1000"),
            min_tvl=Decimal("100000"),
            gross=Decimal("100"),
        )


def test_minimum_profit_is_not_an_expense(monkeypatch) -> None:
    monkeypatch.setattr(target_module, "DYNAMIC_SIZE_IMPACT_PENALTY_BPS", Decimal("0"))

    result = calculate_route_economics(
        flash_principal_usd=Decimal("48655"),
        gross_sell_out_usd=Decimal("48934.229"),
        min_tvl_usd=Decimal("1000000"),
        flash_fee_usd=Decimal("24.3275"),
        gas_cost_usd=Decimal("1.75"),
        relay_tip_usd=Decimal("1"),
        builder_fee_usd=Decimal("0"),
        risk_buffer_usd=Decimal("5"),
        minimum_profit_usd=Decimal("1"),
    )

    assert result.gross_surplus_usd == Decimal("279.229")
    assert result.economic_net_profit_usd == Decimal("247.1515")
    assert result.headroom_usd == Decimal("246.1515")
    assert result.passes_gate is True