#!/usr/bin/env python3
# ==============================================================================
# polygonscan_verification.py -- Chain 137 source-verification audit helper.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable

from .config import ETHERSCAN_API_KEY, ETHERSCAN_API_URL, EXECUTOR_CONTRACT, LIQUIDATION_EXECUTOR_ADDRESS, _env


CHAIN_ID = "137"


@dataclass(frozen=True)
class VerificationTarget:
    name: str
    address: str


def default_targets() -> list[VerificationTarget]:
    return [
        VerificationTarget("OmegaAtomicExecutor", EXECUTOR_CONTRACT),
        VerificationTarget("OmegaLiquidationExecutor", LIQUIDATION_EXECUTOR_ADDRESS),
        VerificationTarget("OmegaAaveV3CapitalSourceAdapter", _env("AAVE_V3_CAPITAL_ADAPTER")),
        VerificationTarget("OmegaBalancerCapitalSourceAdapter", _env("BALANCER_VAULT_CAPITAL_ADAPTER")),
        VerificationTarget("OmegaAaveV3LiquidationAdapter", _env("AAVE_V3_LIQUIDATION_ADAPTER")),
    ]


def _api_key() -> str:
    return (
        ETHERSCAN_API_KEY
        or _env("ETHERSCAN_API_KEY")
        or _env("POLYGONSCAN_API_KEY")
        or os.environ.get("ETHERSCAN_API_KEY", "")
        or os.environ.get("POLYGONSCAN_API_KEY", "")
    )


def _fetch_source_status(address: str, api_key: str) -> dict:
    query = urllib.parse.urlencode({
        "chainid": CHAIN_ID,
        "module": "contract",
        "action": "getsourcecode",
        "address": address,
        "apikey": api_key,
    })
    with urllib.request.urlopen(f"{ETHERSCAN_API_URL}?{query}", timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def audit(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Polygonscan/Etherscan V2 source verification")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--delay-seconds", type=float, default=0.45, help="Delay between API calls to avoid free-tier throttling")
    args = parser.parse_args(list(argv) if argv is not None else None)

    api_key = _api_key()
    if not api_key:
        print("polygonscan_verification=FAIL reason=missing ETHERSCAN_API_KEY/POLYGONSCAN_API_KEY")
        return 1

    rows: list[dict] = []
    failed = False
    for index, target in enumerate(default_targets()):
        if index and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)
        if not target.address:
            rows.append({
                "name": target.name,
                "address": "",
                "verified": False,
                "detail": "address_missing",
            })
            failed = True
            continue
        try:
            payload = _fetch_source_status(target.address, api_key)
            result = payload.get("result") or [{}]
            if isinstance(result, str):
                failed = True
                rows.append({
                    "name": target.name,
                    "address": target.address,
                    "verified": False,
                    "api_status": payload.get("status"),
                    "api_message": payload.get("message"),
                    "detail": result,
                })
                continue
            item = result[0] if isinstance(result, list) and result else {}
            if not isinstance(item, dict):
                failed = True
                rows.append({
                    "name": target.name,
                    "address": target.address,
                    "verified": False,
                    "api_status": payload.get("status"),
                    "api_message": payload.get("message"),
                    "detail": "unexpected_result_shape",
                })
                continue
            source = str(item.get("SourceCode") or "").strip()
            verified = bool(source)
            row = {
                "name": target.name,
                "address": target.address,
                "verified": verified,
                "api_status": payload.get("status"),
                "api_message": payload.get("message"),
                "contract_name": item.get("ContractName") or "",
                "compiler": item.get("CompilerVersion") or "",
                "optimization_used": item.get("OptimizationUsed") or "",
                "runs": item.get("Runs") or "",
            }
            if not verified:
                failed = True
            rows.append(row)
        except Exception as exc:
            failed = True
            rows.append({
                "name": target.name,
                "address": target.address,
                "verified": False,
                "detail": f"{type(exc).__name__}: {exc}",
            })

    if args.json:
        print(json.dumps({"ok": not failed, "chain_id": int(CHAIN_ID), "rows": rows}, indent=2))
    else:
        for row in rows:
            print(
                f"name={row['name']} address={row['address'] or '<missing>'} "
                f"verified={row['verified']} "
                f"contract={row.get('contract_name', '') or '<empty>'} "
                f"compiler={row.get('compiler', '') or '<empty>'}"
            )
        print(f"polygonscan_verification={'PASS' if not failed else 'FAIL'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(audit())
