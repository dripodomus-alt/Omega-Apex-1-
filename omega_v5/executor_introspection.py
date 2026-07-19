#!/usr/bin/env python3
# ==============================================================================
# executor_introspection.py -- read-only executor adapter/probe tooling.
# ==============================================================================

from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from web3 import Web3

from . import rpc_layer
from .config import CHAIN_ID, EXECUTOR_CONTRACT
from .contract_deployments import resolved_deployments, validate_deployment_bytecode
from .execution import (
    ABI_EXECUTOR,
    EXECUTE_FLASH_ARB_SELECTOR,
    _encode_contract_call,
    simulation_from_address,
)
from .flash_loan import MIN_NET_PROFIT_USD
from .revert_decoder import format_revert
from .rpc_layer import TOKEN_ADDRESSES


ZERO = "0x" + "00" * 20
CONFIGURE_ADAPTER_SELECTOR = Web3.keccak(text="configureAdapter(uint8,address)")[:4].hex()
ADAPTER_FOR_SOURCE_SELECTOR = Web3.keccak(text="adapterForSource(uint8)")[:4].hex()
ADAPTER_FOR_SOURCE_ABI = [
    {
        "name": "adapterForSource",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "flashSource", "type": "uint8"}],
        "outputs": [{"name": "", "type": "address"}],
    }
]


@dataclass(frozen=True)
class ProbeResult:
    protocol_seq: tuple[str, ...]
    target_names: tuple[str, ...]
    target_addresses: tuple[str, ...]
    ok: bool
    detail: str

    @property
    def adapter_accepted(self) -> bool:
        return "InvalidAdapter()" not in self.detail


def _runtime_selectors(bytecode: str) -> list[str]:
    code = bytecode.lower().removeprefix("0x")
    selectors: set[str] = set()
    for marker in ("63", "7f"):
        idx = 0
        while True:
            idx = code.find(marker, idx)
            if idx < 0:
                break
            if marker == "63" and idx + 10 <= len(code):
                selectors.add("0x" + code[idx + 2: idx + 10])
            idx += 2
    return sorted(selectors)


def executor_selectors() -> list[str]:
    if rpc_layer.w3 is None or not EXECUTOR_CONTRACT:
        return []
    code = rpc_layer.w3.eth.get_code(Web3.to_checksum_address(EXECUTOR_CONTRACT)).hex()
    return _runtime_selectors(code)


def adapter_for_source_values() -> list[tuple[int, str, str]]:
    if rpc_layer.w3 is None or not EXECUTOR_CONTRACT:
        return []
    contract = rpc_layer.w3.eth.contract(
        address=Web3.to_checksum_address(EXECUTOR_CONTRACT),
        abi=ADAPTER_FOR_SOURCE_ABI,
    )
    rows: list[tuple[int, str, str]] = []
    for source_id in range(4):
        try:
            address = contract.functions.adapterForSource(source_id).call()
            detail = "unset" if address.lower() == ZERO.lower() else "configured"
            rows.append((source_id, address, detail))
        except Exception as exc:
            rows.append((source_id, ZERO, f"read_failed={type(exc).__name__}: {exc}"))
    return rows


def _candidate_targets() -> dict[str, list[tuple[str, str]]]:
    deployments = resolved_deployments()
    return {
        "UniswapV2": [
            ("QuickSwapV2Router", deployments["QUICKSWAP_V2_ROUTER"].address),
            ("QuickSwapV2Factory", deployments["QUICKSWAP_V2_FACTORY"].address),
        ],
        "UniswapV3": [
            ("UniswapV3SwapRouter02", deployments["UNISWAP_V3_SWAP_ROUTER_02"].address),
            ("UniswapV3SwapRouter", deployments["UNISWAP_V3_SWAP_ROUTER"].address),
            ("UniswapUniversalRouter", deployments["UNISWAP_UNIVERSAL_ROUTER"].address),
            ("UniswapV3QuoterV2", deployments["UNISWAP_V3_QUOTER_V2"].address),
            ("UniswapV3Factory", deployments["UNISWAP_V3_FACTORY"].address),
        ],
        "Curve": [
            ("CurveRouter", deployments["CURVE_ROUTER"].address),
            ("CurveMetaRegistry", deployments["CURVE_META_REGISTRY"].address),
            ("CurveStableFactory", deployments["CURVE_STABLE_FACTORY"].address),
            ("CurveStableCalcZap", deployments["CURVE_STABLE_CALC_ZAP"].address),
        ],
        "Balancer": [
            ("BalancerV2Vault", deployments["BALANCER_VAULT"].address),
            ("BalancerAuthorizer", deployments["BALANCER_AUTHORIZER"].address),
        ],
        "DODO": [
            ("DODOV2Proxy", deployments["DODO_V2_PROXY"].address),
            ("DODORouteProxy", deployments["DODO_ROUTE_PROXY"].address),
            ("DODODVMFactory", deployments["DODO_DVM_FACTORY"].address),
            ("DODODPPFactory", deployments["DODO_DPP_FACTORY"].address),
            ("DODODSPFactory", deployments["DODO_DSP_FACTORY"].address),
        ],
    }


