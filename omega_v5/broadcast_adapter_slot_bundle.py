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
from .execution import revalidate_profitability_at_broadcast


def _send_allowed() -> tuple[bool, list[str]]:
    missing: list[str] = []
    if EXEC_MODE != "live":
        missing.append("EXECUTION_MODE=live")
    if LIVE_FLAG != "1":
        missing.append("LIVE_TRADING=1")
    if CONFIRM_FLAG != REQUIRED_CONFIRM:
        missing.append(f"CONFIRM_MAINNET_EXECUTION={REQUIRED_CONFIRM}")
    return len(missing) == 0, missing


def broadcast_with_revalidate(opportunities: Iterable[dict], current_pools: dict = None) -> list[str]:
    """
    Broadcast helper that runs the new re-profitability gate for simultaneous
    C1/C2/Liq families before allowing any submission.
    """
    current_pools = current_pools or {}
    allowed, blockers = _send_allowed()
    if not allowed:
        print("Broadcast blocked:", blockers)
        return []

    sent = []
    for opp in opportunities:
        # Convert to LiveOpportunity-like if needed (simplified)
        if not revalidate_profitability_at_broadcast(opp, current_pools):
            continue
        # Real broadcast would happen here
        sent.append(str(opp.get("path", "unknown")))
    return sent


def main():
    print("broadcast_adapter_slot_bundle: guards + revalidate at broadcast active")


if __name__ == "__main__":
    main()
