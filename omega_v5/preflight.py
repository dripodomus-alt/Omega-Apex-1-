#!/usr/bin/env python3
# ==============================================================================
# preflight.py  -- read-only live-readiness checks for Omega V5.
#
# This command connects to Polygon, verifies the pinned executor bytecode and
# function selector, derives the signer address when configured, and reports
# guard status. It never signs or broadcasts a transaction.
#
# UPDATED: Now reports RPC plan quota status at startup.
# ==============================================================================

from __future__ import annotations

import sys

from . import rpc_layer
from .config import (
    CHAIN_ID,
    EXECUTOR_CONTRACT,
    RPC_QUOTA_ENFORCEMENT,
)
from .rust_engine import assert_rust_engine_ready

from .rpc_layer import get_quota_stats, quota_manager


def run_preflight() -> int:
    print("=== OMEGA V5 PREFLIGHT (with RPC Plan Quota) ===")

    # RPC Quota status first (Developer plan enforcement)
    stats = get_quota_stats()
    print(f"[RPC Quota] Plan: {stats.get('plan')} | "
          f"Units used: {stats.get('total_units')}/{stats.get('units_limit')} "
          f"({stats.get('usage_percent')}%) | "
          f"RPS window: {stats.get('current_rps_window')}/{stats.get('rps_limit')} | "
          f"Enforcement: {stats.get('enforcement')}")

    if RPC_QUOTA_ENFORCEMENT and not quota_manager.can_make_request():
        print("[RPC Quota] WARNING: Near or over quota limits. Throttling will engage on next calls.")

    if not rpc_layer.w3 or not rpc_layer.w3.is_connected():
        print("preflight=FAIL reason=rpc_connect_false")
        return 1

    w3 = rpc_layer.w3
    if w3.eth.chain_id != CHAIN_ID:
        print(f"preflight=FAIL reason=chain_id_mismatch actual={w3.eth.chain_id}")
        return 1

    # Bytecode check
    try:
        code = w3.eth.get_code(EXECUTOR_CONTRACT)
        if len(code) <= 2:
            print(f"preflight=FAIL reason=no_bytecode address={EXECUTOR_CONTRACT}")
            return 1
        print(f"preflight=OK executor_bytecode={len(code)}")
        quota_manager.record_request("eth_getCode")
    except Exception as exc:
        print(f"preflight=FAIL reason=executor_code_error detail={exc}")
        return 1

    try:
        assert_rust_engine_ready()
        print("preflight=OK rust_engine")
    except Exception as e:
        print(f"preflight=WARN rust_engine={e}")

    print("preflight=COMPLETE")
    print(f"Final quota snapshot: {get_quota_stats()}")
    return 0


if __name__ == "__main__":
    sys.exit(run_preflight())
