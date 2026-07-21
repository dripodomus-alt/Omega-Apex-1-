#!/usr/bin/env python3
# ==============================================================================
# configure_route_pool_kinds.py -- typed route-pool allowlist writer.
# ==============================================================================

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Iterable

from eth_account import Account
from web3 import Web3

from . import rpc_layer
from .config import (
    BROADCAST_RPC_URL,
    BROADCAST_RPC_FALLBACK_URLS,
    CHAIN_ID,
    CONFIRM_FLAG,
    EXEC_MODE,
    LIVE_FLAG,
    PRIVATE_KEY,
    REQUIRED_CONFIRM,
    _env,
)
from .execution import wallet_address
from .rpc_layer import DEEP_POOL_REGISTRY
from .adapter_registry import resolve_capital_source_adapter
from .transport_lanes import (
    LANE_LIVE_BROADCAST_PRIMARY,
    LANE_PUBLIC_BROADCAST_FALLBACK,
    select_endpoint,
)


ZERO = "0x" + "00" * 20

ROUTE_POOL_KIND = {
    "UniswapV2": 1,
    "UniswapV3": 2,
    "QuickSwapV3": 3,
    "Algebra": 3,
    "Curve": 4,
    "Balancer": 5,
}

ADAPTER_ENV_KEYS = {
    "aave": "AAVE_V3_CAPITAL_ADAPTER",
    "balancer": "BALANCER_VAULT_CAPITAL_ADAPTER",
    "liquidation": "AAVE_V3_LIQUIDATION_ADAPTER",
    "curve": "CURVE_CAPITAL_ADAPTER",
}

ABI_ROUTE_POOL_KIND = [
    {
        "name": "configureRoutePoolKinds",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "pools", "type": "address[]"},
            {"name": "kinds", "type": "uint8[]"},
        ],
        "outputs": [],
    },
    {
        "name": "setRoutePoolKindEnforced",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "enforced", "type": "bool"}],
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
        "name": "routePoolKindEnforced",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "routePoolKind",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "pool", "type": "address"}],
        "outputs": [{"name": "", "type": "uint8"}],
    },
]


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


def _mask_url(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parsed = urlsplit(url)
        path = parsed.path
        if len(path) > 16:
            path = f"{path[:9]}...{path[-6:]}"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    except Exception:
        return url[:32] + "..." if len(url) > 35 else url


def _dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(v.strip() for v in values if isinstance(v, str) and v.strip()))


def _provider_for_url(url: str) -> Web3:
    provider = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 20}))
    rpc_layer._inject_poa_middleware(provider)
    return provider


def _broadcast_candidates(override_url: str = "") -> list[str]:
    return _dedupe(
        [
            override_url,
            select_endpoint(LANE_LIVE_BROADCAST_PRIMARY, probe_if_stale=True),
            select_endpoint(LANE_PUBLIC_BROADCAST_FALLBACK, probe_if_stale=True),
            BROADCAST_RPC_URL,
            *BROADCAST_RPC_FALLBACK_URLS,
        ]
    )


def _tx_w3(send: bool, *, override_url: str = "") -> tuple[Web3, str]:
    if send:
        failures: list[str] = []
        for url in _broadcast_candidates(override_url):
            try:
                provider = _provider_for_url(url)
                actual_chain_id = int(provider.eth.chain_id)
                if actual_chain_id != CHAIN_ID:
                    detail = f"{_mask_url(url)}: wrong_chain_id_{actual_chain_id}"
                    failures.append(detail)
                    print(f"broadcast_rpc_candidate_rejected={detail}")
                    continue
                print(f"broadcast_rpc_selected={_mask_url(url)}")
                return provider, url
            except Exception as exc:
                detail = f"{_mask_url(url)}: {type(exc).__name__}: {str(exc)[:160]}"
                failures.append(detail)
                print(f"broadcast_rpc_candidate_rejected={detail}")
        print("broadcast_rpc_selection=FAIL")
        for failure in failures[:12]:
            print(f"broadcast_rpc_candidate_rejected={failure}")
        raise RuntimeError("no usable Chain 137 broadcast RPC endpoint")
    if rpc_layer.w3 is None:
        raise RuntimeError("RPC not connected")
    return rpc_layer.w3, ""


