#!/usr/bin/env python3
# ==============================================================================
# configure_adapters.py -- owner-safe configureAdapter transaction utility.
# ==============================================================================

from __future__ import annotations

import argparse
from decimal import Decimal
from typing import Iterable

from web3 import Web3

from . import rpc_layer
from .adapter_registry import (
    FLASH_SOURCE_ENV_KEYS,
    FLASH_SOURCE_NAMES,
    ZERO_ADDRESS,
    FlashSourceId,
    configured_adapters,
)
from .config import (
    ADAPTER_CONFIGURATION_TARGET,
    BROADCAST_RPC_URL,
    CHAIN_ID,
    CONFIRM_FLAG,
    EXEC_MODE,
    LIVE_FLAG,
    PRIVATE_KEY,
    REQUIRED_CONFIRM,
)
from .contract_deployments import resolved_deployments
from .execution import wallet_address


ABI_CONFIGURE_ADAPTER = [
    {
        "name": "configureAdapter",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "flashSource", "type": "uint8"},
            {"name": "adapter", "type": "address"},
        ],
        "outputs": [],
    },
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


def _tx_w3(send: bool = False) -> Web3:
    url = BROADCAST_RPC_URL or ""
    if send and url:
        provider = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 15}))
        rpc_layer._inject_poa_middleware(provider)
        return provider
    if rpc_layer.w3 is None:
        raise RuntimeError("RPC not connected")
    return rpc_layer.w3


def _known_public_infra() -> dict[str, str]:
    return {
        deployment.address.lower(): f"{deployment.env_key}:{deployment.role}"
        for deployment in resolved_deployments().values()
    }


def _require_contract_code(w3: Web3, address: str) -> None:
    code = w3.eth.get_code(Web3.to_checksum_address(address)).hex()
    if code in ("", "0x"):
        raise RuntimeError(f"adapter has no bytecode: {address}")


def _live_send_allowed(owner: str) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if EXEC_MODE != "live":
        missing.append("EXECUTION_MODE=live")
    if LIVE_FLAG != "1":
        missing.append("LIVE_TRADING=1")
    if CONFIRM_FLAG != REQUIRED_CONFIRM:
        missing.append(f"CONFIRM_MAINNET_EXECUTION={REQUIRED_CONFIRM}")
    signer = wallet_address()
    if not signer:
        missing.append("EXECUTOR_PRIVATE_KEY valid")
    elif signer.lower() != owner.lower():
        missing.append(f"owner signer mismatch wallet={signer} owner={owner}")
    return not missing, missing


def _configured_source_items(selected: set[int] | None = None) -> list[tuple[FlashSourceId, str]]:
    adapters = configured_adapters()
    items: list[tuple[FlashSourceId, str]] = []
    for source_id, env_key in FLASH_SOURCE_ENV_KEYS.items():
        if selected is not None and int(source_id) not in selected:
            continue
        address = adapters.get(env_key, "")
        if address:
            items.append((source_id, address))
    return items


def configure(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or send Omega configureAdapter owner txs")
    parser.add_argument("--rpc-url", default="", help="Read RPC URL")
    parser.add_argument("--source", type=int, action="append", choices=[0, 1, 2, 3], help="Only configure this source id")
    parser.add_argument("--send", action="store_true", help="Broadcast transactions. Dry-run is default.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not ADAPTER_CONFIGURATION_TARGET:
        print("configure_adapters=FAIL reason=ADAPTER_CONFIGURATION_TARGET missing")
        return 1
    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("configure_adapters=FAIL reason=rpc_connect_false")
        return 1
    if rpc_layer.w3.eth.chain_id != CHAIN_ID:
        print(f"configure_adapters=FAIL reason=chain_id_mismatch actual={rpc_layer.w3.eth.chain_id}")
        return 1

    w3 = _tx_w3(send=args.send)
    target = Web3.to_checksum_address(ADAPTER_CONFIGURATION_TARGET)
    contract = w3.eth.contract(address=target, abi=ABI_CONFIGURE_ADAPTER)
    owner = contract.functions.owner().call()
    print(f"executor={target}")
    print(f"owner={owner}")
    print("configure_selector=0x6eb76c99")

    public_infra = _known_public_infra()
    selected = set(args.source) if args.source else None
    items = _configured_source_items(selected)
    if not items:
        print("configure_adapters=BLOCKED reason=no source adapter env vars configured")
        return 2

    send_ok, missing = _live_send_allowed(owner)
    if args.send and not send_ok:
        print(f"configure_adapters=BLOCKED reason=send_guards_missing detail={missing}")
        return 2

    signer = wallet_address()
    nonce = w3.eth.get_transaction_count(signer) if args.send else 0
    from .gas_oracle import eip1559_fee_params

    max_fee, priority_fee, gas_fee_source = eip1559_fee_params()
    print(f"configure_adapters_gas_source={gas_fee_source}")
    tx_hashes: list[str] = []

    for source_id, adapter in items:
        adapter = Web3.to_checksum_address(adapter)
        if adapter.lower() == ZERO_ADDRESS.lower():
            print(f"source={int(source_id)} blocked=zero_adapter")
            return 2
        if adapter.lower() in public_infra:
            print(
                f"source={int(source_id)} blocked=public_infra_not_adapter "
                f"address={adapter} infra={public_infra[adapter.lower()]}"
            )
            return 2
        _require_contract_code(w3, adapter)

        current = contract.functions.adapterForSource(int(source_id)).call()
        data = contract.encode_abi("configureAdapter", args=[int(source_id), adapter])
        tx = {
            "chainId": CHAIN_ID,
            "nonce": nonce,
            "to": target,
            "value": 0,
            "data": data,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee,
            "gas": 120_000,
            "type": 2,
        }
        print(
            f"source={int(source_id)} name={FLASH_SOURCE_NAMES[source_id]} "
            f"current={current} new={adapter} calldata={data[:10]} bytes={(len(data)-2)//2}"
        )
        if args.send:
            from eth_account import Account

            signed = Account.from_key(PRIVATE_KEY).sign_transaction(tx)
            raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
            tx_hash = w3.eth.send_raw_transaction(raw_tx).hex()
            tx_hashes.append(tx_hash)
            print(f"sent source={int(source_id)} tx={tx_hash}")
            nonce += 1

    if args.send:
        print(f"configure_adapters=SENT count={len(tx_hashes)}")
    else:
        print("configure_adapters=DRY_RUN send=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(configure())

