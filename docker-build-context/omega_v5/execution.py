#!/usr/bin/env python3
# ==============================================================================
# execution.py  —  EIP-1559 transaction builder + guarded execution loop
# ==============================================================================
"""
This module is the final stage of the arbitrage pipeline, responsible for
taking a validated opportunity and executing it on the blockchain. It handles
transaction construction, simulation, and broadcasting with a strong emphasis
on safety and profitability.

Core Responsibilities:
-   **Transaction Building**: Constructs the raw EIP-1559 transaction, including
    the calldata for the `executeFlashArb` function on the executor contract.
-   **Final Simulation**: Performs a dry-run `eth_call` on the **latest pending block** to ensure the transaction
    is likely to succeed on-chain before signing and broadcasting. If actualProfit < minProfit, suppress dispatch.
-   **Guarded Execution**: Submits transactions to the network only when all
    safety guards (e.g., runtime mode is 'live', wallet checks pass) are met.
-   **Broadcasting**: Manages submission to both private (FastLane MEV) and public RPC
    endpoints, with logic for fallbacks.
-   **Receipt Handling**: Waits for transaction confirmation and records the
    outcome, including realized PnL.
"""
# ==============================================================================

from decimal import Decimal
from dataclasses import dataclass
from typing import List, Optional, Tuple, Any
from eth_account import Account
from web3 import Web3
from eth_abi import encode
import os
import logging
import asyncio
import time

from .config import (
    CHAIN_ID, PRIVATE_KEY, EXECUTOR_CONTRACT, BROADCAST_RPC_URL, BROADCAST_RPC_FALLBACK_URLS, OWNER_ADDRESS,
    C1_PAYLOAD_TARGET, REQUIRED_CONFIRM, CONFIRM_FLAG, LIVE_FLAG, EXEC_MODE,
    MEV_ENABLED, FLASHBOTS_RELAY_URL, FASTLANE_RELAY_URL, MIN_PROFIT_POL,
    MEV_PUBLIC_FALLBACK_ENABLED, PROTOCOL_ID_MAP, normalize_protocol,
)
from .opportunity_ranker import LiveOpportunity
from .rpc_layer import BLOCK as CURRENT_BLOCK, w3, TOKEN_ADDRESSES, TOKEN_DECIMALS
from .pricing.net_delta import route_within_lifespan
from .pnl_tracker import (
    record_lifespan_event, record_stage_event, record_successful_submission, record_pnl_event
)
from .payload_envelope import PayloadEnvelope, build_payload_envelope
from .execution_trace import compute_trace_hash
from .units import to_raw_units
from .gas_oracle import eip1559_fee_params
from .flash_loan import route_tx_gas_limit
from .transport_lanes import web3_for_lane, LANE_EXACT_C1_ETH_CALL
from .revert_decoder import format_revert
from .adapter_registry import AdapterSemanticError
from .execution_trace import record_execution_trace
from .oracle_layer import token_price_usd
from . import rpc_layer
from .mev import submit_via_fastlane_relay
from .webhook_dispatcher import dispatch_webhook
from .transport_lanes import record_for_holding_tank
from .pipeline_validation import validate_canonical_execution_proof

EXECUTE_FLASH_ARB_SELECTOR = "0xafa5f482"

logger = logging.getLogger("omega.execution")
logger.setLevel(logging.INFO)

N_PLUS_4 = 4


@dataclass
class ExecutionResult:
    success: bool
    tx_hash: str = ""
    detail: str = ""
    net_pnl_usd: Decimal = Decimal("0")
    block: int = 0


@dataclass
class StagedForSubmission:
    """A transaction that has passed all gates and is ready for submission."""
    tx: dict
    opportunity: LiveOpportunity
    payload_hash: str
    envelope: Optional[PayloadEnvelope]


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _opp_get(op: Any, key: str, default: Any = None) -> Any:
    if isinstance(op, dict):
        return op.get(key, default)
    return getattr(op, key, default)