def _adapter_address(selection: str) -> str:
    value = _env(ADAPTER_ENV_KEYS[selection])
    if (not value or not Web3.is_address(value) or value.lower() == ZERO.lower()) and selection in {"aave", "balancer"}:
        source_id = 0 if selection == "aave" else 1
        resolution = resolve_capital_source_adapter(source_id)
        if resolution.executable and resolution.adapter_address:
            return Web3.to_checksum_address(resolution.adapter_address)
    if not value or not Web3.is_address(value) or value.lower() == ZERO.lower():
        raise RuntimeError(f"{ADAPTER_ENV_KEYS[selection]} is not configured")
    return Web3.to_checksum_address(value)


def _selected_adapters(selection: str) -> list[str]:
    if selection == "all":
        return list(ADAPTER_ENV_KEYS)
    if selection == "capital":
        return ["aave", "balancer"]
    return [selection]


def _pool_kind_rows(live: bool) -> list[tuple[str, int, str, str]]:
    registry = rpc_layer.discover_factory_pool_registry(DEEP_POOL_REGISTRY) if live else DEEP_POOL_REGISTRY
    rows: list[tuple[str, int, str, str]] = []
    for pool_id, pool in registry.items():
        protocol = str(pool.get("protocol") or "")
        address = str(pool.get("address") or "")
        kind = ROUTE_POOL_KIND.get(protocol)
        if kind and Web3.is_address(address):
            rows.append((Web3.to_checksum_address(address), kind, pool_id, protocol))
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


def _rows_requiring_write(contract, rows: list[tuple[str, int, str, str]]) -> list[tuple[str, int, str, str]]:
    needed: list[tuple[str, int, str, str]] = []
    try:
        calls = [
            (contract.address, True, rpc_layer._encode_fn(contract, "routePoolKind", [address]))
            for address, _, _, _ in rows
        ]
        results = rpc_layer.multicall3_aggregate(calls)
        for row, result in zip(rows, results):
            address, expected_kind, pool_id, protocol = row
            current = -1
            if result[0] and result[1]:
                current = int(rpc_layer.w3.codec.decode(["uint8"], result[1])[0])
            if current != expected_kind:
                needed.append((address, expected_kind, pool_id, protocol))
        return needed
    except Exception as exc:
        print(f"route_pool_kind_multicall=unavailable detail={type(exc).__name__}: {str(exc)[:180]}")
        for address, expected_kind, pool_id, protocol in rows:
            try:
                current = int(contract.functions.routePoolKind(address).call())
            except Exception:
                current = -1
            if current != expected_kind:
                needed.append((address, expected_kind, pool_id, protocol))
    return needed


def _native_fee_cap_wei(value: str) -> int:
    try:
        cap = Decimal(str(value))
    except (InvalidOperation, ValueError):
        cap = Decimal("0.85")
    if cap <= 0:
        cap = Decimal("0.85")
    return int(cap * Decimal("1e18"))


def _native_from_wei(value: int) -> str:
    return f"{Decimal(value) / Decimal('1e18'):.6f}"


