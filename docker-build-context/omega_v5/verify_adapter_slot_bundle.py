#!/usr/bin/env python3
# ==============================================================================
# verify_adapter_slot_bundle.py -- pre-broadcast checks for signed adapter txs.
# ==============================================================================

from __future__ import annotations

import argparse
import json
from typing import Iterable

from eth_account import Account
from web3 import Web3

from . import rpc_layer
from .config import CHAIN_ID
from .paths import output_path, resolve_repo_relative


ZERO_ADDRESS = "0x" + "00" * 20
DEFAULT_BUNDLE = output_path("owner_signed_adapter_slot_txs.json")

EXECUTOR_ABI = [
    {
        "name": "owner",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "name": "adapterForSource",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "flashSource", "type": "uint8"}],
        "outputs": [{"name": "", "type": "address"}],
    },
]


def verify_bundle(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify signed adapter slot tx bundle before broadcast")
    parser.add_argument("--rpc-url", default="", help="Read RPC URL")
    parser.add_argument("--bundle", default=str(DEFAULT_BUNDLE), help="Signed bundle path")
    parser.add_argument("--allow-nonce-drift", action="store_true", help="Report but do not fail on nonce drift")
    args = parser.parse_args(list(argv) if argv is not None else None)

    bundle_path = resolve_repo_relative(args.bundle)
    if not bundle_path.exists():
        print(f"verify_adapter_slot_bundle=FAIL reason=bundle_missing path={bundle_path}")
        return 1
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("verify_adapter_slot_bundle=FAIL reason=rpc_connect_false")
        return 1
    if rpc_layer.w3.eth.chain_id != CHAIN_ID:
        print(f"verify_adapter_slot_bundle=FAIL reason=chain_id_mismatch actual={rpc_layer.w3.eth.chain_id}")
        return 1

    w3 = rpc_layer.w3
    signer = Web3.to_checksum_address(bundle["signer"])
    executor_addr = Web3.to_checksum_address(bundle["executor"])
    predicted_adapter = Web3.to_checksum_address(bundle["predicted_balancer_adapter"])
    nonce_start = int(bundle["nonce_start"])
    txs = bundle.get("transactions", [])
    if len(txs) < 2:
        print(f"verify_adapter_slot_bundle=FAIL reason=expected_at_least_two_transactions actual={len(txs)}")
        return 1

    recovered = []
    for tx in txs:
        raw = tx.get("raw_transaction", "")
        try:
            recovered.append(Web3.to_checksum_address(Account.recover_transaction(raw)))
        except Exception as exc:
            print(f"verify_adapter_slot_bundle=FAIL reason=recover_failed tx={tx.get('name')} detail={exc}")
            return 1
    if any(addr.lower() != signer.lower() for addr in recovered):
        print(f"verify_adapter_slot_bundle=FAIL reason=raw_tx_signer_mismatch recovered={recovered} signer={signer}")
        return 1
    expected_nonces = list(range(nonce_start, nonce_start + len(txs)))
    actual_nonces = [int(tx.get("nonce", -1)) for tx in txs]
    if actual_nonces != expected_nonces:
        print(
            "verify_adapter_slot_bundle=FAIL reason=nonce_sequence_mismatch "
            f"expected={expected_nonces} actual={actual_nonces}"
        )
        return 1
    if txs[0].get("to") is not None:
        print("verify_adapter_slot_bundle=FAIL reason=first_tx_is_not_deploy")
        return 1
    if txs[-1].get("name") != "configure_adapter_for_source_1":
        print("verify_adapter_slot_bundle=FAIL reason=last_tx_is_not_adapter_slot_config")
        return 1

    executor = w3.eth.contract(address=executor_addr, abi=EXECUTOR_ABI)
    owner = Web3.to_checksum_address(executor.functions.owner().call())
    if owner.lower() != signer.lower():
        print(f"verify_adapter_slot_bundle=FAIL reason=owner_mismatch owner={owner} signer={signer}")
        return 1

    latest_nonce = w3.eth.get_transaction_count(signer, "latest")
    pending_nonce = w3.eth.get_transaction_count(signer, "pending")
    nonce_ok = latest_nonce == nonce_start and pending_nonce == nonce_start
    if not nonce_ok and not args.allow_nonce_drift:
        print(
            "verify_adapter_slot_bundle=FAIL reason=nonce_drift "
            f"expected={nonce_start} latest={latest_nonce} pending={pending_nonce}"
        )
        return 1

    current_slot = Web3.to_checksum_address(executor.functions.adapterForSource(1).call())
    if current_slot.lower() != ZERO_ADDRESS.lower():
        print(f"verify_adapter_slot_bundle=FAIL reason=slot_1_already_configured current={current_slot}")
        return 1

    predicted_code = w3.eth.get_code(predicted_adapter).hex()
    if predicted_code not in ("", "0x"):
        print(f"verify_adapter_slot_bundle=FAIL reason=predicted_adapter_already_has_code address={predicted_adapter}")
        return 1

    current_gas = w3.eth.gas_price
    min_max_fee = min(int(tx.get("maxFeePerGas", 0)) for tx in txs)
    if min_max_fee < current_gas:
        print(
            "verify_adapter_slot_bundle=FAIL reason=max_fee_below_current_gas "
            f"minMaxFee={min_max_fee} currentGas={current_gas}"
        )
        return 1

    print("verify_adapter_slot_bundle=PASS")
    print(f"signer={signer}")
    print(f"executor={executor_addr}")
    print(f"predicted_balancer_adapter={predicted_adapter}")
    print(f"nonce_start={nonce_start} latest_nonce={latest_nonce} pending_nonce={pending_nonce}")
    print(f"slot_1={current_slot}")
    print("broadcast_ready=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(verify_bundle())
