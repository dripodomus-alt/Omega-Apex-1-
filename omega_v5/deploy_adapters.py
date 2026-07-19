#!/usr/bin/env python3
# ==============================================================================
# deploy_adapters.py -- guarded deployment utility for Omega source adapters.
# ==============================================================================

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from web3 import Web3

from . import rpc_layer
from .config import (
    ADAPTER_CONFIGURATION_TARGET,
    BROADCAST_RPC_URL,
    C1_PAYLOAD_TARGET,
    CHAIN_ID,
    CONFIRM_FLAG,
    EXEC_MODE,
    LIQUIDATION_EXECUTOR_ADDRESS,
    LIVE_FLAG,
    PRIVATE_KEY,
    REQUIRED_CONFIRM,
    _env,
)
from .contract_deployments import deployment_address
from .execution import wallet_address
from .flash_loan import AAVE_V3_POOL_POLYGON, BALANCER_VAULT_POLYGON
from .paths import env_path, output_path


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
]


ADAPTERS = {
    "balancer": {
        "contract": "OmegaBalancerCapitalSourceAdapter",
        "artifact": output_path("OmegaBalancerCapitalSourceAdapter.sol", "OmegaBalancerCapitalSourceAdapter.json"),
        "env": "BALANCER_VAULT_CAPITAL_ADAPTER",
        "source_id": 1,
        "kind": "capital_source",
    },
    "balancer-v3": {
        "contract": "OmegaBalancerV3CapitalSourceAdapter",
        "artifact": output_path("OmegaBalancerV3CapitalSourceAdapter.sol", "OmegaBalancerV3CapitalSourceAdapter.json"),
        "env": "BALANCER_V3_VAULT_CAPITAL_ADAPTER",
        "source_id": 1,
        "kind": "capital_source",
    },
    "aave": {
        "contract": "OmegaAaveV3CapitalSourceAdapter",
        "artifact": output_path("OmegaAaveV3CapitalSourceAdapter.sol", "OmegaAaveV3CapitalSourceAdapter.json"),
        "env": "AAVE_V3_CAPITAL_ADAPTER",
        "source_id": 0,
        "kind": "capital_source",
    },
    "aave-liquidation": {
        "contract": "OmegaAaveV3LiquidationAdapter",
        "artifact": output_path("OmegaAaveV3LiquidationAdapter.sol", "OmegaAaveV3LiquidationAdapter.json"),
        "env": "AAVE_V3_LIQUIDATION_ADAPTER",
        "source_id": None,
        "kind": "liquidation",
    },
}


def _tx_w3(send: bool = False) -> Web3:
    if send and BROADCAST_RPC_URL:
        provider = Web3(Web3.HTTPProvider(BROADCAST_RPC_URL, request_kwargs={"timeout": 20}))
        rpc_layer._inject_poa_middleware(provider)
        return provider
    if rpc_layer.w3 is None:
        raise RuntimeError("RPC not connected")
    return rpc_layer.w3


def _load_artifact(path: Path) -> tuple[list, str]:
    if not path.exists():
        raise RuntimeError(f"artifact missing: {path}. Run `forge build` first.")
    artifact = json.loads(path.read_text(encoding="utf-8"))
    bytecode = artifact.get("bytecode", {}).get("object", "")
    if not bytecode:
        raise RuntimeError(f"artifact has no bytecode: {path}")
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


def _require_checksum_address(value: str, label: str) -> str:
    if not value or not Web3.is_address(value) or Web3.to_checksum_address(value).lower() == ("0x" + "00" * 20).lower():
        raise RuntimeError(f"{label} must be a valid address")
    return Web3.to_checksum_address(value)


