#!/usr/bin/env python3
# ==============================================================================
# deploy_liquidation_executor.py -- guarded deploy utility for liquidation execution.
# ==============================================================================

from __future__ import annotations

import argparse
import json
from typing import Iterable

from web3 import Web3

from . import rpc_layer
from .config import (
    BROADCAST_RPC_URL,
    CHAIN_ID,
    CONFIRM_FLAG,
    EXEC_MODE,
    LIVE_FLAG,
    OWNER_ADDRESS,
    PRIVATE_KEY,
    REQUIRED_CONFIRM,
    _env,
)
from .deploy_adapters import _write_env_values
from .execution import wallet_address
from .paths import output_path


ARTIFACT = output_path("OmegaLiquidationExecutor.sol", "OmegaLiquidationExecutor.json")
ZERO_ADDRESS = "0x" + "00" * 20


def _tx_w3(send: bool = False) -> Web3:
    if send and BROADCAST_RPC_URL:
        provider = Web3(Web3.HTTPProvider(BROADCAST_RPC_URL, request_kwargs={"timeout": 20}))
        rpc_layer._inject_poa_middleware(provider)
        return provider
    if rpc_layer.w3 is None:
        raise RuntimeError("RPC not connected")
    return rpc_layer.w3


def _load_artifact() -> tuple[list, str]:
    if not ARTIFACT.exists():
        raise RuntimeError(f"artifact missing: {ARTIFACT}. Run `forge build` first.")
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    bytecode = artifact.get("bytecode", {}).get("object", "")
    if not bytecode:
        raise RuntimeError(f"artifact has no bytecode: {ARTIFACT}")
    return artifact["abi"], bytecode


def _send_allowed() -> tuple[bool, list[str]]:
    missing: list[str] = []
    if EXEC_MODE != "live":
        missing.append("EXECUTION_MODE=live")
    if LIVE_FLAG != "1":
        missing.append("LIVE_TRADING=1")
    if CONFIRM_FLAG != REQUIRED_CONFIRM:
        missing.append(f"CONFIRM_MAINNET_EXECUTION={REQUIRED_CONFIRM}")
    if not wallet_address():
        missing.append("EXECUTOR_PRIVATE_KEY valid")
    return not missing, missing


def _owner_arg(explicit_owner: str = "") -> str:
    owner = explicit_owner or wallet_address() or OWNER_ADDRESS
    if not owner or not Web3.is_address(owner):
        raise RuntimeError("owner must be provided with --owner or a valid EXECUTOR_PRIVATE_KEY/OWNER_ADDRESS")
    return Web3.to_checksum_address(owner)


def _adapter_arg(explicit_adapter: str = "") -> str:
    adapter = explicit_adapter or _env("AAVE_V3_LIQUIDATION_ADAPTER") or ZERO_ADDRESS
    if not Web3.is_address(adapter):
        raise RuntimeError("liquidation adapter must be a valid address or empty")
    return Web3.to_checksum_address(adapter)


def deploy(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy OmegaLiquidationExecutor")
    parser.add_argument("--rpc-url", default="", help="Read RPC URL")
    parser.add_argument("--owner", default="", help="Owner address override")
    parser.add_argument("--adapter", default="", help="Initial AAVE_V3_LIQUIDATION_ADAPTER address")
    parser.add_argument("--send", action="store_true", help="Broadcast deployment. Dry-run is default.")
    parser.add_argument("--write-env", action="store_true", help="Write LIQUIDATION_EXECUTOR_ADDRESS to .env after send")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("deploy_liquidation_executor=FAIL reason=rpc_connect_false")
        return 1
    w3 = _tx_w3(send=args.send)
    if w3.eth.chain_id != CHAIN_ID:
        print(f"deploy_liquidation_executor=FAIL reason=chain_id_mismatch actual={w3.eth.chain_id}")
        return 1

    try:
        owner = _owner_arg(args.owner)
        adapter = _adapter_arg(args.adapter)
        abi, bytecode = _load_artifact()
    except RuntimeError as exc:
        print(f"deploy_liquidation_executor=FAIL reason={exc}")
        return 1

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    constructor = contract.constructor(owner, adapter)
    print(
        f"contract=OmegaLiquidationExecutor owner={owner} initial_adapter={adapter} "
        f"bytecode_bytes={(len(bytecode.removeprefix('0x'))) // 2}"
    )

    if not args.send:
        data = constructor.data_in_transaction
        print(f"deploy_data selectorless_bytes={(len(data) - 2) // 2}")
        if args.write_env:
            print("write_env_plan key=LIQUIDATION_EXECUTOR_ADDRESS requires --send")
        print("deploy_liquidation_executor=DRY_RUN send=false")
        return 0

    send_ok, missing = _send_allowed()
    if not send_ok:
        print(f"deploy_liquidation_executor=BLOCKED reason=send_guards_missing detail={missing}")
        return 2

    signer = wallet_address()
    nonce = w3.eth.get_transaction_count(signer)
    built = constructor.build_transaction({
        "chainId": CHAIN_ID,
        "from": signer,
        "nonce": nonce,
        "value": 0,
    })
    gas_estimate = w3.eth.estimate_gas(built)
    built["gas"] = int(gas_estimate * 1.25)
    from .gas_oracle import eip1559_fee_params

    max_fee, priority_fee, gas_fee_source = eip1559_fee_params()
    built["maxFeePerGas"] = max_fee
    built["maxPriorityFeePerGas"] = priority_fee
    built["type"] = 2
    print(f"deploy_liquidation_executor_gas_source={gas_fee_source}")

    from eth_account import Account

    signed = Account.from_key(PRIVATE_KEY).sign_transaction(built)
    raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    tx_hash = w3.eth.send_raw_transaction(raw_tx).hex()
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        print(f"deploy_liquidation_executor=FAIL tx={tx_hash}")
        return 1

    address = Web3.to_checksum_address(receipt.contractAddress)
    code = w3.eth.get_code(address).hex()
    if code in ("", "0x"):
        print(f"deploy_liquidation_executor=FAIL reason=no_bytecode address={address}")
        return 1
    if args.write_env:
        _write_env_values({"LIQUIDATION_EXECUTOR_ADDRESS": address})
        print("write_env=OK keys=['LIQUIDATION_EXECUTOR_ADDRESS']")
    print(f"LIQUIDATION_EXECUTOR_ADDRESS={address}")
    print(f"deploy_liquidation_executor=SENT tx={tx_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(deploy())

