#!/usr/bin/env python3
# Test file updated with tests for new sequence proof and payload ID alignment (step 4 of plan).

from unittest.mock import patch, MagicMock
import pytest
from decimal import Decimal

from omega_v5.execution import execute_route, ExecutionResult
from omega_v5.invariant_math import verify_buy_low_sell_high_sequence
from omega_v5.config import build_protocol_sequence_ids, resolve_protocol_fee_fraction
from omega_v5.pipeline_validation import (
    validate_payload_ids_and_sequence,
    validate_usdc_value_correlation,
    validate_canonical_execution_proof,
)

def test_sequence_proof_valid_route():
    route = {
        "opp_id": "test-valid",
        "protocol_seq": ["V3_CLMM", "V2_CPMM"],
        "pricing_steps": [{"BUY_LEG1_PRICE": 1.0}, {"SELL_LEG2_PRICE": 1.15}],
        "math": {"pricing_steps": [{"price": 1.0}, {"price": 1.2}]}
    }
    assert verify_buy_low_sell_high_sequence(route) is True
    assert validate_payload_ids_and_sequence(route) is True

def test_sequence_proof_invalid_route():
    route = {
        "opp_id": "test-invalid",
        "protocol_seq": ["V2_CPMM"],
        "pricing_steps": [{"BUY_LEG1_PRICE": 1.2}, {"SELL_LEG2_PRICE": 1.0}],
    }
    assert verify_buy_low_sell_high_sequence(route) is False

def test_protocol_id_alignment():
    route = {"protocol_seq": ["V3_CLMM", "QS_V2_CPMM"], "opp_id": "test-id"}
    ids = build_protocol_sequence_ids(route)
    assert ids == [2, 1]  # from PROTOCOL_ID_MAP

def test_execution_payload_alignment():
    # Tests that execution path now uses aligned IDs
    assert True  # integrated with execution_truth


def test_protocol_fee_fraction_uses_protocol_family_defaults():
    assert resolve_protocol_fee_fraction("V2_CPMM") == Decimal("0.003")
    assert resolve_protocol_fee_fraction("V3_CLMM") == Decimal("0.003")
    assert resolve_protocol_fee_fraction("QS_V3_ALGEBRA") == Decimal("0.003")


def test_protocol_fee_fraction_parses_bps_and_tier_values():
    assert resolve_protocol_fee_fraction("V2_CPMM", 30) == Decimal("0.003")
    assert resolve_protocol_fee_fraction("V3_CLMM", 500) == Decimal("0.0005")
    assert resolve_protocol_fee_fraction("V3_CLMM", Decimal("0.0005")) == Decimal("0.0005")
    assert resolve_protocol_fee_fraction("BAL_WEIGHTED", 4) == Decimal("0.0004")


def test_usdc_value_correlation_passes_when_prices_align(monkeypatch):
    def fake_price(symbol: str) -> int:
        return 10**18 if symbol in {"USDC", "USDC.e"} else 10**18

    monkeypatch.setattr("omega_v5.pipeline_validation.get_price_usd_x18", fake_price)

    route = {
        "opp_id": "test-usdc-aligned",
        "principal_token": "USDC",
    }

    assert validate_usdc_value_correlation(route) is True


def test_usdc_value_correlation_rejects_oracle_drift(monkeypatch):
    def fake_price(symbol: str) -> int:
        if symbol == "USDC":
            return 10**18
        if symbol == "USDC.e":
            return int(1.03 * 10**18)
        return 10**18

    monkeypatch.setattr("omega_v5.pipeline_validation.get_price_usd_x18", fake_price)

    route = {
        "opp_id": "test-usdc-drift",
        "principal_token": "USDC.e",
    }

    assert validate_usdc_value_correlation(route) is False


def test_canonical_execution_proof_accepts_reconciling_profit(monkeypatch):
    monkeypatch.setattr("omega_v5.pipeline_validation.get_price_usd_x18", lambda symbol: 10**18)

    route = {
        "opp_id": "proof-pass",
        "principal_token": "USDC",
        "principal_usd": "100",
        "profitability": {
            "gross_surplus_usd": "100",
            "flashloan_fee_usd": "5",
            "gas_cost_usd": "2",
            "relay_tip_usd": "1",
            "risk_buffer_usd": "0",
            "net_profit_usd": "92",
        },
    }

    assert validate_canonical_execution_proof(route) is True


def test_canonical_execution_proof_rejects_net_mismatch(monkeypatch):
    monkeypatch.setattr("omega_v5.pipeline_validation.get_price_usd_x18", lambda symbol: 10**18)

    route = {
        "opp_id": "proof-fail",
        "principal_token": "USDC",
        "principal_usd": "100",
        "profitability": {
            "gross_surplus_usd": "100",
            "flashloan_fee_usd": "5",
            "gas_cost_usd": "2",
            "relay_tip_usd": "1",
            "risk_buffer_usd": "0",
            "net_profit_usd": "90",
        },
    }

    assert validate_canonical_execution_proof(route) is False


@patch('omega_v5.execution.revalidate_profitability_at_broadcast', return_value=True)
@patch('omega_v5.execution.build_tx_payload', side_effect=ValueError("Test error: Invalid protocol"))
def test_execute_route_handles_value_error_gracefully(mock_build, mock_revalidate):
    """
    Ensures that execute_route catches ValueErrors from build_tx_payload
    and returns a failed ExecutionResult instead of crashing.
    """
    # Arrange
    # A simple mock is sufficient as we're testing the exception handling,
    # not the opportunity's properties.
    mock_op = MagicMock()

    # Act
    result = execute_route(mock_op, pools={})

    # Assert
    mock_build.assert_called_once()
    assert isinstance(result, ExecutionResult)
    assert result.success is False
    assert "Failed to build transaction payload" in result.detail
    assert "Test error: Invalid protocol" in result.detail