def _calldata(protocol_targets: list[str]) -> str:
    if rpc_layer.w3 is None:
        raise RuntimeError("RPC not connected")
    if not EXECUTOR_CONTRACT:
        raise RuntimeError("EXECUTOR_CONTRACT_ADDR missing")

    asset = Web3.to_checksum_address(TOKEN_ADDRESSES.get("USDC.e", TOKEN_ADDRESSES.get("USDC", ZERO)))
    token_path = [
        asset,
        Web3.to_checksum_address(TOKEN_ADDRESSES.get("WETH", ZERO)),
        asset,
    ]
    amount = int(Decimal("10000") * Decimal("1e6"))
    min_profit = int(MIN_NET_PROFIT_USD * Decimal("1e6"))
    contract = rpc_layer.w3.eth.contract(
        address=Web3.to_checksum_address(EXECUTOR_CONTRACT),
        abi=ABI_EXECUTOR,
    )
    data = _encode_contract_call(
        contract,
        [
            1,
            asset,
            amount,
            [Web3.to_checksum_address(address) for address in protocol_targets],
            token_path,
            min_profit,
        ],
    )
    if not data.startswith(EXECUTE_FLASH_ARB_SELECTOR):
        raise RuntimeError(f"selector mismatch: {data[:10]}")
    return data


def probe_target_sequence(
    protocol_seq: Iterable[str],
    target_pairs: Iterable[tuple[str, str]],
) -> ProbeResult:
    names = tuple(name for name, _ in target_pairs)
    addresses = tuple(address for _, address in target_pairs)
    tx = {
        "to": Web3.to_checksum_address(EXECUTOR_CONTRACT),
        "data": _calldata(list(addresses)),
        "value": 0,
    }
    from_addr = simulation_from_address()
    if from_addr:
        tx["from"] = Web3.to_checksum_address(from_addr)

    try:
        result = rpc_layer.w3.eth.call(tx, block_identifier="latest")
        return ProbeResult(tuple(protocol_seq), names, addresses, True, result.hex())
    except Exception as exc:
        return ProbeResult(tuple(protocol_seq), names, addresses, False, format_revert(exc))


def probe_known_targets(protocol_seq: tuple[str, ...] = ("UniswapV3", "UniswapV2")) -> list[ProbeResult]:
    candidates = _candidate_targets()
    candidate_lists = [candidates[p] for p in protocol_seq if p in candidates]
    if len(candidate_lists) != len(protocol_seq):
        return []
    results = []
    for combo in itertools.product(*candidate_lists):
        results.append(probe_target_sequence(protocol_seq, combo))
    results.sort(key=lambda item: (not item.adapter_accepted, item.target_names))
    return results


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only executor adapter introspection")
    parser.add_argument("--rpc-url", default="", help="HTTP RPC URL")
    parser.add_argument("--probe", action="store_true", help="Probe known router/quoter candidates")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("executor_introspection=FAIL rpc_connect=False")
        return 1

    print(f"executor={EXECUTOR_CONTRACT}")
    print(f"simulation_from={simulation_from_address() or 'NOT SET'}")
    print(f"selector adapterForSource(uint8)=0x{ADAPTER_FOR_SOURCE_SELECTOR}")
    print(f"selector configureAdapter(uint8,address)=0x{CONFIGURE_ADAPTER_SELECTOR}")
    selectors = executor_selectors()
    print(f"runtime_selectors={len(selectors)} {selectors}")
    for source_id, adapter, detail in adapter_for_source_values():
        print(f"adapterForSource[{source_id}]={adapter} detail={detail}")

    deployment_results = validate_deployment_bytecode(rpc_layer.w3)
    ok_count = sum(1 for _, ok, _ in deployment_results if ok)
    print(f"protocol_infrastructure_bytecode_ok={ok_count}/{len(deployment_results)}")
    for deployment, ok, detail in deployment_results:
        print(f"infra {deployment.env_key} {deployment.address} ok={ok} role={deployment.role} detail={detail}")

    if args.probe:
        print("probe_note=legacy public infrastructure probe; routers/quoters are not capital-source adapters")
        results = probe_known_targets()
        for item in results:
            print(
                "probe "
                f"protocols={item.protocol_seq} "
                f"targets={item.target_names} "
                f"adapter_accepted={item.adapter_accepted} "
                f"ok={item.ok} detail={item.detail[:180]}"
            )
        accepted = [item for item in results if item.adapter_accepted]
        print(f"executor_adapter_candidates_accepted={len(accepted)}")
        if not accepted:
            print("executor_adapter_resolution=BLOCKED reason=no known public router/quoter target passed InvalidAdapter gate")
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