def _constructor_args(
    name: str,
    *,
    liquidation_executor_override: str = "",
    balancer_v3_vault_override: str = "",
) -> list[str]:
    if name == "aave-liquidation":
        executor = _require_checksum_address(
            liquidation_executor_override or LIQUIDATION_EXECUTOR_ADDRESS,
            "LIQUIDATION_EXECUTOR_ADDRESS",
        )
    else:
        executor = _require_checksum_address(C1_PAYLOAD_TARGET, "C1_PAYLOAD_TARGET")
    balancer_vault = Web3.to_checksum_address(
        deployment_address("BALANCER_VAULT") or BALANCER_VAULT_POLYGON
    )
    if name == "balancer":
        return [executor, balancer_vault]
    if name == "balancer-v3":
        return [
            executor,
            _require_checksum_address(
                balancer_v3_vault_override or _env("BALANCER_V3_VAULT"),
                "BALANCER_V3_VAULT",
            ),
        ]
    if name in {"aave", "aave-liquidation"}:
        return [
            executor,
            balancer_vault,
            Web3.to_checksum_address(deployment_address("AAVE_V3_POOL") or AAVE_V3_POOL_POLYGON),
        ]
    raise RuntimeError(f"unknown adapter {name}")


def _selected_adapters(selection: str) -> list[str]:
    def is_selectable(name: str) -> bool:
        return name != "balancer-v3" or (_env("BALANCER_V3_ENABLED_POLYGON", "false").lower() in {"1", "true", "yes", "on"} and bool(_env("BALANCER_V3_VAULT")))

    if selection == "all":
        return [name for name in ADAPTERS.keys() if is_selectable(name)]
    if selection == "capital":
        return [
            name for name, spec in ADAPTERS.items()
            if spec["kind"] == "capital_source" and is_selectable(name)
        ]
    if selection == "liquidation":
        return [name for name, spec in ADAPTERS.items() if spec["kind"] == "liquidation"]
    return [selection]


