"""Polygon micro-gas expense stack: deduct all costs from raw delta."""

import pytest
from decimal import Decimal

from omega_v5.flash_loan import (
    GAS_PRICE_GWEI,
    POL_USD_PRICE,
    deduct_expenses_from_raw_delta,
    estimate_static_gas_usd,
    evaluate_profitability,
)


def test_static_two_hop_gas_is_about_one_tenth_cent():
    gas = estimate_static_gas_usd(hops=2)
    # 350k * 10 gwei * 1e-9 * 0.30 ≈ 0.00105
    expected_gas = Decimal("350000") * GAS_PRICE_GWEI / Decimal("1000000000") * POL_USD_PRICE
    assert gas == pytest.approx(expected_gas)
    assert gas == pytest.approx(Decimal("0.00105"), abs=Decimal("0.001"))


def test_deduct_expenses_from_raw_delta_stack():
    principal = Decimal("1000")
    gross = Decimal("1000.05")  # $0.05 raw delta
    breakdown = deduct_expenses_from_raw_delta(
        gross_amount_out_usd=gross,
        principal_usd=principal,
        flash_fee_usd=Decimal("0"),
        gas_cost_usd=Decimal("0.001"),
        relay_tip_usd=Decimal("0.001"),
        risk_buffer_usd=Decimal("0.005"),
        min_net_profit_usd=Decimal("0.001"),
    )
    assert breakdown.raw_delta_usd == Decimal("0.05")
    assert breakdown.total_expenses_usd == Decimal("0.007")
    assert breakdown.net_after_expenses_usd == Decimal("0.043")
    assert breakdown.passes_min_net is True


def test_evaluate_profitability_exposes_expense_breakdown(monkeypatch):
    monkeypatch.setattr(
        "omega_v5.flash_loan.current_gas_price_gwei",
        lambda: (Decimal("10"), "test_static"),
    )
    monkeypatch.setattr(
        "omega_v5.flash_loan.current_pol_price_usd",
        lambda: (Decimal("0.30"), "test_pol"),
    )
    monkeypatch.setattr(
        "omega_v5.flash_loan._read_live_flash_fee_bps",
        lambda source: (Decimal("0"), "test_fee", 0, True),
    )
    monkeypatch.setenv("RELAY_TIP_USD", "0.001")
    monkeypatch.setenv("RISK_BUFFER_USD", "0.005")
    monkeypatch.setenv("MIN_NET_PROFIT_USD", "0.001")
    monkeypatch.setenv("MIN_PROFIT_TO_GAS_RATIO", "0")

    principal = Decimal("5000")
    gross = principal + Decimal("1.00")
    prof = evaluate_profitability(gross, principal, hops=2)

    assert prof.raw_delta_usd == Decimal("1.00")
    assert prof.expense_breakdown is not None
    assert Decimal(prof.expense_breakdown["gas_cost_usd"]) > 0
    assert prof.net_profit_usd == (
        prof.raw_delta_usd - Decimal(prof.expense_breakdown["total_expenses_usd"])
    )
    assert prof.passes_gate is True
