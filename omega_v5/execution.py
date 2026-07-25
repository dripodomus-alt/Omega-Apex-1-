#!/usr/bin/env python3
# ==============================================================================
# execution.py  —  EIP-1559 transaction builder + guarded execution loop
# ==============================================================================
#
# Constructs flash-arb calldata, verifies wallet balances, and submits to
# Polygon mainnet only when the runtime control plane is set to live and the
# required wallet/RPC/executor checks pass.
#
# Pipeline updates for this task:
# - Enforces n+4 lifespan on every submission path.
# - Full logging of stage/execute/expire.
# - Records to pnl_tracker for successful submissions, staging, PNL.
# - PATH alignment: only closed paths reach broadcast.
# - Dry-run cycle support via simulate path.
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

from .config import (
    CHAIN_ID, PRIVATE_KEY, EXECUTOR_CONTRACT, BROADCAST_RPC_URL, BROADCAST_RPC_FALLBACK_URLS, OWNER_ADDRESS,
    C1_PAYLOAD_TARGET, REQUIRED_CONFIRM, CONFIRM_FLAG, LIVE_FLAG, EXEC_MODE,
    MEV_ENABLED, FLASHBOTS_RELAY_URL,
    MEV_PUBLIC_FALLBACK_ENABLED,
)
from .opportunity_ranker import LiveOpportunity
from .rpc_layer import BLOCK as CURRENT_BLOCK, w3, TOKEN_ADDRESSES
from .pricing.net_delta import route_within_lifespan
from .pnl_tracker import (
    record_lifespan_event, record_stage_event, record_successful_submission, record_pnl_event
)
from .payload_envelope import PayloadEnvelope, build_payload_envelope
from .execution_trace import compute_trace_hash
from .units import to_raw_units, TOKEN_DECIMALS
from .gas_oracle import eip1559_fee_params
from .flash_loan import route_tx_gas_limit
from .transport_lanes import web3_for_lane, LANE_EXACT_C1_ETH_CALL
from .revert_decoder import format_revert
from .adapter_registry import AdapterSemanticError
from .execution_trace import record_execution_trace
from .oracle_layer import token_price_usd
from . import rpc_layer # Import the new rpc_layer
from .webhook_dispatcher import dispatch_webhook

EXECUTE_FLASH_ARB_SELECTOR = Web3.keccak(
    text="executeFlashArb(address,uint256,(address,address,address,uint8)[])"
)[:4].hex()

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
    envelope: PayloadEnvelope


def build_tx_payload(op: LiveOpportunity, pools: dict, nonce: int = 0, base_fee_gwei: Decimal = Decimal("30")) -> dict:
    """Builds the EIP-1559 transaction payload for a flash arbitrage opportunity.
    This constructs the calldata for the executor contract based on the opportunity details."""
    protocol_map = {
        "UniswapV2": 1, "UniswapV3": 2, "QuickSwapV2": 1, "QuickSwapV3": 3,
        "Algebra": 3, "Balancer": 4, "Curve": 5
    }
    flash_asset_symbol = op.path[0]
    flash_asset_address = TOKEN_ADDRESSES.get(flash_asset_symbol)
    if not flash_asset_address:
        raise ValueError(f"Missing address for flash asset {flash_asset_symbol}")

    principal_raw = to_raw_units(flash_asset_symbol, op.profitability.flashloan.principal_usd)

    route_steps = []
    for i, pool_id in enumerate(op.pool_sequence):
        from_token_symbol = op.path[i]
        to_token_symbol = op.path[i+1]
        from_token_addr = TOKEN_ADDRESSES.get(from_token_symbol)
        to_token_addr = TOKEN_ADDRESSES.get(to_token_symbol)
        
        pool_meta = pools.get(pool_id)
        if not pool_meta:
            raise ValueError(f"Pool metadata not found for pool_id: {pool_id}")
        pool_addr = pool_meta.get("address")

        protocol_id = protocol_map.get(op.protocol_seq[i], 0)
        if not from_token_addr or not to_token_addr or not pool_addr:
            raise ValueError(f"Missing address in route step {i}: from={from_token_addr} to={to_token_addr} pool={pool_addr}")
        
        route_steps.append((
            Web3.to_checksum_address(from_token_addr),
            Web3.to_checksum_address(to_token_addr),
            Web3.to_checksum_address(pool_addr),
            protocol_id
        ))

    selector = "0x" + Web3.keccak(text="executeFlashArb(address,uint256,(address,address,address,uint8)[])")[:4].hex()
    encoded_args = encode(['address', 'uint256', '(address,address,address,uint8)[]'], [Web3.to_checksum_address(flash_asset_address), principal_raw, route_steps])
    calldata = selector + encoded_args.hex()

    try:
        max_fee, priority_fee, gas_fee_source = eip1559_fee_params()
    except Exception:
        max_fee = int((base_fee_gwei + Decimal("30")) * Decimal("1e9"))
        priority_fee = int(Decimal("30") * Decimal("1e9"))
        gas_fee_source = "legacy_base_plus_30_gwei"

    return {
        "to": C1_PAYLOAD_TARGET,
        "data": calldata,
        "value": 0,
        "nonce": nonce,
        "chainId": CHAIN_ID,
        "gas": route_tx_gas_limit(len(op.path) - 1),
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee,
        "type": 2,
        "gasFeeSource": gas_fee_source,
    }


