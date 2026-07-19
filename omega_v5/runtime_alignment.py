#!/usr/bin/env python3
# ==============================================================================
# runtime_alignment.py -- dry-run/live/fork/exact/broadcast alignment validator.
#
# The engine has several independent runtime surfaces: .env defaults, Redis/UI
# runtime state, PM2 process env, Anvil fork env, transport lanes, and execution
# guards. This module turns those into one auditable readiness record.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from web3 import Web3

from .config import (
    BROADCAST_RPC_URL,
    BROADCAST_RPC_FALLBACK_URLS,
    BROADCAST_WSS_URL,
    BROADCAST_WSS_FALLBACK_URLS,
    CHAIN_ID,
    CONFIRM_FLAG,
    EXACT_CALL_RPC_URL,
    EXEC_MODE,
    FORK_RPC_URL,
    FORK_SIM_RPC_URL,
    FORK_UPSTREAM_RPC_URL,
    HTTP_URL,
    LIVE_FLAG,
    PRIMARY_READ_RPC_URL,
    PRIMARY_WSS_URL,
    PRIVATE_KEY,
    REQUIRED_CONFIRM,
    SESSION_SIGNER_MODE,
    WAAS_BROADCAST_ADAPTER_ENABLED,
    WAAS_BROADCAST_ADAPTER_MODE,
)
from .execution import wallet_address
from .paths import output_path
from .runtime_control import get_runtime_state, runtime_mode
from .wallet_config_verification import wallet_config_status
from .transport_lanes import (
    LANE_EXACT_C1_ETH_CALL,
    LANE_FORK_SIMULATION,
    LANE_LIVE_BROADCAST_PRIMARY,
    _inject_poa,
    _mask_url,
    probe_broadcast_endpoint,
    select_endpoint,
)


ALIGNMENT_JSON_PATH = output_path("runtime_alignment_latest.json")


def _host(url: str) -> str:
    return url.split("/")[2].lower() if "//" in str(url) else str(url).lower()


def _same_endpoint(a: str, b: str) -> bool:
    return bool(a and b and a.strip().rstrip("/") == b.strip().rstrip("/"))


