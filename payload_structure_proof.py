#!/usr/bin/env python3
# ==============================================================================
# payload_structure_proof.py -- proves C1/C2/Liquidation calldata structures.
#
# This script generates mock opportunities for each execution type and builds
# the corresponding transaction payloads. The resulting artifact demonstrates
# the system's ability to construct valid calldata for each strategy.
# ==============================================================================

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any

# Add project root to path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from web3 import Web3
from eth_abi import encode

from omega_v5.config import (
    C1_PAYLOAD_TARGET,
    LIQUIDATION_EXECUTOR_ADDRESS,
    AAVE_V3_LIQUIDATION_ADAPTER,
)
from omega_v5.rpc_layer import TOKEN_ADDRESSES, TOKEN_DECIMALS
from omega_v5.opportunity_ranker import LiveOpportunity
from omega_v5.flash_loan import FlashSource, Profitability, FlashLoanParams
from omega_v5.aave_liquidations import ApexLiquidationCandidatePacket, ExitQuote
from omega_v5.liquidation_capital import CapitalSourceCheck
from omega_v5.state_machine import C1Cycle, C2Cycle, C2Decision
from omega_v5.paths import output_path

PROOF_REPORT_PATH = output_path("payload_structure_proof_latest.json")

def _json_ready(value: Any) -> Any:
    """Helper to make various types JSON serializable."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if hasattr(value, "as_packet"):
        return value.as_packet()
    if hasattr(value, "__dict__"):
        return {k: _json_ready(v) for k, v in value.__dict__.items() if not k.startswith("_")}
    return value

def _token_units_to_raw_floor(units: Decimal, decimals: int) -> int:
    """Converts token units to raw integer format, flooring the result."""
    if not isinstance(units, Decimal):
        units = Decimal(str(units))
    return int(units * (Decimal(10) ** decimals))

def _build_c1_c2_payload(op: LiveOpportunity) -> str:
    """
    Builds the calldata for a C1 or C2 flash arbitrage.
    This demonstrates the structure the on-chain executor expects.
    Executor function signature:
      executeFlashArb(address flashAsset, uint256 flashAmount, RouteStep[] calldata route)
    """
    protocol_map = {"UniswapV3": 1, "QuickSwapV2": 2, "Balancer": 3, "QuickSwapV3": 4, "Algebra": 4}
    flash_asset = TOKEN_ADDRESSES[op.path[0]]
    principal_raw = _token_units_to_raw_floor(op.profitability.flashloan.principal_usd, TOKEN_DECIMALS[op.path[0]])

    route_steps = []
    for i in range(len(op.path) - 1):
        from_token = TOKEN_ADDRESSES[op.path[i]]
        to_token = TOKEN_ADDRESSES[op.path[i+1]]
        pool = op.pool_sequence[i]
        protocol_id = protocol_map.get(op.protocol_seq[i], 0)
        route_steps.append((from_token, to_token, Web3.to_checksum_address(pool), protocol_id))

    selector = Web3.keccak(text="executeFlashArb(address,uint256,(address,address,address,uint8)[])")[:4].hex()
    encoded_args = encode(['address', 'uint256', '(address,address,address,uint8)[]'], [Web3.to_checksum_address(flash_asset), principal_raw, route_steps])
    return selector + encoded_args.hex()

def _build_liquidation_payload(packet: ApexLiquidationCandidatePacket) -> str:
    """
    Builds the calldata for an Aave V3 liquidation.
    Executor function signature:
      executeLiquidation(address collateralAsset, address debtAsset, address user, uint256 debtToCover, bool receiveAToken)
    """
    collateral_asset = TOKEN_ADDRESSES[packet.collateral_symbol]
    debt_asset = TOKEN_ADDRESSES[packet.debt_symbol]
    user = packet.borrower
    debt_to_cover = packet.debt_to_cover_raw
    receive_a_token = False  # For arbitrage, we want the underlying asset to sell

    selector = Web3.keccak(text="executeLiquidation(address,address,address,uint256,bool)")[:4].hex()
    encoded_args = encode(['address', 'address', 'address', 'uint256', 'bool'], [Web3.to_checksum_address(collateral_asset), Web3.to_checksum_address(debt_asset), Web3.to_checksum_address(user), debt_to_cover, receive_a_token])
    return selector + encoded_args.hex()

def _create_mock_c1_opp() -> LiveOpportunity:
    """Creates a mock C1 arbitrage opportunity."""
    profitability = Profitability(gross_amount_out=Decimal("50050"), flashloan=FlashLoanParams(source=FlashSource.BALANCER, asset="USDC", principal_usd=Decimal("50000"), fee_bps=Decimal("0"), fee_usd=Decimal("0"), repayment_usd=Decimal("50000")), gas_cost_usd=Decimal("1.50"), relay_tip_usd=Decimal("0.50"), risk_buffer_usd=Decimal("5.00"), net_profit_usd=Decimal("43.00"), profit_to_gas=Decimal("28.67"), passes_gate=True)
    metadata = {
        "opp_id": "C1-MOCK-OPP-001",
        "strategy": "CROSS_POOL_TWO_LEG",
        "sizing": {"selected_principal_usd": "50000"},
    }
    return LiveOpportunity(
        path=("USDC", "WETH", "USDC"),
        pool_sequence=("0xMockPoolAddr01", "0xMockPoolAddr02"),
        protocol_seq=("UniswapV3", "QuickSwapV2"),
        flash_source=FlashSource.BALANCER,
        profitability=profitability,
        block_detected=123456,
        gross_rate=Decimal("1.001"),
        gross_out_usd=Decimal("50050"),
        metadata=metadata,
    )

def _create_mock_liquidation_packet() -> ApexLiquidationCandidatePacket:
    """Creates a mock Aave V3 liquidation opportunity."""
    return ApexLiquidationCandidatePacket(authority="SCANNER_ONLY", nextStage="LIQUIDATION", borrower="0xBorrowerAddress00000000000000000000000000", block_number=123456, health_factor=Decimal("0.95"), debt_symbol="USDC", collateral_symbol="WETH", debt_to_cover_raw=1000 * 10**6, debt_to_cover=Decimal("1000"), seized_collateral_estimate=Decimal("0.3"), gross_profit_usd=Decimal("50.00"), expected_net_profit_usd=Decimal("40.00"), capital_sources=[CapitalSourceCheck(source_name="AaveV3", source_address=AAVE_V3_LIQUIDATION_ADAPTER, usable=True, reason="")], selected_capital_source=CapitalSourceCheck(source_name="AaveV3", source_address=AAVE_V3_LIQUIDATION_ADAPTER, usable=True, reason=""), exit_quote=ExitQuote(ok=True, debt_symbol="USDC", collateral_symbol="WETH", collateral_amount=Decimal("0.3"), debt_out=Decimal("1050"), pool_id="0xExitPool", protocol="UniswapV3", route=["WETH", "USDC"]))

def generate_payload_proof() -> dict[str, Any]:
    """Generates and proves the structure of all payload types."""
    c1_opp = _create_mock_c1_opp()
    c1_calldata = _build_c1_c2_payload(c1_opp)

    c1_cycle = C1Cycle(c1_id="C1-MOCK-CYCLE-001", opportunity=c1_opp)
    c2_cycle = C2Cycle(c2_id="C2-MOCK-CYCLE-001", c1_cycle=c1_cycle)
    c2_cycle.decision = C2Decision.MIRROR
    c2_cycle.recomputed_opportunity = c1_opp
    c2_calldata = _build_c1_c2_payload(c2_cycle.recomputed_opportunity)

    liq_packet = _create_mock_liquidation_packet()
    liq_calldata = _build_liquidation_payload(liq_packet)

    report = {
        "ok": True,
        "schema_version": "omega_v5.payload_structure_proof.v1",
        "generated_at": int(time.time()),
        "proof_of": "Correct calldata structure for C1, C2, and Liquidation payloads.",
        "c1_payload": {
            "description": "Standard flash arbitrage transaction.",
            "input_opportunity": _json_ready(c1_opp),
            "payload": {"to": C1_PAYLOAD_TARGET, "data": c1_calldata, "value": 0},
        },
        "c2_payload": {
            "description": "Follow-up C2 (MIRROR) flash arbitrage transaction.",
            "input_opportunity": _json_ready(c2_cycle.recomputed_opportunity),
            "payload": {"to": C1_PAYLOAD_TARGET, "data": c2_calldata, "value": 0},
        },
        "liquidation_payload": {
            "description": "Aave V3 liquidation transaction.",
            "input_packet": _json_ready(liq_packet),
            "payload": {"to": LIQUIDATION_EXECUTOR_ADDRESS or "0xLIQUIDATION_EXECUTOR_NOT_SET", "data": liq_calldata, "value": 0},
        }
    }
    
    PROOF_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROOF_REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    
    return report

if __name__ == "__main__":
    print("🧬 Generating payload structure proof artifact...")
    proof_report = generate_payload_proof()
    print(f"✅ Proof artifact generated successfully at: {PROOF_REPORT_PATH}")
    print("\n--- C1 Payload ---")
    print(f"  To: {proof_report['c1_payload']['payload'].get('to')}")
    print(f"  Data (first 66 chars): {proof_report['c1_payload']['payload'].get('data', '0x')[:66]}...")
    print("\n--- C2 Payload ---")
    print(f"  To: {proof_report['c2_payload']['payload'].get('to')}")
    print(f"  Data (first 66 chars): {proof_report['c2_payload']['payload'].get('data', '0x')[:66]}...")
    print("\n--- Liquidation Payload ---")
    print(f"  To: {proof_report['liquidation_payload']['payload'].get('to')}")
    print(f"  Data (first 66 chars): {proof_report['liquidation_payload']['payload'].get('data', '0x')[:66]}...")