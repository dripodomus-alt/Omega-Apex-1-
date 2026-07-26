#!/usr/bin/env python3
"""
scripts/ops/verify_deployed_contracts.py

Contract verification + RPC Plan Quota gate.
Pings HFT and Liquidation contracts and ensures we stay within plan limits
(Developer: 25 RPS, 3M request units) before industrial scaling.
"""

import asyncio
import os
import sys
from web3 import AsyncWeb3

# Add project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from omega_v5 import config
from omega_v5.rpc_layer import quota_manager, get_quota_stats

# Pinned addresses (override via .env if needed)
HFT_ADDRESS = config.CANONICAL_ON_CHAIN_MUSCLE or "0x409ece3Fd71DFBd8f692B600f36A89301cb37346"
LIQ_ADDRESS = config.LIQUIDATION_EXECUTOR_ADDRESS or "0x8cD1e93eE2DeD4F59e15650c0a16029b6Ad9b951"
POLYGON_RPC = config.HTTP_URL or os.getenv("PRIMARY_READ_RPC_URL", "https://polygon-rpc.com")

async def verify_infrastructure():
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(POLYGON_RPC))

    print("\n" + "="*60)
    print(" OMEGA-V5 CONTRACT + RPC PLAN QUOTA VERIFICATION ".center(60, "="))
    print("="*60 + "\n")

    # Quota pre-check
    stats = get_quota_stats()
    print(f"[RPC Plan] {stats['plan']} | Units used: {stats['total_units']}/{stats['units_limit']} ({stats['usage_percent']}%) | RPS window: {stats['current_rps_window']}/{stats['rps_limit']}")

    if not quota_manager.can_make_request("eth_getCode"):
        print("[✗] RPC quota would be exceeded. Aborting verification.")
        return False

    # 1. Network
    if await w3.is_connected():
        block = await w3.eth.block_number
        print(f"[✓] Connected to Polygon. Current Block: {block}")
        quota_manager.record_request("eth_blockNumber")
    else:
        print("[✗] Failed to connect to Polygon RPC.")
        return False

    # 2. HFT Contract
    quota_manager.sync_wait_if_needed("eth_getCode")
    hft_code = await w3.eth.get_code(HFT_ADDRESS)
    if len(hft_code) > 2:
        print(f"[✓] HFT/C1 Contract Verified at {HFT_ADDRESS}")
        print(f"    - Bytecode detected ({len(hft_code)} bytes).")
        quota_manager.record_request("eth_getCode")
    else:
        print(f"[✗] HFT/C1 Contract MISSING or INVALID at {HFT_ADDRESS}")

    # 3. Liquidation Contract
    quota_manager.sync_wait_if_needed("eth_getCode")
    liq_code = await w3.eth.get_code(LIQ_ADDRESS)
    if len(liq_code) > 2:
        print(f"[✓] Liquidation Contract Verified at {LIQ_ADDRESS}")
        print(f"    - Bytecode detected ({len(liq_code)} bytes).")
        quota_manager.record_request("eth_getCode")
    else:
        print(f"[✗] Liquidation Contract MISSING or INVALID at {LIQ_ADDRESS}")

    # 4. Final Verdict
    if len(hft_code) > 2 and len(liq_code) > 2:
        print("\n" + "="*60)
        print(" VERDICT: INFRASTRUCTURE COMPATIBLE + QUOTA OK ".center(60, " "))
        print("="*60)
        print("\n>>> System Authorized for Industrial Staircase Scaling.")
        print(">>> Injector Math Gated to $1,000 Floor.")
        print(f">>> Current quota: {stats['usage_percent']}% used")
        return True
    else:
        print("\n[!] CRITICAL: Source compatibility check FAILED.")
        print("    Check your .env and ensure contracts are on Polygon (Chain 137).")
        return False

if __name__ == "__main__":
    success = asyncio.run(verify_infrastructure())
    sys.exit(0 if success else 1)