def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return Decimal(stripped)
        except Exception:
            return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _opp_net_profit_usd(op: Any) -> Decimal:
    profitability = _opp_get(op, "profitability")
    if profitability is not None:
        if isinstance(profitability, dict):
            return _safe_decimal(profitability.get("net_profit_usd", "0"))
        return _safe_decimal(getattr(profitability, "net_profit_usd", "0"))
    return _safe_decimal(_opp_get(op, "net_gain_usd", "0"))


def _opp_principal_usd(op: Any) -> Decimal:
    profitability = _opp_get(op, "profitability")
    if profitability is not None:
        flashloan = profitability.get("flashloan") if isinstance(profitability, dict) else getattr(profitability, "flashloan", None)
        if isinstance(flashloan, dict):
            return _safe_decimal(flashloan.get("principal_usd", "0"))
        if flashloan is not None:
            return _safe_decimal(getattr(flashloan, "principal_usd", "0"))
    return _safe_decimal(_opp_get(op, "principal_usd", "0"))


def revalidate_profitability_at_broadcast(
    op: LiveOpportunity,
    current_pools: dict,
    tx_payload: Optional[dict[str, Any]] = None,
) -> bool:
    """
    Re-checks that the opportunity is still net-profitable right before broadcast.
    Now uses pending block simulation and the canonical execution proof gate.
    """
    try:
        route_payload = {
            "opp_id": _opp_get(op, "opp_id", "unknown"),
            "principal_token": _opp_get(op, "principal_token", "USDC"),
            "principal_usd": _opp_principal_usd(op),
            "profitability": {
                "gross_surplus_usd": _safe_decimal(_opp_get(op, "gross_surplus_usd", 0)),
                "flashloan_fee_usd": _safe_decimal(_opp_get(op, "flashloan_fee_usd", 0)),
                "gas_cost_usd": _safe_decimal(_opp_get(op, "gas_cost_usd", 0)),
                "relay_tip_usd": _safe_decimal(_opp_get(op, "relay_tip_usd", 0)),
                "risk_buffer_usd": _safe_decimal(_opp_get(op, "risk_buffer_usd", 0)),
                "net_profit_usd": _opp_net_profit_usd(op),
            },
            "protocol_seq": list(_opp_get(op, "protocol_seq", []) or []),
            "path": list(_opp_get(op, "path", []) or []),
            "pool_sequence": list(_opp_get(op, "pool_sequence", []) or []),
        }
        if not validate_canonical_execution_proof(route_payload, opportunity_id=str(route_payload["opp_id"]), cycle_id="execution_broadcast"):
            logger.warning("Revalidate failed: canonical execution proof mismatch")
            return False

        net = _opp_net_profit_usd(op)
        if net <= Decimal("0"):
            logger.warning("Revalidate failed: non-positive net profit at broadcast time")
            return False

        # Pre-flight exact eth_call on pending block using the real payload.
        if not simulate_on_pending_block(op, current_pools, tx_payload=tx_payload):
            logger.warning("Pre-flight pending simulation failed or profit too low")
            return False

        if net < Decimal(str(MIN_PROFIT_POL)):
            logger.warning(f"Suppressing dispatch: actual profit {net} < min {MIN_PROFIT_POL}")
            return False

        # Re-check lifespan if block info available
        block_detected = _opp_get(op, "block_detected", 0)
        if block_detected:
            latest_block = int(getattr(rpc_layer, "BLOCK", 0) or 0)
            if not route_within_lifespan(discovery_block=int(block_detected), current_block=latest_block):
                logger.warning("Revalidate failed: route outside N+4 lifespan at broadcast")
                return False

        family = str(_opp_get(op, "family", "C1"))
        if family == "LIQUIDATION":
            return net > Decimal("0")

        return net > Decimal("0.5")
    except Exception as e:
        logger.error(f"Revalidate error: {e}")
        return False