def _send_configure_chunk(
    *,
    w3: Web3,
    contract,
    adapter_name: str,
    chunk: list[tuple[str, int, str, str]],
    signer: str,
    nonce: int,
    max_tx_fee_wei: int,
) -> tuple[int, int]:
    pools = [item[0] for item in chunk]
    kinds = [item[1] for item in chunk]
    tx = contract.functions.configureRoutePoolKinds(pools, kinds).build_transaction({
        "chainId": CHAIN_ID,
        "from": signer,
        "nonce": nonce,
        "value": 0,
    })
    gas_estimate = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas_estimate * 1.25)
    from .gas_oracle import eip1559_fee_params

    max_fee, priority_fee, gas_fee_source = eip1559_fee_params()
    tx["maxFeePerGas"] = max_fee
    tx["maxPriorityFeePerGas"] = priority_fee
    tx["type"] = 2
    worst_case_fee_wei = int(tx["gas"]) * int(tx["maxFeePerGas"])

    if worst_case_fee_wei > max_tx_fee_wei and len(chunk) > 1:
        midpoint = max(1, len(chunk) // 2)
        print(
            "configure_chunk_split "
            f"adapter={adapter_name} pools={len(chunk)} "
            f"worst_case_native={_native_from_wei(worst_case_fee_wei)} "
            f"cap_native={_native_from_wei(max_tx_fee_wei)}"
        )
        sent_left, nonce = _send_configure_chunk(
            w3=w3,
            contract=contract,
            adapter_name=adapter_name,
            chunk=chunk[:midpoint],
            signer=signer,
            nonce=nonce,
            max_tx_fee_wei=max_tx_fee_wei,
        )
        sent_right, nonce = _send_configure_chunk(
            w3=w3,
            contract=contract,
            adapter_name=adapter_name,
            chunk=chunk[midpoint:],
            signer=signer,
            nonce=nonce,
            max_tx_fee_wei=max_tx_fee_wei,
        )
        return sent_left + sent_right, nonce

    signed = Account.from_key(PRIVATE_KEY).sign_transaction(tx)
    raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    try:
        tx_hash = w3.eth.send_raw_transaction(raw_tx).hex()
    except Exception as exc:
        if len(chunk) > 1 and "exceeds the configured cap" in str(exc).lower():
            midpoint = max(1, len(chunk) // 2)
            print(
                "configure_chunk_split "
                f"adapter={adapter_name} pools={len(chunk)} reason=provider_fee_cap "
                f"detail={str(exc)[:160]}"
            )
            sent_left, nonce = _send_configure_chunk(
                w3=w3,
                contract=contract,
                adapter_name=adapter_name,
                chunk=chunk[:midpoint],
                signer=signer,
                nonce=nonce,
                max_tx_fee_wei=max_tx_fee_wei,
            )
            sent_right, nonce = _send_configure_chunk(
                w3=w3,
                contract=contract,
                adapter_name=adapter_name,
                chunk=chunk[midpoint:],
                signer=signer,
                nonce=nonce,
                max_tx_fee_wei=max_tx_fee_wei,
            )
            return sent_left + sent_right, nonce
        raise
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        raise RuntimeError(f"configure_route_pool_kinds tx reverted: {tx_hash}")
    print(
        f"configured_route_pool_kinds adapter={adapter_name} pools={len(pools)} "
        f"kinds={dict(sorted(Counter(kinds).items()))} "
        f"gas={receipt.gasUsed} max_native={_native_from_wei(worst_case_fee_wei)} "
        f"gas_source={gas_fee_source} tx={tx_hash}"
    )
    return 1, nonce + 1


def configure(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure typed route pool kinds on Omega adapters")
    parser.add_argument("--rpc-url", default="", help="Read RPC URL")
    parser.add_argument(
        "--adapter",
        choices=["all", "capital", *ADAPTER_ENV_KEYS.keys()],
        default="capital",
    )
    parser.add_argument("--live-registry", action="store_true", help="Use discovered live registry instead of base registry")
    parser.add_argument("--chunk-size", type=int, default=60)
    parser.add_argument("--send", action="store_true", help="Broadcast configuration transactions")
    parser.add_argument(
        "--broadcast-rpc-url",
        default="",
        help="Optional writable RPC override for --send. Falls back to transport lane selection.",
    )
    parser.add_argument(
        "--max-tx-fee-native",
        default=_env("ROUTE_POOL_KIND_MAX_TX_FEE_NATIVE", "0.85"),
        help="Worst-case native token fee cap per configuration tx before recursive chunk splitting.",
    )
    parser.add_argument(
        "--disable-enforcement",
        action="store_true",
        help="Also set routePoolKindEnforced=false. Not recommended for live mode.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.chunk_size <= 0:
        print("configure_route_pool_kinds=FAIL reason=chunk_size_must_be_positive")
        return 1
    if args.disable_enforcement and args.send:
        print("configure_route_pool_kinds=BLOCKED reason=disable_enforcement_live_write_refused")
        return 2
    max_tx_fee_wei = _native_fee_cap_wei(args.max_tx_fee_native)
    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("configure_route_pool_kinds=FAIL reason=rpc_connect_false")
        return 1

    try:
        w3, selected_broadcast_url = _tx_w3(args.send, override_url=args.broadcast_rpc_url)
    except RuntimeError as exc:
        print(f"configure_route_pool_kinds=FAIL reason=broadcast_rpc_unavailable detail={exc}")
        return 1
    actual_chain_id = int(w3.eth.chain_id)
    if actual_chain_id != CHAIN_ID:
        print(f"configure_route_pool_kinds=FAIL reason=chain_id_mismatch actual={actual_chain_id}")
        return 1

    rows = _pool_kind_rows(args.live_registry)
    counts = Counter(protocol for _, _, _, protocol in rows)
    print(
        f"route_pool_kind_rows={len(rows)} live_registry={args.live_registry} "
        f"protocol_counts={dict(sorted(counts.items()))}"
    )
    if not rows:
        print("configure_route_pool_kinds=FAIL reason=no_supported_pools")
        return 1

    send_ok, missing = _send_allowed()
    if args.send and not send_ok:
        print(f"configure_route_pool_kinds=BLOCKED reason=send_guards_missing detail={missing}")
        return 2

    signer = wallet_address()
    nonce = w3.eth.get_transaction_count(signer) if args.send else 0
    tx_count = 0

    for adapter_name in _selected_adapters(args.adapter):
        try:
            address = _adapter_address(adapter_name)
        except RuntimeError as exc:
            print(f"adapter={adapter_name} skipped reason={exc}")
            continue
        code = w3.eth.get_code(address).hex()
        if code in ("", "0x"):
            print(f"adapter={adapter_name} skipped reason=no_bytecode address={address}")
            continue
        contract = w3.eth.contract(address=address, abi=ABI_ROUTE_POOL_KIND)
        try:
            owner = contract.functions.owner().call()
        except Exception as exc:
            print(f"adapter={adapter_name} skipped reason=owner_read_failed detail={exc}")
            continue
        print(f"adapter={adapter_name} address={address} owner={owner}")

        if args.send and owner.lower() != signer.lower():
            print(f"configure_route_pool_kinds=BLOCKED adapter={adapter_name} reason=owner_mismatch signer={signer}")
            return 2

        needed_rows = _rows_requiring_write(contract, rows)
        skipped_rows = len(rows) - len(needed_rows)
        print(
            f"adapter={adapter_name} route_pool_kind_needed={len(needed_rows)} "
            f"already_correct={skipped_rows}"
        )
        if not needed_rows:
            continue

        for chunk in _chunked(needed_rows, args.chunk_size):
            pools = [item[0] for item in chunk]
            kinds = [item[1] for item in chunk]
            if not args.send:
                print(
                    f"configure_plan adapter={adapter_name} pools={len(pools)} "
                    f"kinds={dict(sorted(Counter(kinds).items()))}"
                )
                continue
            sent, nonce = _send_configure_chunk(
                w3=w3,
                contract=contract,
                adapter_name=adapter_name,
                chunk=chunk,
                signer=signer,
                nonce=nonce,
                max_tx_fee_wei=max_tx_fee_wei,
            )
            tx_count += sent

        if args.disable_enforcement and not args.send:
            print(f"enforcement_plan adapter={adapter_name} enforced=false dry_run_only")

    if args.send:
        print(f"configure_route_pool_kinds=SENT tx_count={tx_count} broadcast_rpc={_mask_url(selected_broadcast_url)}")
    else:
        print("configure_route_pool_kinds=DRY_RUN send=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(configure())
