#!/usr/bin/env python3
"""
verify_deployed_contracts.py -- read-only bytecode presence gate.

This is not source-code verification. It only checks that the configured HFT/C1
executor and liquidation executor addresses have deployed bytecode on the
configured Polygon RPC before capital-injector simulations rely on them.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from web3 import AsyncHTTPProvider, AsyncWeb3, Web3

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omega_v5.config import (  # noqa: E402
    CHAIN_ID,
    EXACT_CALL_RPC_URL,
    HFT_EXECUTOR_ADDRESS,
    LIQUIDATION_EXECUTOR_ADDRESS,
)

PINNED_HFT_EXECUTOR = "0x409ece3Fd71DFBd8f692B600f36A89301cb37346"
PINNED_LIQUIDATION_EXECUTOR = "0x8cD1e93eE2DeD4F59e15650c0a16029b6Ad9b951"


@dataclass(frozen=True)
class ContractCheck:
    label: str
    address: str
    ok: bool
    bytecode_bytes: int = 0
    reason: str = ""


def _clean_address(value: str) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _resolve_targets(*, use_pinned_liq_fallback: bool) -> list[tuple[str, str]]:
    hft = _clean_address(HFT_EXECUTOR_ADDRESS) or PINNED_HFT_EXECUTOR
    liq = _clean_address(LIQUIDATION_EXECUTOR_ADDRESS)
    if not liq and use_pinned_liq_fallback:
        liq = PINNED_LIQUIDATION_EXECUTOR
    targets = [("HFT_EXECUTOR", hft)]
    if liq:
        targets.append(("LIQUIDATION_EXECUTOR", liq))
    return targets


def _rpc_url(cli_rpc_url: str = "") -> str:
    return _clean_address(cli_rpc_url) or _clean_address(os.environ.get("PRIMARY_READ_RPC_URL")) or _clean_address(EXACT_CALL_RPC_URL)


async def _check_contract(w3: AsyncWeb3, label: str, address: str) -> ContractCheck:
    if not Web3.is_address(address):
        return ContractCheck(label=label, address=address, ok=False, reason="invalid_address")
    checksum = Web3.to_checksum_address(address)
    try:
        code = await w3.eth.get_code(checksum)
    except Exception as exc:
        return ContractCheck(label=label, address=checksum, ok=False, reason=f"eth_getCode_failed:{type(exc).__name__}:{exc}")
    size = len(code or b"")
    return ContractCheck(
        label=label,
        address=checksum,
        ok=size > 0,
        bytecode_bytes=size,
        reason="bytecode_present" if size > 0 else "no_deployed_bytecode",
    )


async def verify_deployed_contracts(
    *,
    rpc_url: str = "",
    expected_chain_id: int = CHAIN_ID,
    use_pinned_liq_fallback: bool = True,
) -> tuple[bool, list[ContractCheck], str]:
    resolved_rpc = _rpc_url(rpc_url)
    if not resolved_rpc:
        return False, [], "missing_rpc_url"
    w3 = AsyncWeb3(AsyncHTTPProvider(resolved_rpc, request_kwargs={"timeout": 15}))
    try:
        chain_id = await w3.eth.chain_id
    except Exception as exc:
        return False, [], f"chain_id_failed:{type(exc).__name__}:{exc}"
    if int(chain_id) != int(expected_chain_id):
        return False, [], f"wrong_chain_id:{chain_id}:expected:{expected_chain_id}"

    targets = _resolve_targets(use_pinned_liq_fallback=use_pinned_liq_fallback)
    checks = await asyncio.gather(*(_check_contract(w3, label, address) for label, address in targets))
    ok = bool(checks) and all(check.ok for check in checks)
    return ok, list(checks), f"chain_id={chain_id} rpc={resolved_rpc}"


def _print_report(ok: bool, checks: Iterable[ContractCheck], detail: str) -> None:
    print("Omega V5 deployed-contract bytecode gate")
    print(detail)
    for check in checks:
        status = "PASS" if check.ok else "FAIL"
        print(
            f"{check.label}: {status} address={check.address} "
            f"bytecode_bytes={check.bytecode_bytes} reason={check.reason}"
        )
    print("VERDICT: INFRASTRUCTURE COMPATIBLE" if ok else "VERDICT: INFRASTRUCTURE INCOMPATIBLE")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify deployed bytecode for configured Omega executor contracts.")
    parser.add_argument("--rpc-url", default="", help="Override read RPC URL for eth_getCode checks.")
    parser.add_argument("--chain-id", type=int, default=CHAIN_ID, help="Expected chain ID, default Polygon 137.")
    parser.add_argument(
        "--no-pinned-liq-fallback",
        action="store_true",
        help="Skip LIQUIDATION_EXECUTOR_ADDRESS when the env/config value is empty instead of using the pinned fallback.",
    )
    args = parser.parse_args(argv)
    ok, checks, detail = asyncio.run(verify_deployed_contracts(
        rpc_url=args.rpc_url,
        expected_chain_id=args.chain_id,
        use_pinned_liq_fallback=not args.no_pinned_liq_fallback,
    ))
    _print_report(ok, checks, detail)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())