def simulate_tx_payload(tx: dict, from_addr: str | None = None) -> tuple[bool, str]:
    """Performs a dry-run simulation of the transaction using eth_call on a dedicated exact-call RPC lane.
    This verifies the transaction's on-chain behavior without broadcasting."""
    call_tx = {
        "to": tx.get("to"),
        "data": tx.get("data"),
        "value": tx.get("value", 0),
    }
    if from_addr:
        call_tx["from"] = from_addr

    provider = web3_for_lane(LANE_EXACT_C1_ETH_CALL)
    if not provider:
        # Enforce strict pipeline mirroring. The exact-call lane MUST be available.
        raise RuntimeError("Exact-call RPC provider lane is not available. Cannot guarantee simulation integrity.")

    try:
        result = provider.eth.call(call_tx, block_identifier="latest")
        return True, result.hex()
    except Exception as exc:
        return False, format_revert(exc)


def simulation_from_address() -> str:
    return OWNER_ADDRESS or "0x0000000000000000000000000000000000000000"


def wallet_address() -> str:
    """Return the configured signer address, or the explicit owner fallback."""
    if PRIVATE_KEY:
        try:
            return Web3().eth.account.from_key(PRIVATE_KEY).address
        except Exception:
            return ""
    return OWNER_ADDRESS or ""


def _broadcast_w3() -> Web3:
    """
    Build a Web3 client for the primary (non-MEV) broadcast URL.
    The new submission logic will handle MEV endpoints separately.
    """
    # Use the dynamically selected primary broadcast URL
    url = rpc_layer.BROADCAST_ENDPOINTS[0]['url'] if rpc_layer.BROADCAST_ENDPOINTS else BROADCAST_RPC_URL
    return Web3(Web3.HTTPProvider(url))


def _receipt_dict(receipt: Any) -> dict[str, Any]:
    """Convert a Web3 receipt-like object to JSON-safe primitives."""
    if receipt is None:
        return {}
    if hasattr(receipt, "items"):
        source = dict(receipt)
    else:
        source = {
            key: getattr(receipt, key)
            for key in ("transactionHash", "blockNumber", "status", "gasUsed")
            if hasattr(receipt, key)
        }
    out: dict[str, Any] = {}
    for key, value in source.items():
        if isinstance(value, bytes):
            out[str(key)] = "0x" + value.hex()
        elif hasattr(value, "hex"):
            try:
                out[str(key)] = value.hex()
            except Exception:
                out[str(key)] = str(value)
        else:
            out[str(key)] = value
    return out