def simulate_on_pending_block(
    op: LiveOpportunity,
    current_pools: Optional[dict] = None,
    tx_payload: Optional[dict[str, Any]] = None,
) -> bool:
    """Performs exact eth_call on 'pending' block using route calldata."""
    try:
        if not Web3.is_address(str(C1_PAYLOAD_TARGET)):
            return not _send_allowed()

        pools = current_pools or {}
        tx = tx_payload if isinstance(tx_payload, dict) else build_tx_payload(op, pools, nonce=0)
        ok, detail = simulate_tx_payload(tx)
        if not ok:
            logger.warning("Pending block simulation failed: %s", detail)
            return False

        logger.info("Pending block simulation passed for opportunity: %s", detail)
        return True
    except Exception as e:
        logger.warning(f"Pending simulation failed: {e}")
        return False


def build_tx_payload(op: LiveOpportunity, pools: dict, nonce: int = 0, base_fee_gwei: Decimal = Decimal("30")) -> dict:
    """Builds the EIP-1559 transaction payload for a flash arbitrage opportunity."""
    path = list(_opp_get(op, "path", []) or [])
    pool_sequence = list(_opp_get(op, "pool_sequence", []) or [])
    protocol_seq = list(_opp_get(op, "protocol_seq", []) or [])
    if len(path) < 2:
        raise ValueError("invalid_opportunity_path")

    flash_asset_symbol = path[0]
    flash_asset_address = TOKEN_ADDRESSES.get(flash_asset_symbol)
    if not flash_asset_address:
        raise ValueError(f"Missing address for flash asset {flash_asset_symbol}")

    principal_raw = to_raw_units(flash_asset_symbol, _opp_principal_usd(op))

    route_steps = []
    for i, (token_in, token_out) in enumerate(zip(path[:-1], path[1:])):
        pool_id = pool_sequence[i] if i < len(pool_sequence) else None
        pool_meta = pools.get(pool_id, {}) if pool_id else {}
        pool_address = pool_meta.get("address")
        if not pool_address:
            raise ValueError(f"Pool metadata not found for pool_id: {pool_id}")

        token_in_addr = TOKEN_ADDRESSES.get(token_in)
        token_out_addr = TOKEN_ADDRESSES.get(token_out)
        if not token_in_addr or not token_out_addr:
            raise ValueError(f"Missing address in route step {i}: from={token_in_addr} to={token_out_addr}")

        protocol = normalize_protocol(protocol_seq[i] if i < len(protocol_seq) else "UniswapV2")
        protocol_id = PROTOCOL_ID_MAP.get(protocol, 1)

        route_steps.append((pool_address, token_in_addr, token_out_addr, protocol_id))

    encoded_route = encode(
        ["(address,address,address,uint8)[]"],
        [route_steps]
    )

    data = EXECUTE_FLASH_ARB_SELECTOR + encoded_route.hex()

    try:
        max_fee, max_priority, gas_source = eip1559_fee_params()
    except Exception:
        max_fee = int((base_fee_gwei + Decimal("30")) * Decimal("1e9"))
        max_priority = int(Decimal("30") * Decimal("1e9"))
        gas_source = "legacy_base_plus_30_gwei"

    gas_limit = route_tx_gas_limit(len(op.path) - 1)

    tx = {
        "to": C1_PAYLOAD_TARGET,
        "value": 0,
        "nonce": nonce,
        "chainId": CHAIN_ID,
        "gas": gas_limit,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority,
        "type": 2,
        "data": data,
        "gasFeeSource": gas_source,
    }
    return tx


def _send_allowed() -> bool:
    """Central guard for whether we are allowed to broadcast real transactions."""
    if str(EXEC_MODE).lower() != "live":
        return False
    if not _is_truthy(LIVE_FLAG):
        return False
    if str(CONFIRM_FLAG or "").strip() != str(REQUIRED_CONFIRM):
        return False
    if not PRIVATE_KEY or PRIVATE_KEY.startswith("0x0000"):
        return False
    return True


