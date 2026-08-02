#!/usr/bin/env python3
# ==============================================================================
# sign_adapter_slot_txs.py -- offline owner-signed adapter deployment/config txs.
# ==============================================================================

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable
from collections import Counter

from eth_account import Account
from eth_utils import keccak, to_checksum_address
from web3 import Web3

from . import rpc_layer
from .config import (
    ADAPTER_CONFIGURATION_TARGET,
    C1_PAYLOAD_TARGET,
    CHAIN_ID,
    PRIVATE_KEY,
    PROTOCOL_REGISTRY,
    normalize_protocol,
)
from .contract_deployments import deployment_address
from .execution import wallet_address
from .flash_loan import BALANCER_VAULT_POLYGON
from .paths import output_path, resolve_repo_relative
from .rpc_layer import DEEP_POOL_REGISTRY


ZERO_ADDRESS = "0x" + "00" * 20
BALANCER_ARTIFACT = output_path("OmegaBalancerCapitalSourceAdapter.sol", "OmegaBalancerCapitalSourceAdapter.json")
DEFAULT_OUTPUT = output_path("owner_signed_adapter_slot_txs.json")

EXECUTOR_ABI = [
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
]

ROUTE_POOL_KIND_ABI = [
    {
        "name": "configureRoutePoolKinds",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "pools", "type": "address[]"},
            {"name": "kinds", "type": "uint8[]"},
        ],
        "outputs": [],
    }
]

ROUTE_POOL_KIND = {
    key: int(meta["pool_kind"])
    for key, meta in PROTOCOL_REGISTRY.items()
    if meta.get("pool_kind") is not None
}

def _load_artifact(path: Path = BALANCER_ARTIFACT) -> tuple[list, str]:
    if not path.exists():
        raise RuntimeError(f"artifact missing: {path}. Run `forge build` first.")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    bytecode = artifact.get("bytecode", {}).get("object", "")
    if not bytecode:
        raise RuntimeError(f"artifact has no bytecode: {path}")
    return artifact["abi"], bytecode