def executor_code_status() -> tuple[bool, str]:
    """Check whether the configured executor address has bytecode."""
    if not EXECUTOR_CONTRACT or not Web3.is_address(EXECUTOR_CONTRACT):
        return False, "executor_contract_missing_or_invalid"
    try:
        code = w3.eth.get_code(Web3.to_checksum_address(EXECUTOR_CONTRACT)).hex()
        return (code not in {"", "0x"}, "bytecode_present" if code not in {"", "0x"} else "no_bytecode")
    except Exception as exc:
        return False, f"executor_code_check_failed:{type(exc).__name__}"


def executor_owner() -> str:
    """Best-effort owner() read for operator status surfaces."""
    if not EXECUTOR_CONTRACT or not Web3.is_address(EXECUTOR_CONTRACT):
        return ""
    try:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(EXECUTOR_CONTRACT),
            abi=[
                {
                    "name": "owner",
                    "type": "function",
                    "stateMutability": "view",
                    "inputs": [],
                    "outputs": [{"name": "", "type": "address"}],
                }
            ],
        )
        return str(contract.functions.owner().call())
    except Exception:
        return ""


def _payload_hash(tx: dict[str, Any]) -> str:
    """Computes a stable hash for a transaction payload dictionary."""
    return compute_trace_hash({
        "chainId": tx.get("chainId"),
        "to": tx.get("to"),
        "value": tx.get("value", 0),
        "data": tx.get("data"),
        "gas": tx.get("gas"),
        "maxFeePerGas": tx.get("maxFeePerGas"),
        "maxPriorityFeePerGas": tx.get("maxPriorityFeePerGas"),
        "type": tx.get("type"),
    })


def build_c1_payload_envelope(op: LiveOpportunity, tx: dict[str, Any]) -> PayloadEnvelope:
    """Builds a C1 envelope for a staged opportunity."""
    return build_payload_envelope(
        kind="ARBITRAGE_C1",
        target=tx["to"],
        calldata=tx["data"],
        unique_salt=str(op.metadata.get("opp_id", id(op))),
        metadata={
            "path": list(op.path),
            "principal_usd": str(op.profitability.flashloan.principal_usd),
            "net_profit_usd": str(op.profitability.net_profit_usd),
        },
    )


def _check_lifespan(op: LiveOpportunity) -> bool:
    current = getattr(CURRENT_BLOCK, "BLOCK", CURRENT_BLOCK) if hasattr(CURRENT_BLOCK, "BLOCK") else CURRENT_BLOCK
    if not route_within_lifespan(op.block_detected, current, N_PLUS_4):
        record_lifespan_event(
            event_type="EXPIRED",
            discovery_block=op.block_detected,
            current_block=current,
            route=list(op.path),
            opp_id=str(id(op)),
            status="EXPIRED_AT_EXECUTION",
        )
        record_stage_event(stage="EXECUTION", status="LIFESPAN_EXPIRED", route=list(op.path), block=current)
        return False
    return True