async def simulate_and_maybe_broadcast(
    staged: StagedForSubmission,
    current_pools: dict = None
) -> ExecutionResult:
    """
    Performs final eth_call simulation on pending block then (if allowed and profitable) broadcasts via FastLane.
    """
    current_pools = current_pools or {}
    op = staged.opportunity

    if not revalidate_profitability_at_broadcast(op, current_pools, tx_payload=staged.tx):
        return ExecutionResult(
            success=False,
            detail="Revalidate failed: opportunity no longer profitable or pending simulation failed"
        )

    if not _send_allowed():
        logger.info("Broadcast blocked by guards (EXEC_MODE=%s, LIVE=%s)", EXEC_MODE, LIVE_FLAG)
        return ExecutionResult(success=False, detail="Broadcast guards not satisfied (dry-run)")

    try:
        # The opportunity has passed all gates. Place it in the holding tank
        # for the dedicated broadcaster daemon to pick up and submit.
        holding_tank_payload = {
            "tx": staged.tx,
            "opp_id": str(_opp_get(op, "opp_id", "unknown")),
            "net_profit_usd": str(_opp_net_profit_usd(op)),
            "staged_at": int(time.time()),
        }
        record_for_holding_tank(holding_tank_payload)
        logger.info(f"Opportunity {_opp_get(op, 'opp_id', 'unknown')} passed all gates and was sent to the holding tank.")
        # This function's responsibility now ends here.
        return ExecutionResult(success=True, detail="Sent to holding tank", net_pnl_usd=_opp_net_profit_usd(op))
    except Exception as e:
        logger.error(f"Failed to send opportunity {_opp_get(op, 'opp_id', 'unknown')} to holding tank: {e}")
        return ExecutionResult(success=False, detail=str(e))


def _broadcast_w3() -> Web3:
    """Return the broadcast Web3 client used for send/receipt paths."""
    if BROADCAST_RPC_URL:
        return Web3(Web3.HTTPProvider(BROADCAST_RPC_URL))
    return w3


def _receipt_dict(receipt: Any) -> dict[str, Any]:
    """Normalize Web3 receipt objects for JSON logging."""
    if receipt is None:
        return {}
    try:
        raw = dict(receipt)
    except Exception:
        raw = {key: getattr(receipt, key) for key in dir(receipt) if not key.startswith("_")}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, bytes):
            out[key] = "0x" + value.hex()
        elif isinstance(value, list):
            out[key] = [dict(item) if hasattr(item, "items") else item for item in value]
        else:
            out[key] = value
    return out


def wallet_address() -> str:
    """Resolve the configured signer address without exposing the private key."""
    if PRIVATE_KEY and not PRIVATE_KEY.startswith("0x0000"):
        try:
            return Account.from_key(PRIVATE_KEY).address
        except Exception:
            logger.warning("Configured private key could not derive a wallet address")
    return OWNER_ADDRESS or ""


def simulation_from_address() -> str:
    """Address to use for eth_call simulation sender."""
    return wallet_address() or OWNER_ADDRESS or C1_PAYLOAD_TARGET or ""


def executor_code_status() -> tuple[bool, str]:
    """Check executor bytecode presence on the active RPC."""
    if not C1_PAYLOAD_TARGET:
        return False, "missing_executor_address"
    try:
        code = w3.eth.get_code(Web3.to_checksum_address(C1_PAYLOAD_TARGET))
        return (len(code) > 0, f"code_bytes={len(code)}")
    except Exception as exc:
        return False, f"code_check_error:{type(exc).__name__}:{exc}"


def executor_owner() -> str:
    """Best-effort owner read for dashboards; blank on ABI/RPC ambiguity."""
    if OWNER_ADDRESS:
        return OWNER_ADDRESS
    return wallet_address()


