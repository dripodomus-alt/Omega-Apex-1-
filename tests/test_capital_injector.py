"""Tests for official capital_injector: registries, cannibalization, derivative sizing."""

from __future__ import annotations

from decimal import Decimal

import pytest

from omega_v5.capital_injector import (
    CAPITAL_SOURCE_REGISTRY,
    check_self_cannibalization,
    compute_derivative_optimal_size,
    compute_optimal_injection,
    prepare_sizing_for_rust,
    register_execution_venue,
)
from omega_v5.flash_loan import FlashSource


def test_capital_source_registry_has_funding_silos():
    assert "BALANCER" in CAPITAL_SOURCE_REGISTRY
    assert "AAVE_V3" in CAPITAL_SOURCE_REGISTRY
    assert CAPITAL_SOURCE_REGISTRY["BALANCER"]["type"] == "flash_funding"
    assert CAPITAL_SOURCE_REGISTRY["AAVE_V3"]["fee_bps"] == Decimal("5")


def test_self_cannibalization_detected_on_funding_pool_overlap():
    funding_id = CAPITAL_SOURCE_REGISTRY["BALANCER"]["pool_id"]
    is_c, msg = check_self_cannibalization("BALANCER", [funding_id, "TRADE_POOL"])
    assert is_c is True
    assert "SELF-CANNIBALIZATION DETECTED" in msg


def test_self_cannibalization_clean_route():
    is_c, msg = check_self_cannibalization("BALANCER", ["POOL_A", "POOL_B"])
    assert is_c is False
    assert msg == ""


def test_derivative_formula_friction_returns_zero():
    # Equal reserves with fees: no positive optimal
    size = compute_derivative_optimal_size(
        Decimal("100000"),
        Decimal("100000"),
        Decimal("0.003"),
        Decimal("0.0005"),
    )
    assert size == Decimal("0")


def test_derivative_formula_positive_on_spread():
    size = compute_derivative_optimal_size(
        Decimal("10000"),
        Decimal("15000"),
        Decimal("0.003"),
        Decimal("0"),
    )
    assert size > 0


def test_compute_optimal_injection_blocks_cannibal():
    funding_id = str(CAPITAL_SOURCE_REGISTRY["BALANCER"]["pool_id"])
    pools = {
        funding_id: {"total_executable_liquidity_usd": "800000", "fee_bps": 3000},
        "POOL_X": {"total_executable_liquidity_usd": "600000", "fee_bps": 3000},
    }
    result = compute_optimal_injection(
        pool_sequence=[funding_id, "POOL_X"],
        pools=pools,
        flash_source=FlashSource.BALANCER,
    )
    assert result.cannibalization_detected is True
    assert result.optimal_injection_usd == 0
    assert result.method == "cannibalization_blocked"
    params = result.as_sizing_params()
    assert params.get("cannibalization_detected") is True


def test_compute_optimal_injection_clean_route_non_negative():
    pools = {
        "POOL_A": {
            "total_executable_liquidity_usd": "500000",
            "fee_bps": 3000,
            "tokens": ["USDC", "WETH"],
            "reserves": ["250000", "100"],
        },
        "POOL_B": {
            "total_executable_liquidity_usd": "400000",
            "fee_bps": 3000,
            "tokens": ["WETH", "USDC"],
            "reserves": ["80", "200000"],
        },
    }
    result = compute_optimal_injection(
        pool_sequence=["POOL_A", "POOL_B"],
        pools=pools,
        path=["USDC", "WETH", "USDC"],
        flash_source=FlashSource.BALANCER,
    )
    assert result.cannibalization_detected is False
    assert result.optimal_injection_usd >= 0
    assert "cannibalization_checked" in (result.metadata or {})


def test_prepare_sizing_for_rust_shape():
    pools = {
        "P1": {"total_executable_liquidity_usd": "300000", "fee_bps": 500},
        "P2": {"total_executable_liquidity_usd": "280000", "fee_bps": 500},
    }
    params = prepare_sizing_for_rust(
        ["P1", "P2"],
        pools,
        path=["USDC", "USDT", "USDC"],
        flash_source=FlashSource.BALANCER,
    )
    assert "principal_usd" in params
    assert "sizing_method" in params
    assert params.get("cannibalization_detected") is False


def test_register_execution_venue_isolated():
    register_execution_venue("DISC_TEST_POOL", {"protocol": "UniswapV3", "type": "execution_venue"})
    from omega_v5.capital_injector import EXECUTION_VENUE_REGISTRY

    assert "DISC_TEST_POOL" in EXECUTION_VENUE_REGISTRY
    assert EXECUTION_VENUE_REGISTRY["DISC_TEST_POOL"].get("type") == "execution_venue"
    # Must not appear in capital sources
    assert "DISC_TEST_POOL" not in CAPITAL_SOURCE_REGISTRY