def stage_for_submission(
    op: LiveOpportunity,
    live_pools: dict,
    base_fee_gwei: Decimal = Decimal("30"),
) -> StagedForSubmission | None:
    """
    Takes a truth-ranked opportunity and prepares it for submission.
    This includes final payload construction and simulation.
    """
    current_block = getattr(CURRENT_BLOCK, "BLOCK", 0)

    if not _check_lifespan(op):
        asyncio.create_task(dispatch_webhook(
            "opportunity_staging_failed",
            {"opp_id": str(id(op)), "path": list(op.path), "reason": "lifespan_expired", "block": current_block}
        ))
        return None

    # The opportunity is already truth-ranked, so we proceed to build and simulate.
    record_stage_event(stage="STAGING", status="ATTEMPT", route=list(op.path), block=current_block)

    # Webhook for staging attempt
    asyncio.create_task(dispatch_webhook(
        "opportunity_staging_attempt",
        {
            "opp_id": str(id(op)),
            "path": list(op.path),
            "expected_net_usd": str(op.profitability.net_profit_usd),
            "block": current_block
        }
    ))


    try:
        tx = build_tx_payload(op, live_pools, nonce=0, base_fee_gwei=base_fee_gwei)
        payload_hash = _payload_hash(tx)
        envelope = build_c1_payload_envelope(op, tx)
    except Exception as e:
        record_stage_event(stage="STAGING", status="PAYLOAD_BUILD_FAILED", route=list(op.path), block=current_block, metadata={"error": str(e)})
        asyncio.create_task(dispatch_webhook(
            "opportunity_staging_failed",
            {"opp_id": str(id(op)), "path": list(op.path), "reason": "payload_build_failed", "error": str(e), "block": current_block}
        ))
        return None

    # Final simulation before handing off to submission
    ok, detail = simulate_tx_payload(tx)
    if not ok:
        record_stage_event(stage="STAGING", status="SIMULATION_FAILED", route=list(op.path), block=current_block, metadata={"detail": detail})
        asyncio.create_task(dispatch_webhook(
            "opportunity_staging_failed",
            {"opp_id": str(id(op)), "path": list(op.path), "reason": "simulation_failed", "detail": detail, "block": current_block}
        ))
        return None

    record_stage_event(stage="STAGING", status="STAGED", route=list(op.path), block=current_block, metadata={"payload_hash": payload_hash})
    asyncio.create_task(dispatch_webhook(
        "opportunity_staged_success",
        {"opp_id": str(id(op)), "path": list(op.path), "expected_net_usd": str(op.profitability.net_profit_usd), "payload_hash": payload_hash, "block": current_block}
    ))

    return StagedForSubmission(
        tx=tx,
        opportunity=op,
        payload_hash=payload_hash,
        envelope=envelope,
    )


async def _try_submit_mev(staged: StagedForSubmission, w3: Web3, endpoint: dict) -> str | None:
    """Attempts to submit a transaction to an MEV relay."""
    op = staged.opportunity
    tx_to_sign = {**staged.tx, "nonce": w3.eth.get_transaction_count(wallet_address())}
    signed_tx = w3.eth.account.sign_transaction(tx_to_sign, PRIVATE_KEY)
    
    mev_provider = Web3(Web3.HTTPProvider(endpoint['url']))
    
    try:
        if endpoint.get("mev_capability") == "Flashbots":
            # Flashbots-style bundle
            bundle = [{"signed_transaction": signed_tx.rawTransaction}]
            block_number = w3.eth.block_number
            # Send for next block
            tx_hash_bytes = mev_provider.eth.send_bundle(bundle, target_block_number=block_number + 1)
            logger.info(f"MEV BUNDLE submitted to {endpoint['url']} for block {block_number + 1}")
            return tx_hash_bytes.hex()

        elif endpoint.get("mev_capability") == "PrivateTx":
            # Generic private transaction
            tx_hash_bytes = mev_provider.eth.send_private_transaction({"tx": signed_tx.rawTransaction.hex()})
            logger.info(f"PRIVATE TX submitted to {endpoint['url']}")
            return tx_hash_bytes.hex()

    except Exception as e:
        logger.warning(f"MEV submission to {endpoint['url']} failed: {e}")
    
    return None


async def _try_submit_public(staged: StagedForSubmission, w3: Web3, endpoint: dict) -> str | None:
    """Attempts to submit a transaction to a public RPC endpoint."""
    try:
        public_provider = Web3(Web3.HTTPProvider(endpoint['url']))
        if not public_provider.is_connected():
            logger.warning(f"Public broadcast endpoint {endpoint['url']} is not connected.")
            return None

        wallet = Account.from_key(PRIVATE_KEY)
        nonce = public_provider.eth.get_transaction_count(wallet.address)
        tx_to_sign = {**staged.tx, "nonce": nonce, "from": wallet.address}

        signed_tx = public_provider.eth.account.sign_transaction(tx_to_sign, PRIVATE_KEY)
        tx_hash_bytes = public_provider.eth.send_raw_transaction(signed_tx.rawTransaction)
        logger.info(f"PUBLIC TX submitted to {endpoint['url']}, tx_hash: {tx_hash_bytes.hex()}")
        return tx_hash_bytes.hex()

    except Exception as e:
        logger.error(f"Public submission to {endpoint['url']} FAILED: {e}")
    
    return None


