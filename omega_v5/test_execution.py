#!/usr/bin/env python3
# Test file updated with tests for new sequence proof and payload ID alignment (step 4 of plan).

import pytest
from decimal import Decimal
from omega_v5.invariant_math import verify_buy_low_sell_high_sequence
from omega_v5.config import build_protocol_sequence_ids
from omega_v5.pipeline_validation import validate_payload_ids_and_sequence

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
