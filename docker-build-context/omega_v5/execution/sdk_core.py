"""
sdk_core.py - Core SDK-driven transaction submission logic.

This module provides a high-performance, web3.py-native implementation for
signing, broadcasting, and managing transactions. It is designed to be called
by operational scripts like `run_benchmark.py` for live and anvil modes.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List

from web3 import Web3
from web3.exceptions import TransactionNotFound

try:
    from web3.middleware import geth_poa_middleware
except ImportError:  # pragma: no cover - compatibility for newer web3.py
    geth_poa_middleware = None

from .. import config
from ..gas_oracle import eip1559_fee_params
from ..paths import output_path

logger = logging.getLogger(__name__)


def get_gas_policy(w3: Web3) -> Dict[str, Any]:
    """Build a minimal EIP-1559 gas policy that works in dry-run and local benchmark paths."""
    try:
        max_fee, priority_fee, _ = eip1559_fee_params()
        return {
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee,
        }
    except Exception:
        return {"maxFeePerGas": 30_000_000_000, "maxPriorityFeePerGas": 1_500_000_000}


def get_web3_instance(rpc_url: str) -> Web3:
    """Initializes and returns a configured Web3 instance."""
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
    if geth_poa_middleware is not None and ("poa" in rpc_url.lower() or "drpc" in rpc_url.lower()):
        try:
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except Exception:
            logger.debug("POA middleware injection skipped", exc_info=True)
    if not w3.is_connected():
        raise ConnectionError(f"Failed to connect to Web3 provider at {rpc_url}")
    return w3


def submit_staged_routes(
    staged_routes: List[Dict[str, Any]],
    w3: Web3,
    private_key: str,
    chain_id: int,
    executor_address: str,
) -> List[Dict[str, Any]]:
    """
    Signs and broadcasts a list of staged routes.

    Returns a list of submission results, each containing the route and tx_hash.
    """
    if not staged_routes:
        return []

    account = w3.eth.account.from_key(private_key)
    nonce = w3.eth.get_transaction_count(account.address)
    gas_policy = get_gas_policy(w3)
    submissions = []

    for i, route in enumerate(staged_routes):
        try:
            tx_params = {
                "from": account.address,
                "to": Web3.to_checksum_address(executor_address),
                "nonce": nonce + i,
                "gas": route.get("gas_estimate", 750_000),
                "value": 0,
                "chainId": chain_id,
                "data": route["calldata"],
                **gas_policy,
            }

            signed_tx = w3.eth.account.sign_transaction(tx_params, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

            logger.info(f"Submitted Tx for opp_id {route['opp_id']}: {tx_hash.hex()}")
            submissions.append({"route": route, "tx_hash": tx_hash.hex()})

        except Exception as e:
            logger.error(f"Failed to submit transaction for opp_id {route['opp_id']}: {e}")
            submissions.append({"route": route, "tx_hash": None, "error": str(e)})

    return submissions


def wait_for_receipts(
    w3: Web3, submissions: List[Dict[str, Any]], timeout: int
) -> List[Dict[str, Any]]:
    """
    Waits for transaction receipts for a list of submissions.
    """
    results = []
    start_time = time.time()

    for sub in submissions:
        if sub.get("error") or not sub.get("tx_hash"):
            results.append({**sub, "receipt": None, "status": "failed_submission"})
            continue

        tx_hash = sub["tx_hash"]
        receipt = None
        status = "pending"
        try:
            logger.debug(f"Waiting for receipt for tx: {tx_hash} (timeout: {timeout}s)")
            receipt_raw = w3.eth.wait_for_transaction_receipt(
                sub["tx_hash"], timeout=timeout
            )
            receipt = json.loads(Web3.to_json(receipt_raw))
            status = "success" if receipt.get("status") == 1 else "reverted"
            logger.info(f"Receipt for {tx_hash}: status={status}")
        except TransactionNotFound:
            status = "not_found"
            logger.warning(f"Tx {tx_hash} not found after timeout.")
        except Exception as e:
            status = "timeout"
            logger.warning(f"Timeout or error waiting for receipt for {tx_hash}: {e}")

        results.append({**sub, "receipt": receipt, "status": status})

    return results