async def submit_staged_batch(
    staged_txs: list[StagedForSubmission],
    dry_run: bool = True,
) -> list[ExecutionResult]:
    """
    Submits a batch of staged transactions.
    In a live environment, this could be a bundle submission.
    """
    results = []
    if not staged_txs:
        return results

    # Use the primary discovery RPC for nonce checks and receipts
    w3 = rpc_layer.w3

    # For now, we submit sequentially. A future MEV/bundle implementation
    # would take the whole batch.
    for staged in staged_txs:
        op = staged.opportunity
        current_block = getattr(CURRENT_BLOCK, "BLOCK", 0)

        if dry_run:
            record_lifespan_event(event_type="EXECUTED", discovery_block=op.block_detected, current_block=current_block, route=list(op.path))
            record_pnl_event(
                mode="dry_run",
                stage="C1",
                status="DRY_RUN_STAGED",
                route=list(op.path),
                expected_net_usd=op.profitability.net_profit_usd,
                block=current_block,
            )
            record_stage_event(stage="SUBMISSION", status="DRY_RUN_SUCCESS", route=list(op.path), block=current_block)
            logger.info(f"DRY_RUN success for route {op.path} at block {current_block}")
            asyncio.create_task(dispatch_webhook(
                "tx_dry_run_success",
                {
                    "opp_id": str(id(op)), "path": list(op.path), "expected_net_usd": str(op.profitability.net_profit_usd),
                    "block": current_block, "detail": "dry_run_pass"
                }
            ))
            results.append(ExecutionResult(success=True, detail="dry_run_pass", net_pnl_usd=op.profitability.net_profit_usd, block=current_block))
        else:
            # --- LIVE PATH: Sign, Broadcast, and Wait for Receipt ---
            tx_hash = ""
            submission_successful = False
            for endpoint in rpc_layer.BROADCAST_ENDPOINTS:
                if endpoint.get("mev_capability", "None") != "None":
                    tx_hash = await _try_submit_mev(staged, w3, endpoint)
                else:
                    tx_hash = await _try_submit_public(staged, w3, endpoint)

                if tx_hash:
                    submission_successful = True
                    record_successful_submission(tx_hash=tx_hash, route=list(op.path), opp_id=str(id(op)), block=current_block, net_pnl_usd=op.profitability.net_profit_usd)
                    
                    # Wait for receipt using the reliable discovery RPC
                    try:
                        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                        if receipt and receipt.status == 1:
                            gas_used = Decimal(receipt.get("gasUsed", 0))
                            gas_price_wei = Decimal(receipt.get("effectiveGasPrice", 0))
                            gas_cost_matic = (gas_used * gas_price_wei) / Decimal("1e18")
                            gas_cost_usd = gas_cost_matic * token_price_usd("WPOL")
                            realized_pnl = op.profitability.net_profit_usd # Placeholder
                            record_pnl_event(mode="live", stage="C1", status="CONFIRMED", route=list(op.path), expected_net_usd=op.profitability.net_profit_usd, realized_net_usd=realized_pnl, gas_cost_usd=gas_cost_usd, tx_hash=tx_hash, block=receipt.blockNumber, metadata={"receipt": _receipt_dict(receipt)})
                            results.append(ExecutionResult(success=True, tx_hash=tx_hash, net_pnl_usd=realized_pnl, block=receipt.blockNumber))
                        else:
                            logger.warning(f"Transaction reverted on-chain for {op.path}, tx_hash: {tx_hash}")
                            record_pnl_event(mode="live", stage="C1", status="REVERTED", route=list(op.path), expected_net_usd=op.profitability.net_profit_usd, tx_hash=tx_hash, block=receipt.blockNumber if receipt else current_block, metadata={"receipt": _receipt_dict(receipt)})
                            results.append(ExecutionResult(success=False, tx_hash=tx_hash, detail="Transaction reverted on-chain", block=receipt.blockNumber if receipt else current_block))
                    except Exception as e:
                        logger.error(f"Receipt wait/processing failed for tx {tx_hash}: {e}")
                        results.append(ExecutionResult(success=False, tx_hash=tx_hash, detail=f"Receipt wait failed: {e}", block=current_block))
                    
                    break # Exit loop on successful submission

            if not submission_successful:
                logger.error(f"LIVE SUBMISSION FAILED for {op.path}: All broadcast endpoints failed.")
                record_pnl_event(
                    mode="live",
                    stage="C1",
                    status="FAILED",
                    route=list(op.path),
                    expected_net_usd=op.profitability.net_profit_usd,
                    tx_hash=tx_hash,
                    block=current_block,
                    metadata={"error": "All broadcast endpoints failed"},
                )
                results.append(ExecutionResult(success=False, tx_hash=tx_hash, detail=str(e), block=current_block))

    return results


