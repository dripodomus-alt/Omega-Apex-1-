#!/usr/bin/env python3
# ==============================================================================
# preflight.py  -- read-only live-readiness checks for Omega V5.
#
# This command connects to Polygon, verifies the pinned executor bytecode and
# function selector, derives the signer address when configured, and reports
# guard status. It never signs or broadcasts a transaction.
# ==============================================================================

from __future__ import annotations

from . import rpc_layer
from .config import (
    BROADCAST_RPC_URL,
    BROADCAST_WSS_URL,
    CHAIN_ID,
    DODO_RPC_PROVIDER_URL,
    DODO_RPC_PROXY_URL,
    ENABLE_INDEXER_STATE_READS,
    ENABLE_POLYGON_TOKEN_LIST_DISCOVERY,
    EXECUTOR_CONTRACT,
    FLASHBOTS_RELAY_URL,
    TITAN_MEV_US_WEST,
)
from .fork_rpc import resolve_fork_upstream
from .redis_cache import status as redis_status
from .rust_engine import assert_rust_engine_ready
from .transport_lanes import transport_status
from .execution import (
    EXECUTE_FLASH_ARB_SELECTOR,
    EXECUTE_FLASH_ARB_SIGNATURE,
    execution_armed,
    execution_guard_status,
    executor_owner,
    executor_code_status,
    simulation_from_address,
    wallet_address,
)


def _probe_broadcast_rpc() -> tuple[bool, str]:
    if not BROADCAST_RPC_URL:
        return False, "not configured"
    try:
        from web3 import Web3
        probe = Web3(Web3.HTTPProvider(BROADCAST_RPC_URL, request_kwargs={"timeout": 10}))
        chain_id = probe.eth.chain_id
        block = probe.eth.block_number
        if chain_id != CHAIN_ID:
            return False, f"wrong chain_id={chain_id}"
        return True, f"chain_id={chain_id} block={block}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    print("Omega V5 preflight: read-only Polygon execution readiness")
    print(f"chain_id={CHAIN_ID}")
    print(f"executor={EXECUTOR_CONTRACT or 'NOT SET'}")
    print(f"schema={EXECUTE_FLASH_ARB_SIGNATURE}")
    print(f"selector={EXECUTE_FLASH_ARB_SELECTOR}")
    print(f"broadcast_rpc={'SET' if BROADCAST_RPC_URL else 'NOT SET'}")
    print(f"broadcast_wss={'SET' if BROADCAST_WSS_URL else 'NOT SET'}")
    print(f"flashbots_relay={'SET' if FLASHBOTS_RELAY_URL else 'NOT SET'}")
    print(f"titan_mev_us_west={'SET' if TITAN_MEV_US_WEST else 'NOT SET'}")
    print(f"dodo_rpc_provider={'SET' if DODO_RPC_PROVIDER_URL else 'NOT SET'}")
    print(f"dodo_rpc_proxy={'SET' if DODO_RPC_PROXY_URL else 'NOT SET'}")
    print(f"polygon_token_list_discovery={ENABLE_POLYGON_TOKEN_LIST_DISCOVERY}")
    print(f"indexer_state_reads={ENABLE_INDEXER_STATE_READS}")
    try:
        print(f"rust_engine_required=True binary={assert_rust_engine_ready()}")
    except Exception as exc:
        print(f"rust_engine_required=True ready=False error={type(exc).__name__}: {exc}")
    redis_ok, redis_detail = redis_status()
    print(f"redis_cache_ok={redis_ok} detail={redis_detail}")
    dodo_count = len(rpc_layer.dodo_provider_endpoints(CHAIN_ID))
    print(f"dodo_provider_polygon_endpoints={dodo_count}")
    lane_status = transport_status()
    print(f"transport_lanes_enabled={lane_status['enabled']}")
    print(f"transport_lane_count={lane_status['lane_count']}")
    print(f"transport_redis_ok={lane_status['redis_ok']} detail={lane_status['redis_detail']}")
    for lane_name, endpoint in lane_status["selected_endpoints"].items():
        print(f"transport_lane {lane_name}: {endpoint or 'NO_ENDPOINT_SELECTED'}")
    fork_url, fork_detail = resolve_fork_upstream(validate=True)
    print(f"fork_upstream_ok={bool(fork_url)} detail={fork_detail}")
    broadcast_ok, broadcast_detail = _probe_broadcast_rpc()
    print(f"broadcast_rpc_ok={broadcast_ok} detail={broadcast_detail}")

    rpc_layer.connect()
    print(f"rpc_live={rpc_layer.RPC_LIVE}")
    print(f"block={rpc_layer.BLOCK}")
    rpc_layer.hydrate_polygon_token_list_candidates()
    print(f"polygon_token_list_stats={rpc_layer.POLYGON_TOKEN_LIST_DISCOVERY_STATS}")
    if ENABLE_INDEXER_STATE_READS:
        try:
            from .indexer_state import indexer_status

            print(f"indexer_status={indexer_status()}")
        except Exception as exc:
            print(f"indexer_status={{'healthy': False, 'error': '{type(exc).__name__}: {exc}'}}")

    ok, detail = executor_code_status()
    print(f"executor_code_ok={ok} detail={detail}")
    owner = executor_owner()
    print(f"executor_owner={owner or 'UNKNOWN'}")
    print(f"simulation_from={simulation_from_address() or 'NOT SET'}")

    wallet = wallet_address()
    print(f"wallet={'SET ' + wallet if wallet else 'NOT SET'}")

    guards = execution_guard_status()
    for name, value in guards.items():
        print(f"guard {name}: {value}")

    print(f"live_execution_armed={execution_armed()}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