def _rlp_bytes(raw: bytes) -> bytes:
    if len(raw) == 1 and raw[0] < 0x80:
        return raw
    if len(raw) <= 55:
        return bytes([0x80 + len(raw)]) + raw
    length_bytes = len(raw).to_bytes((len(raw).bit_length() + 7) // 8, "big")
    return bytes([0xB7 + len(length_bytes)]) + length_bytes + raw


def _rlp_int(value: int) -> bytes:
    if value == 0:
        return bytes([0x80])
    return _rlp_bytes(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def _rlp_list(items: list[bytes]) -> bytes:
    payload = b"".join(items)
    if len(payload) <= 55:
        return bytes([0xC0 + len(payload)]) + payload
    length_bytes = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
    return bytes([0xF7 + len(length_bytes)]) + length_bytes + payload


def _created_contract_address(sender: str, nonce: int) -> str:
    encoded = _rlp_list([
        _rlp_bytes(bytes.fromhex(sender.removeprefix("0x"))),
        _rlp_int(nonce),
    ])
    return to_checksum_address(keccak(encoded)[-20:])


def _raw_tx_hex(signed) -> str:
    raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    return raw_tx.hex()


def _pool_kind_rows(*, live_registry: bool) -> list[tuple[str, int, str, str]]:
    registry = DEEP_POOL_REGISTRY
    if live_registry:
        registry = rpc_layer.load_all_live_pools(DEEP_POOL_REGISTRY)
    rows: list[tuple[str, int, str, str]] = []
    for pool_id, pool in registry.items():
        raw_protocol = str(pool.get("protocol") or "")
        address = str(pool.get("address") or "")
        try:
            protocol = normalize_protocol(raw_protocol)
        except Exception:
            protocol = raw_protocol
        kind = ROUTE_POOL_KIND.get(protocol)
        if kind and Web3.is_address(address):
            rows.append((Web3.to_checksum_address(address), kind, str(pool_id), protocol))
    rows.sort(key=lambda item: (item[1], item[0].lower()))
    seen: set[str] = set()
    deduped: list[tuple[str, int, str, str]] = []
    for row in rows:
        key = row[0].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _chunked(items: list[tuple[str, int, str, str]], size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def sign_bundle(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create signed raw txs to deploy Balancer adapter and configure adapterForSource(1)."
    )
    parser.add_argument("--rpc-url", default="", help="Read RPC URL for nonce/gas/owner checks")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Signed bundle JSON output path")
    parser.add_argument("--replace-existing", action="store_true", help="Allow signing if slot 1 is already configured")
    parser.add_argument("--skip-route-kinds", action="store_true", help="Do not include typed route-pool allowlist transactions")
    parser.add_argument("--live-registry", action="store_true", help="Include live discovered rankable pools in route-kind config")
    parser.add_argument("--route-kind-chunk-size", type=int, default=60)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not PRIVATE_KEY or not wallet_address():
        print("sign_adapter_slot_txs=FAIL reason=EXECUTOR_PRIVATE_KEY invalid")
        return 1
    if not C1_PAYLOAD_TARGET or not ADAPTER_CONFIGURATION_TARGET:
        print("sign_adapter_slot_txs=FAIL reason=executor target missing")
        return 1
    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("sign_adapter_slot_txs=FAIL reason=rpc_connect_false")
        return 1
    if rpc_layer.w3.eth.chain_id != CHAIN_ID:
        print(f"sign_adapter_slot_txs=FAIL reason=chain_id_mismatch actual={rpc_layer.w3.eth.chain_id}")
        return 1

    w3 = rpc_layer.w3
    signer = Web3.to_checksum_address(wallet_address())
    target = Web3.to_checksum_address(ADAPTER_CONFIGURATION_TARGET)
    executor = w3.eth.contract(address=target, abi=EXECUTOR_ABI)
    owner = Web3.to_checksum_address(executor.functions.owner().call())
    if signer.lower() != owner.lower():
        print(f"sign_adapter_slot_txs=FAIL reason=owner_mismatch wallet={signer} owner={owner}")
        return 1

    current = Web3.to_checksum_address(executor.functions.adapterForSource(1).call())
    if current.lower() != ZERO_ADDRESS.lower() and not args.replace_existing:
        print(f"sign_adapter_slot_txs=FAIL reason=slot_1_already_configured current={current}")
        return 1

    abi, bytecode = _load_artifact()
    bytecode_hash = Web3.keccak(hexstr=bytecode).hex()
    adapter_contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    constructor_args = [
        Web3.to_checksum_address(C1_PAYLOAD_TARGET),
        Web3.to_checksum_address(deployment_address("BALANCER_VAULT") or BALANCER_VAULT_POLYGON),
    ]
    deploy_constructor = adapter_contract.constructor(*constructor_args)

    nonce = w3.eth.get_transaction_count(signer)
    predicted_adapter = _created_contract_address(signer, nonce)
    from .gas_oracle import eip1559_fee_params

    max_fee, max_priority_fee, gas_fee_source = eip1559_fee_params()
    print(f"sign_adapter_slot_txs_gas_source={gas_fee_source}")

    deploy_tx = deploy_constructor.build_transaction({
        "chainId": CHAIN_ID,
        "from": signer,
        "nonce": nonce,
        "value": 0,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority_fee,
        "type": 2,
    })
    deploy_gas = w3.eth.estimate_gas(deploy_tx)
    deploy_tx["gas"] = int(deploy_gas * 1.25)

    route_kind_txs = []
    route_kind_summary = {
        "included": False,
        "live_registry": False,
        "pool_count": 0,
        "protocol_counts": {},
        "chunk_size": args.route_kind_chunk_size,
    }
    if not args.skip_route_kinds:
        if args.route_kind_chunk_size <= 0:
            print("sign_adapter_slot_txs=FAIL reason=route_kind_chunk_size_must_be_positive")
            return 1
        rows = _pool_kind_rows(live_registry=args.live_registry)
        route_kind_summary = {
            "included": True,
            "live_registry": args.live_registry,
            "pool_count": len(rows),
            "protocol_counts": dict(sorted(Counter(protocol for _, _, _, protocol in rows).items())),
            "chunk_size": args.route_kind_chunk_size,
        }
        route_adapter = w3.eth.contract(address=predicted_adapter, abi=ROUTE_POOL_KIND_ABI)
        for chunk_index, chunk in enumerate(_chunked(rows, args.route_kind_chunk_size), start=1):
            pools = [item[0] for item in chunk]
            kinds = [item[1] for item in chunk]
            data = route_adapter.encode_abi("configureRoutePoolKinds", args=[pools, kinds])
            route_kind_txs.append({
                "name": f"configure_route_pool_kinds_{chunk_index:02d}",
                "nonce": nonce + len(route_kind_txs) + 1,
                "to": predicted_adapter,
                "value": 0,
                "data": data,
                "gas": 1_500_000,
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": max_priority_fee,
                "type": 2,
                "pool_count": len(pools),
                "kind_counts": dict(sorted(Counter(kinds).items())),
            })

    configure_nonce = nonce + 1 + len(route_kind_txs)
    configure_data = executor.encode_abi("configureAdapter", args=[1, predicted_adapter])
    configure_tx = {
        "chainId": CHAIN_ID,
        "from": signer,
        "nonce": configure_nonce,
        "to": target,
        "value": 0,
        "data": configure_data,
        "gas": 120_000,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": max_priority_fee,
        "type": 2,
    }

    signed_deploy = Account.from_key(PRIVATE_KEY).sign_transaction(deploy_tx)
    signed_route_kind_txs = []
    for tx in route_kind_txs:
        built = {
            "chainId": CHAIN_ID,
            "from": signer,
            "nonce": tx["nonce"],
            "to": tx["to"],
            "value": tx["value"],
            "data": tx["data"],
            "gas": tx["gas"],
            "maxFeePerGas": tx["maxFeePerGas"],
            "maxPriorityFeePerGas": tx["maxPriorityFeePerGas"],
            "type": tx["type"],
        }
        signed = Account.from_key(PRIVATE_KEY).sign_transaction(built)
        signed_route_kind_txs.append((tx, signed))
    signed_configure = Account.from_key(PRIVATE_KEY).sign_transaction(configure_tx)
    bundle = {
        "chain_id": CHAIN_ID,
        "signer": signer,
        "executor": target,
        "owner": owner,
        "source_slot": 1,
        "current_adapter_for_source_1": current,
        "predicted_balancer_adapter": predicted_adapter,
        "constructor_args": constructor_args,
        "adapter_bytecode_hash": bytecode_hash,
        "route_pool_kinds": route_kind_summary,
        "nonce_start": nonce,
        "transactions": [
            {
                "name": "deploy_balancer_capital_adapter",
                "nonce": nonce,
                "to": None,
                "gas": deploy_tx["gas"],
                "maxFeePerGas": deploy_tx["maxFeePerGas"],
                "maxPriorityFeePerGas": deploy_tx["maxPriorityFeePerGas"],
                "hash": signed_deploy.hash.hex(),
                "raw_transaction": _raw_tx_hex(signed_deploy),
            },
            *[
                {
                    "name": tx["name"],
                    "nonce": tx["nonce"],
                    "to": tx["to"],
                    "gas": tx["gas"],
                    "maxFeePerGas": tx["maxFeePerGas"],
                    "maxPriorityFeePerGas": tx["maxPriorityFeePerGas"],
                    "calldata": tx["data"],
                    "pool_count": tx["pool_count"],
                    "kind_counts": tx["kind_counts"],
                    "hash": signed.hash.hex(),
                    "raw_transaction": _raw_tx_hex(signed),
                }
                for tx, signed in signed_route_kind_txs
            ],
            {
                "name": "configure_adapter_for_source_1",
                "nonce": configure_nonce,
                "to": target,
                "gas": configure_tx["gas"],
                "maxFeePerGas": configure_tx["maxFeePerGas"],
                "maxPriorityFeePerGas": configure_tx["maxPriorityFeePerGas"],
                "calldata": configure_data,
                "hash": signed_configure.hash.hex(),
                "raw_transaction": _raw_tx_hex(signed_configure),
            },
        ],
        "broadcast_order": [
            "deploy_balancer_capital_adapter",
            *[tx["name"] for tx in route_kind_txs],
            "configure_adapter_for_source_1",
        ],
        "safety": {
            "broadcasted": False,
            "note": "Raw signed transactions are valid for Polygon mainnet; broadcast only in listed order.",
        },
    }

    output = resolve_repo_relative(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    print(f"sign_adapter_slot_txs=SIGNED output={output}")
    print(f"signer={signer}")
    print(f"executor={target}")
    print(f"predicted_balancer_adapter={predicted_adapter}")
    print(f"adapter_bytecode_hash={bytecode_hash}")
    print(f"route_pool_kinds={route_kind_summary}")
    print(f"deploy_tx_hash={signed_deploy.hash.hex()}")
    print(f"configure_tx_hash={signed_configure.hash.hex()}")
    print("broadcasted=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(sign_bundle())