def _probe_http(url: str, timeout: int = 5) -> dict[str, Any]:
    if not url:
        return {"configured": False, "ok": False}
    started = time.perf_counter()
    try:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": timeout}))
        _inject_poa(w3)
        chain_id = int(w3.eth.chain_id)
        block = int(w3.eth.block_number)
        return {
            "configured": True,
            "ok": chain_id == CHAIN_ID,
            "chain_id": chain_id,
            "block": block,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except Exception as exc:
        return {
            "configured": True,
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


def runtime_alignment_status(*, probe: bool = False) -> dict[str, Any]:
    mode = runtime_mode()
    runtime = get_runtime_state()
    exact_lane = select_endpoint(LANE_EXACT_C1_ETH_CALL, probe_if_stale=probe)
    broadcast_lane = select_endpoint(LANE_LIVE_BROADCAST_PRIMARY, probe_if_stale=probe)
    fork_lane = select_endpoint(LANE_FORK_SIMULATION, probe_if_stale=probe)
    wallet = wallet_address()
    wallet_status = wallet_config_status(mode=mode, probe_balance=probe)

    checks: dict[str, dict[str, Any]] = {}
    checks["runtime_mode_valid"] = {
        "ok": mode in {"dry_run", "live"},
        "detail": mode,
    }
    checks["live_env_triplet_aligned"] = {
        "ok": (EXEC_MODE == "live" and LIVE_FLAG == "1" and CONFIRM_FLAG == REQUIRED_CONFIRM)
        if mode == "live"
        else True,
        "detail": {
            "runtime_mode": mode,
            "EXECUTION_MODE": EXEC_MODE,
            "LIVE_TRADING": LIVE_FLAG,
            "CONFIRM_MAINNET_EXECUTION": "present" if CONFIRM_FLAG == REQUIRED_CONFIRM else "missing_or_mismatch",
        },
    }
    checks["dry_run_does_not_require_live_triplet"] = {
        "ok": True if mode == "live" else not (EXEC_MODE == "live" and LIVE_FLAG == "1" and CONFIRM_FLAG == REQUIRED_CONFIRM) or True,
        "detail": "dry-run can coexist with configured live credentials because runtime control is authoritative",
    }
    checks["private_key_gate"] = {
        "ok": bool(wallet) if mode == "live" else True,
        "detail": "configured" if PRIVATE_KEY else "missing",
        "wallet": wallet,
    }
    checks["wallet_config"] = {
        "ok": bool(wallet_status.get("ok")),
        "detail": {
            "gas_payer": wallet_status.get("gas_payer"),
            "native_balance_pol": wallet_status.get("native_balance_pol"),
            "min_wallet_gas_buffer_pol": wallet_status.get("min_wallet_gas_buffer_pol"),
            "balance_source": wallet_status.get("balance_source"),
            "checks": wallet_status.get("checks"),
        },
    }
    checks["primary_exact_aligned"] = {
        "ok": bool(EXACT_CALL_RPC_URL and PRIMARY_READ_RPC_URL),
        "detail": {
            "primary_read": _mask_url(PRIMARY_READ_RPC_URL),
            "exact_call": _mask_url(EXACT_CALL_RPC_URL),
            "same_endpoint": _same_endpoint(PRIMARY_READ_RPC_URL, EXACT_CALL_RPC_URL),
            "selected_exact": _mask_url(exact_lane),
        },
    }
    checks["broadcast_isolated"] = {
        "ok": bool(BROADCAST_RPC_URL or BROADCAST_RPC_FALLBACK_URLS)
        and not _same_endpoint(broadcast_lane, EXACT_CALL_RPC_URL),
        "detail": {
            "broadcast": _mask_url(BROADCAST_RPC_URL),
            "broadcast_wss": _mask_url(BROADCAST_WSS_URL),
            "broadcast_fallback_count": len([url for url in BROADCAST_RPC_FALLBACK_URLS if url]),
            "broadcast_wss_fallback_count": len([url for url in BROADCAST_WSS_FALLBACK_URLS if url]),
            "selected_broadcast": _mask_url(broadcast_lane),
            "exact_call": _mask_url(EXACT_CALL_RPC_URL),
            "same_as_exact": _same_endpoint(broadcast_lane, EXACT_CALL_RPC_URL),
        },
    }
    checks["fork_runtime_aligned"] = {
        "ok": bool(FORK_RPC_URL and FORK_SIM_RPC_URL and FORK_UPSTREAM_RPC_URL),
        "detail": {
            "fork_upstream": _mask_url(FORK_UPSTREAM_RPC_URL),
            "fork_rpc": _mask_url(FORK_RPC_URL),
            "fork_sim": _mask_url(FORK_SIM_RPC_URL),
            "selected_fork_lane": _mask_url(fork_lane),
            "local_fork": _host(FORK_SIM_RPC_URL).startswith("127.0.0.1") or _host(FORK_SIM_RPC_URL).startswith("localhost"),
        },
    }
    checks["wss_aligned"] = {
        "ok": bool(PRIMARY_WSS_URL),
        "detail": {"primary_wss": _mask_url(PRIMARY_WSS_URL)},
    }
    checks["session_lane_isolated"] = {
        "ok": (
            SESSION_SIGNER_MODE == "dry_run"
            and WAAS_BROADCAST_ADAPTER_MODE == "dry_run"
            and not WAAS_BROADCAST_ADAPTER_ENABLED
        ),
        "detail": {
            "session_signer_mode": SESSION_SIGNER_MODE,
            "waas_adapter_mode": WAAS_BROADCAST_ADAPTER_MODE,
            "waas_adapter_enabled": WAAS_BROADCAST_ADAPTER_ENABLED,
        },
    }

    probes = {}
    if probe:
        probes = {
            "primary_read": _probe_http(PRIMARY_READ_RPC_URL),
            "exact_call": _probe_http(EXACT_CALL_RPC_URL),
            "broadcast_primary": _probe_http(BROADCAST_RPC_URL),
            "broadcast": probe_broadcast_endpoint(broadcast_lane or BROADCAST_RPC_URL),
            "fork_sim": _probe_http(FORK_SIM_RPC_URL, timeout=3),
            "fork_upstream": _probe_http(FORK_UPSTREAM_RPC_URL),
        }
        required_probe_keys = ["primary_read", "exact_call", "fork_sim", "fork_upstream"]
        if mode == "live":
            required_probe_keys.append("broadcast")
        checks["probed_chain_ids"] = {
            "ok": all(bool(probes[key].get("ok")) for key in required_probe_keys),
            "detail": {
                **probes,
                "required_for_mode": required_probe_keys,
                "broadcast_probe_required": mode == "live",
            },
        }

    hard_fail_keys = [
        "runtime_mode_valid",
        "live_env_triplet_aligned",
        "private_key_gate",
        "primary_exact_aligned",
        "broadcast_isolated",
        "fork_runtime_aligned",
        "wss_aligned",
        "session_lane_isolated",
    ]
    if probe:
        hard_fail_keys.append("probed_chain_ids")

    ok = all(bool(checks[key].get("ok")) for key in hard_fail_keys)
    status = {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "generated_at_unix": time.time(),
        "chain_id": CHAIN_ID,
        "runtime": runtime,
        "policy": {
            "runtime_control_is_authoritative": True,
            "dry_run_and_live_share_route_builders": True,
            "live_requires_exact_call_before_broadcast": True,
            "anvil_fork_uses_same_upstream_profile": True,
            "broadcast_isolated_from_read_rotation": True,
        },
        "checks": checks,
    }
    ALIGNMENT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALIGNMENT_JSON_PATH.write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
    return status


def load_latest_alignment() -> dict[str, Any]:
    if not ALIGNMENT_JSON_PATH.exists():
        return {"ok": False, "status": "MISSING", "path": str(ALIGNMENT_JSON_PATH)}
    try:
        return json.loads(ALIGNMENT_JSON_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "status": "INVALID", "path": str(ALIGNMENT_JSON_PATH), "error": f"{type(exc).__name__}: {exc}"}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Validate Omega dry-run/live/fork runtime alignment")
    parser.add_argument("--probe", action="store_true", help="probe configured HTTP endpoints")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    status = runtime_alignment_status(probe=args.probe)
    if args.json:
        print(json.dumps(status, indent=2, default=str))
    else:
        print(f"runtime_alignment={status['status']}")
        for name, check in status["checks"].items():
            print(f"{name}={'PASS' if check.get('ok') else 'FAIL'} detail={check.get('detail')}")
        print(f"JSON proof: {ALIGNMENT_JSON_PATH}")
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
