#!/usr/bin/env python3
# ==============================================================================
# fork_rpc.py -- resolves the best available RPC URL for Anvil fork creation.
#
# It checks these sources in order:
# 1. FORK_UPSTREAM_RPC_URL environment variable
# 2. FORK_RPC_URL environment variable
# 3. A healthy, live-probed RPC from the transport layer's read lanes
# ==============================================================================

import argparse
import os
import sys
from typing import Any

# Add project root to path to allow direct script execution
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from web3 import Web3
from omega_v5.config import CHAIN_ID
from omega_v5.transport_lanes import transport_probe


def _is_healthy(url: str) -> bool:
    """Checks if an RPC URL is healthy and matches the target chain ID."""
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 5}))
        return w3.is_connected() and w3.eth.chain_id == CHAIN_ID
    except Exception:
        return False


def _get_healthy_read_lane_rpc() -> str | None:
    """Probes transport lanes to find a healthy read RPC."""
    try:
        probe_results = transport_probe(
            lanes=["read", "exact_c1_eth_call"],
            max_results_per_lane=1,
            force_probe=True,
        )
        for lane_results in probe_results.values():
            for result in lane_results:
                if result.get("ok"):
                    url = result.get("url")
                    if url and _is_healthy(url):
                        return url
    except Exception:
        return None
    return None


def resolve_fork_upstream(*, validate: bool = False) -> tuple[str | None, str]:
    """
    Resolves the best available RPC URL for forking.

    Returns a tuple of (url, reason).
    """
    # 1. Explicit upstream URL
    fork_upstream = os.environ.get("FORK_UPSTREAM_RPC_URL")
    if fork_upstream and (not validate or _is_healthy(fork_upstream)):
        return fork_upstream, "FORK_UPSTREAM_RPC_URL"

    # 2. Explicit fork URL (often the local Anvil instance itself, but can be remote)
    fork_rpc = os.environ.get("FORK_RPC_URL")
    if fork_rpc and (not validate or _is_healthy(fork_rpc)):
        return fork_rpc, "FORK_RPC_URL"

    # 3. Probe transport lanes for a healthy read RPC
    healthy_read_rpc = _get_healthy_read_lane_rpc()
    if healthy_read_rpc:
        return healthy_read_rpc, "transport_read_lane"

    # 4. Fallback to primary read RPC from config
    primary_read = os.environ.get("PRIMARY_READ_RPC_URL")
    if primary_read and (not validate or _is_healthy(primary_read)):
        return primary_read, "PRIMARY_READ_RPC_URL"

    return None, "no_healthy_rpc_found"


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Resolve and print the best fork RPC URL.")
    parser.add_argument(
        "--print-url",
        action="store_true",
        help="Print the resolved URL to stdout.",
    )
    args = parser.parse_args()

    url, reason = resolve_fork_upstream(validate=True)

    if args.print_url:
        if url:
            print(url)
            return 0
        return 1

    print(f"Resolved Fork RPC URL: {url or 'Not Found'}")
    print(f"Source: {reason}")
    return 0 if url else 1


if __name__ == "__main__":
    sys.exit(main())