def _write_env_values(values: dict[str, str], target_env_path: Path | None = None) -> None:
    target_env_path = target_env_path or env_path()
    lines = target_env_path.read_text(encoding="utf-8").splitlines() if target_env_path.exists() else []
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

    target_env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def deploy(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy Omega capital-source adapters")
    parser.add_argument("--rpc-url", default="", help="Read RPC URL")
    parser.add_argument("--adapter", choices=["all", "capital", "liquidation", *ADAPTERS.keys()], default="all")
    parser.add_argument("--send", action="store_true", help="Broadcast deployments. Dry-run is default.")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="After a sent deployment, update .env with emitted adapter addresses.",
    )
    parser.add_argument(
        "--configure",
        action="store_true",
        help="After a sent deployment, owner-call configureAdapter(source, deployedAdapter).",
    )
    parser.add_argument(
        "--liquidation-executor",
        default="",
        help="Explicit LIQUIDATION_EXECUTOR_ADDRESS for deploying the liquidation adapter.",
    )
    parser.add_argument(
        "--balancer-v3-vault",
        default="",
        help="Explicit BALANCER_V3_VAULT for deploying the Balancer V3 unlock/settle adapter.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not C1_PAYLOAD_TARGET:
        print("deploy_adapters=FAIL reason=C1_PAYLOAD_TARGET missing")
        return 1
    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("deploy_adapters=FAIL reason=rpc_connect_false")
        return 1

    w3 = _tx_w3(send=args.send)
    if w3.eth.chain_id != CHAIN_ID:
        print(f"deploy_adapters=FAIL reason=chain_id_mismatch actual={w3.eth.chain_id}")
        return 1

    selected = _selected_adapters(args.adapter)
    send_ok, missing = _send_allowed()
    if args.configure and not ADAPTER_CONFIGURATION_TARGET:
        print("deploy_adapters=FAIL reason=ADAPTER_CONFIGURATION_TARGET missing")
        return 1
    if args.send and not send_ok:
        print(f"deploy_adapters=BLOCKED reason=send_guards_missing detail={missing}")
        return 2

    signer = wallet_address()
    nonce = w3.eth.get_transaction_count(signer) if args.send else 0
    deployed: list[tuple[str, str, str]] = []

    for name in selected:
        spec = ADAPTERS[name]
        abi, bytecode = _load_artifact(spec["artifact"])
        try:
            ctor_args = _constructor_args(
                name,
                liquidation_executor_override=args.liquidation_executor,
                balancer_v3_vault_override=args.balancer_v3_vault,
            )
        except RuntimeError as exc:
            print(f"deploy_adapters=FAIL adapter={name} reason={exc}")
            return 1
        contract = w3.eth.contract(abi=abi, bytecode=bytecode)
        constructor = contract.constructor(*ctor_args)
        print(
            f"adapter={name} contract={spec['contract']} env={spec['env']} "
            f"bytecode_bytes={(len(bytecode.removeprefix('0x'))) // 2} ctor_args={ctor_args}"
        )
        if not args.send:
            data = constructor.data_in_transaction
            print(f"deploy_data adapter={name} selectorless_bytes={(len(data) - 2) // 2}")
            if args.configure:
                if spec["source_id"] is None:
                    print(f"configure_plan adapter={name} skipped=no_adapterForSource_slot")
                else:
                    print(
                        f"configure_plan adapter={name} source={spec['source_id']} "
                        "requires --send because deployed address is not known in dry-run"
                    )
            if args.write_env:
                print(f"write_env_plan adapter={name} env={spec['env']} requires --send")
            continue

        built = constructor.build_transaction({
            "chainId": CHAIN_ID,
            "from": signer,
            "nonce": nonce,
            "value": 0,
        })
        if args.send:
            gas_estimate = w3.eth.estimate_gas(built)
            built["gas"] = int(gas_estimate * 1.25)
            from .gas_oracle import eip1559_fee_params

            max_fee, priority_fee, gas_fee_source = eip1559_fee_params()
            built["maxFeePerGas"] = max_fee
            built["maxPriorityFeePerGas"] = priority_fee
            built["type"] = 2
            from eth_account import Account

            signed = Account.from_key(PRIVATE_KEY).sign_transaction(built)
            raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
            tx_hash = w3.eth.send_raw_transaction(raw_tx).hex()
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            if receipt.status != 1:
                print(f"deploy_adapters=FAIL adapter={name} tx={tx_hash}")
                return 1
            address = receipt.contractAddress
            deployed.append((name, spec["env"], address))
            print(f"deployed adapter={name} address={address} gas_source={gas_fee_source} tx={tx_hash}")
            nonce += 1

    if args.send and args.configure and deployed:
        target = Web3.to_checksum_address(ADAPTER_CONFIGURATION_TARGET)
        executor = w3.eth.contract(address=target, abi=ABI_CONFIGURE_ADAPTER)
        owner = executor.functions.owner().call()
        if owner.lower() != signer.lower():
            print(f"deploy_adapters=BLOCKED reason=owner_mismatch wallet={signer} owner={owner}")
            return 2
        for name, _, address in deployed:
            if ADAPTERS[name]["source_id"] is None:
                print(f"configure_adapter=SKIP adapter={name} reason=no_adapterForSource_slot")
                continue
            source_id = int(ADAPTERS[name]["source_id"])
            data = executor.encode_abi("configureAdapter", args=[source_id, Web3.to_checksum_address(address)])
            tx = {
                "chainId": CHAIN_ID,
                "from": signer,
                "nonce": nonce,
                "to": target,
                "value": 0,
                "data": data,
                "gas": 120_000,
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": priority_fee,
                "type": 2,
            }
            from eth_account import Account

            signed = Account.from_key(PRIVATE_KEY).sign_transaction(tx)
            raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
            tx_hash = w3.eth.send_raw_transaction(raw_tx).hex()
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            if receipt.status != 1:
                print(f"configure_adapter=FAIL source={source_id} adapter={address} tx={tx_hash}")
                return 1
            print(f"configured source={source_id} adapter={address} tx={tx_hash}")
            nonce += 1

    if args.send:
        if args.write_env and deployed:
            env_values = {env_key: Web3.to_checksum_address(address) for _, env_key, address in deployed}
            _write_env_values(env_values)
            print(f"write_env=OK keys={list(env_values.keys())}")
        for name, env_key, address in deployed:
            print(f"{env_key}={address}")
        print(f"deploy_adapters=SENT count={len(deployed)}")
    else:
        print("deploy_adapters=DRY_RUN send=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(deploy())



