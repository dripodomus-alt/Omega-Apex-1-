#!/usr/bin/env python3
# ==============================================================================
# sync_adapter_env.py -- bytecode-checked local env sync from executor slots.
# ==============================================================================

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from web3 import Web3

from . import rpc_layer
from .adapter_registry import ADAPTER_FOR_SOURCE_ABI, ZERO_ADDRESS
from .config import ADAPTER_CONFIGURATION_TARGET, CHAIN_ID


SOURCE_ENV_KEYS = {
    0: "AAVE_V3_CAPITAL_ADAPTER",
    1: "BALANCER_VAULT_CAPITAL_ADAPTER",
    2: "V2_FLASH_SWAP_ADAPTER",
    3: "V3_FLASH_CALLBACK_ADAPTER",
}


def _write_env_values(values: dict[str, str], env_path: Path) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in values.items():
        if key not in seen:
            out.append(f"{key}={value}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def sync(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync deployed executor adapterForSource slots into .env")
    parser.add_argument("--rpc-url", default="", help="Read RPC URL")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--write", action="store_true", help="Write .env. Dry-run is default.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("sync_adapter_env=FAIL reason=rpc_connect_false")
        return 1
    if rpc_layer.w3.eth.chain_id != CHAIN_ID:
        print(f"sync_adapter_env=FAIL reason=chain_id_mismatch actual={rpc_layer.w3.eth.chain_id}")
        return 1
    if not ADAPTER_CONFIGURATION_TARGET:
        print("sync_adapter_env=FAIL reason=ADAPTER_CONFIGURATION_TARGET missing")
        return 1

    executor = rpc_layer.w3.eth.contract(
        address=Web3.to_checksum_address(ADAPTER_CONFIGURATION_TARGET),
        abi=ADAPTER_FOR_SOURCE_ABI,
    )
    updates: dict[str, str] = {}
    for source_id, env_key in SOURCE_ENV_KEYS.items():
        try:
            address = Web3.to_checksum_address(executor.functions.adapterForSource(source_id).call())
        except Exception as exc:
            print(f"slot={source_id} env={env_key} status=READ_FAILED detail={exc}")
            continue
        if address.lower() == ZERO_ADDRESS.lower():
            print(f"slot={source_id} env={env_key} status=UNSET")
            continue
        code = rpc_layer.w3.eth.get_code(address).hex()
        if code in ("", "0x"):
            print(f"slot={source_id} env={env_key} status=NO_BYTECODE address={address}")
            continue
        updates[env_key] = address
        print(f"slot={source_id} env={env_key} status=SYNCABLE address={address}")

    if not updates:
        print("sync_adapter_env=NOOP reason=no_deployed_bytecode_slots")
        return 0
    if not args.write:
        print(f"sync_adapter_env=DRY_RUN updates={updates}")
        return 0

    _write_env_values(updates, Path(args.env_path))
    print(f"sync_adapter_env=OK keys={list(updates.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(sync())