def simulate_tx_payload(tx: dict[str, Any], from_addr: Optional[str] = None, w3_override: Optional[Web3] = None) -> tuple[bool, str]:
    """
    Fail-closed exact eth_call helper for staged transaction payloads.

    This does not sign or broadcast. It only proves the call path is executable
    against the selected RPC state. Any missing target/data or RPC ambiguity is
    returned as a failed simulation.
    """
    # Use the provided w3 instance, or get one from the transport lane.
    w3_instance = w3_override or web3_for_lane(LANE_EXACT_C1_ETH_CALL)

    if not isinstance(tx, dict):
        return False, "invalid_tx_payload"
    to_addr = tx.get("to") or C1_PAYLOAD_TARGET
    data = tx.get("data")
    if not to_addr:
        return False, "missing_tx_to"
    if not isinstance(data, str) or not data.startswith("0x") or len(data) < 10:
        return False, "missing_or_short_calldata"
    call_tx = {
        "to": Web3.to_checksum_address(str(to_addr)),
        "data": data,
        "value": int(tx.get("value", 0) or 0),
    }
    sender = from_addr or simulation_from_address()
    if sender:
        call_tx["from"] = Web3.to_checksum_address(str(sender))
    gas = tx.get("gas") or tx.get("gasLimit")
    if gas:
        call_tx["gas"] = int(gas)
    try:
        result = w3_instance.eth.call(call_tx, block_identifier="pending")
        size = len(result) if result is not None else 0
        return True, f"eth_call_pass:return_bytes={size}"
    except Exception as exc:
        return False, f"eth_call_failed:{format_revert(exc)}"

async def _await_next_block(timeout_seconds: float = 30.0) -> int:
    """Wait until the observed block number advances, then return it."""
    start_block = int(getattr(w3.eth, "block_number", 0) or 0)
    deadline = asyncio.get_event_loop().time() + float(timeout_seconds)
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(1)
        try:
            current = int(getattr(w3.eth, "block_number", 0) or 0)
        except Exception:
            current = start_block
        if current > start_block:
            return current
    return start_block


def execution_armed() -> bool:
    """True only when all explicit live-broadcast guards are satisfied."""
    return _send_allowed()


def execution_guard_status() -> dict[str, Any]:
    """Expose guard state for dashboards and dry-run readiness checks."""
    has_private_key = bool(PRIVATE_KEY and not PRIVATE_KEY.startswith("0x0000"))
    return {
        "armed": _send_allowed(),
        "exec_mode": EXEC_MODE,
        "live_flag": _is_truthy(LIVE_FLAG),
        "confirm_flag": str(CONFIRM_FLAG or "").strip() == str(REQUIRED_CONFIRM),
        "has_private_key": has_private_key,
        "executor": C1_PAYLOAD_TARGET,
        "chain_id": CHAIN_ID,
    }


async def run_execution_loop(opportunities: Optional[List[LiveOpportunity]] = None, pools: Optional[dict] = None, nonce: int = 0) -> list[ExecutionResult]:
    """
    Minimal guarded execution loop used by ops/tests.

    In dry-run it builds and simulates payloads but does not broadcast. Live send
    still goes through simulate_and_maybe_broadcast and _send_allowed().
    """
    results: list[ExecutionResult] = []
    pools = pools or {}
    for index, op in enumerate(opportunities or []):
        try:
            tx = build_tx_payload(op, pools, nonce + index)
            ok, detail = simulate_tx_payload(tx)
            if not ok:
                results.append(ExecutionResult(success=False, detail=detail))
                continue
            staged = StagedForSubmission(tx=tx, opportunity=op, payload_hash="loop", envelope=None)
            results.append(await simulate_and_maybe_broadcast(staged, pools))
        except Exception as exc:
            results.append(ExecutionResult(success=False, detail=f"execution_loop_error:{type(exc).__name__}:{exc}"))
    return results

def execute_route(op: LiveOpportunity, pools: dict, nonce: int = 0) -> ExecutionResult:
    """Synchronous wrapper used by some callers."""
    try:
        if not revalidate_profitability_at_broadcast(op, pools):
            return ExecutionResult(success=False, detail="Failed re-profitability gate at execution entry")
        tx = build_tx_payload(op, pools, nonce)
        staged = StagedForSubmission(tx=tx, opportunity=op, payload_hash="legacy", envelope=None)
        
        # Execute via synchronous simulation gate
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(simulate_and_maybe_broadcast(staged, pools))
    except (ValueError, TypeError) as e:
        return ExecutionResult(success=False, detail=f"Failed to build transaction payload: {e}")
    except Exception as e:
        return ExecutionResult(success=False, detail=f"Execution error: {e}")

if __name__ == "__main__":
    print("execution.py - guarded execution with pending-block pre-flight and FastLane routing")
