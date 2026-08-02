#!/usr/bin/env python3
# ==============================================================================
# wallet_config_verification.py -- gas-wallet and signing config readiness check.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import time
from decimal import Decimal
from typing import Any

from web3 import Web3

from .config import (
    BROADCAST_RPC_URL,
    CHAIN_ID,
    EXECUTOR_CONTRACT,
    MIN_WALLET_GAS_BUFFER_POL,
    OWNER_ADDRESS,
    PRIMARY_READ_RPC_URL,
    PRIVATE_KEY,
)
from .flash_loan import current_pol_price_usd
from .gas_oracle import polygon_gas_quote
from .paths import output_path
from .runtime_control import runtime_mode


WALLET_CONFIG_JSON_PATH = output_path("wallet_config_latest.json")


def _mask_address(address: str) -> str:
    return f"{address[:6]}...{address[-4:]}" if address and len(address) >= 12 else address


def _wallet_from_private_key() -> tuple[str, str]:
    if not PRIVATE_KEY:
        return "", "missing"
    try:
        from eth_account import Account

        return Account.from_key(PRIVATE_KEY).address, "valid"
    except Exception as exc:
        return "", f"invalid:{type(exc).__name__}"


def _probe_w3() -> tuple[Any | None, str]:
    for url in (BROADCAST_RPC_URL, PRIMARY_READ_RPC_URL):
        if not url:
            continue
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 5}))
            if int(w3.eth.chain_id) == CHAIN_ID:
                host = url.split("/")[2] if "//" in url else url
                return w3, host
        except Exception:
            continue
    return None, ""


def wallet_config_status(*, mode: str | None = None, probe_balance: bool = True) -> dict[str, Any]:
    selected_mode = (mode or runtime_mode() or "dry_run").lower()
    wallet, private_key_status = _wallet_from_private_key()
    owner_matches = True
    if OWNER_ADDRESS and wallet and Web3.is_address(OWNER_ADDRESS):
        owner_matches = Web3.to_checksum_address(OWNER_ADDRESS) == Web3.to_checksum_address(wallet)

    native_balance_pol = Decimal("0")
    balance_source = "not_probed"
    if probe_balance and wallet:
        w3, source = _probe_w3()
        if w3 is not None:
            try:
                native_balance_pol = Decimal(str(w3.eth.get_balance(Web3.to_checksum_address(wallet)))) / Decimal("1e18")
                balance_source = source
            except Exception as exc:
                balance_source = f"balance_probe_failed:{type(exc).__name__}"
        else:
            balance_source = "rpc_unavailable"

    pol_price, pol_price_source = current_pol_price_usd()
    quote = polygon_gas_quote()
    estimated_liquidation_gas_pol = Decimal("900000") * quote.max_fee_gwei * Decimal("1e-9")
    checks = {
        "private_key_valid": private_key_status == "valid",
        "wallet_present": bool(wallet),
        "executor_contract_configured": bool(EXECUTOR_CONTRACT and Web3.is_address(EXECUTOR_CONTRACT)),
        "owner_matches_wallet_or_unset": owner_matches,
        "gas_wallet_has_min_buffer": (
            native_balance_pol >= MIN_WALLET_GAS_BUFFER_POL
            if probe_balance and wallet and balance_source not in {"not_probed", "rpc_unavailable"}
            else selected_mode != "live"
        ),
    }
    if selected_mode != "live":
        checks["private_key_valid"] = True if not PRIVATE_KEY else checks["private_key_valid"]
        checks["wallet_present"] = True if not PRIVATE_KEY else checks["wallet_present"]

    status = {
        "ok": all(checks.values()),
        "mode": selected_mode,
        "updated_at": int(time.time()),
        "chain_id": CHAIN_ID,
        "wallet": _mask_address(wallet),
        "wallet_address": wallet,
        "private_key_status": private_key_status,
        "owner_address": _mask_address(OWNER_ADDRESS),
        "owner_matches_wallet_or_unset": owner_matches,
        "executor_contract": _mask_address(EXECUTOR_CONTRACT),
        "native_gas_asset": "POL",
        "gas_payer": "user_wallet",
        "native_balance_pol": str(native_balance_pol),
        "native_balance_usd": str(native_balance_pol * pol_price),
        "min_wallet_gas_buffer_pol": str(MIN_WALLET_GAS_BUFFER_POL),
        "balance_source": balance_source,
        "pol_price_usd": str(pol_price),
        "pol_price_source": pol_price_source,
        "gas_quote": {
            "source": quote.source,
            "tier": quote.tier,
            "max_fee_gwei": str(quote.max_fee_gwei),
            "priority_fee_gwei": str(quote.priority_fee_gwei),
        },
        "estimated_liquidation_gas_pol": str(estimated_liquidation_gas_pol),
        "estimated_liquidation_gas_usd": str(estimated_liquidation_gas_pol * pol_price),
        "checks": checks,
    }
    return status


def write_wallet_config_status(status: dict[str, Any]) -> None:
    WALLET_CONFIG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    WALLET_CONFIG_JSON_PATH.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify wallet/signing/gas configuration.")
    parser.add_argument("--mode", choices=["dry_run", "live"], default=None)
    parser.add_argument("--no-balance-probe", action="store_true")
    args = parser.parse_args()
    status = wallet_config_status(mode=args.mode, probe_balance=not args.no_balance_probe)
    write_wallet_config_status(status)
    print(f"wallet_config={'PASS' if status['ok'] else 'FAIL'} mode={status['mode']} wallet={status['wallet'] or 'missing'} gas_payer=user_wallet path={WALLET_CONFIG_JSON_PATH}")
    for name, ok in status["checks"].items():
        print(f"{name}={'PASS' if ok else 'FAIL'}")
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
