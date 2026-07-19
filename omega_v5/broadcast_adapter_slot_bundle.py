#!/usr/bin/env python3
# ==============================================================================
# broadcast_adapter_slot_bundle.py -- guarded raw bundle broadcaster.
# ==============================================================================

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from web3 import Web3

from . import rpc_layer
from .config import (
    BROADCAST_RPC_URL,
    CHAIN_ID,
    CONFIRM_FLAG,
    EXEC_MODE,
    LIVE_FLAG,
    REQUIRED_CONFIRM,
)
from .sync_adapter_env import sync as sync_adapter_env
from .verify_adapter_slot_bundle import DEFAULT_BUNDLE, verify_bundle


def _send_allowed() -> tuple[bool, list[str]]:
    missing: list[str] = []
    if EXEC_MODE != "live":
        missing.append("EXECUTION_MODE=live")
    if LIVE_FLAG != "1":
        missing.append("LIVE_TRADING=1")
    if CONFIRM_FLAG != REQUIRED_CONFIRM:
        missing.append(f"CONFIRM_MAINNET_EXECUTION={REQUIRED_CONFIRM}")
    if not BROADCAST_RPC_URL:
        missing.append("BROADCAST_RPC_URL")
    return not missing, missing


def broadcast(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Broadcast owner-signed adapter slot bundle")
    parser.add_argument("--rpc-url", default="", help="Read RPC URL for prechecks")
    parser.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    parser.add_argument("--write-env", action="store_true", help="Sync .env after successful broadcast")
    args = parser.parse_args(list(argv) if argv is not None else None)

    ok, missing = _send_allowed()
    if not ok:
        print(f"broadcast_adapter_slot_bundle=BLOCKED reason=send_guards_missing detail={missing}")
        return 2

    verify_args = ["--bundle", args.bundle]
    if args.rpc_url:
        verify_args.extend(["--rpc-url", args.rpc_url])
    verify_code = verify_bundle(verify_args)
    if verify_code != 0:
        print("broadcast_adapter_slot_bundle=FAIL reason=bundle_verification_failed")
        return verify_code

    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    w3 = Web3(Web3.HTTPProvider(BROADCAST_RPC_URL, request_kwargs={"timeout": 30}))
    if w3.eth.chain_id != CHAIN_ID:
        print(f"broadcast_adapter_slot_bundle=FAIL reason=chain_id_mismatch actual={w3.eth.chain_id}")
        return 1

    receipts = []
    for tx in bundle["transactions"]:
        raw = tx["raw_transaction"]
        tx_hash = w3.eth.send_raw_transaction(raw).hex()
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
        print(f"broadcasted name={tx['name']} nonce={tx['nonce']} tx={tx_hash} status={receipt.status}")
        if receipt.status != 1:
            print(f"broadcast_adapter_slot_bundle=FAIL tx={tx_hash}")
            return 1
        receipts.append(tx_hash)

    print(f"broadcast_adapter_slot_bundle=SENT count={len(receipts)}")
    if args.write_env:
        sync_args = ["--write"]
        if args.rpc_url:
            sync_args.extend(["--rpc-url", args.rpc_url])
        sync_adapter_env(sync_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(broadcast())