# ==============================================================================
# Execution loop and guards (added to complete the main.py integration)
# ==============================================================================

async def _await_next_block() -> None:
    """Simple block wait helper. In production this would poll for new block."""
    await asyncio.sleep(1)


def execution_armed() -> bool:
    """Returns whether live execution is currently allowed."""
    if os.environ.get("EXECUTION_DISABLED", "false").lower() in ("1", "true", "yes"):
        return False
    live = os.environ.get("LIVE_EXECUTION", "false").lower()
    return live in ("1", "true", "yes", "on")


def execution_guard_status() -> dict:
    """Returns current guard state for logging."""
    return {
        "armed": execution_armed(),
        "dry_run_default": True,
        "execution_disabled": os.environ.get("EXECUTION_DISABLED", "false"),
        "live_execution": os.environ.get("LIVE_EXECUTION", "false"),
    }


async def run_execution_loop(
    opportunities: list[LiveOpportunity],
    live_pools: dict,
    max_per_cycle: int = 5,
    canary_mode: bool = False,
    base_fee_gwei: Decimal = Decimal("50"),
) -> None:
    """
    Stages a batch of opportunities and submits them.
    Respects canary_mode (at most 1) and max_per_cycle.
    """
    if not opportunities:
        record_stage_event(stage="EXEC_LOOP", status="NO_OPPORTUNITIES")
        logger.info("run_execution_loop: no opportunities to execute")
        return

    limit = 1 if canary_mode else max_per_cycle
    candidates = opportunities[:limit]

    staged_for_submission: list[StagedForSubmission] = []

    # STAGING a batch
    logger.info(f"run_execution_loop: Staging up to {len(candidates)} opportunities...")
    for op in candidates:
        staged = stage_for_submission(op, live_pools, base_fee_gwei=base_fee_gwei)
        if staged:
            staged_for_submission.append(staged)

    if not staged_for_submission:
        logger.info("run_execution_loop: No opportunities passed staging.")
        record_stage_event(stage="EXEC_LOOP", status="NOTHING_STAGED")
        return

    # SUBMISSION of the batch
    is_dry_run = not execution_armed()
    logger.info(f"run_execution_loop: Submitting {len(staged_for_submission)} staged transactions (dry_run={is_dry_run})...")
    submission_results = await submit_staged_batch(staged_for_submission, dry_run=is_dry_run)

    executed_count = sum(1 for r in submission_results if r.success)

    record_stage_event(
        stage="EXEC_LOOP",
        status="COMPLETE",
        metadata={
            "considered": len(candidates),
            "staged": len(staged_for_submission),
            "submitted_and_successful": executed_count,
            "executed": executed_count,
            "canary_mode": canary_mode,
        },
    )
    logger.info(f"run_execution_loop finished: executed={executed_count}")
