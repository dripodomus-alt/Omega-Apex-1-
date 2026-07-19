#!/usr/bin/env python3
# ==============================================================================
# liquidation_capital.py -- capital-source checks for liquidation candidates.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from web3 import Web3

from .adapter_registry import FlashSourceId, ZERO_ADDRESS, resolve_capital_source_adapter
from .config import FLASH_BASE_ASSETS, _env
from .flash_loan import AAVE_V3_POOL_POLYGON, BALANCER_VAULT_POLYGON
from .rpc_layer import TOKEN_ADDRESSES


_ERC20_BALANCE_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    }
]


@dataclass(frozen=True)
class CapitalSourceCheck:
    source_id: int
    source_name: str
    configured_onchain: bool
    adapter: str
    asset_supported: bool
    available_raw: int
    required_raw: int
    usable: bool
    reject_reason: str = ""

    def as_packet(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "configuredOnChain": self.configured_onchain,
            "adapter": self.adapter,
            "assetSupported": self.asset_supported,
            "availableRaw": str(self.available_raw),
            "requiredRaw": str(self.required_raw),
            "usable": self.usable,
            "rejectReason": self.reject_reason,
        }


def _source_supported_assets(source_id: int) -> set[str]:
    raw = _env(f"FLASH_SOURCE_{source_id}_ASSETS")
    if raw:
        return {item.strip() for item in raw.split(",") if item.strip()}
    return set(FLASH_BASE_ASSETS)


def _balance_of(token: str, holder: str) -> int:
    try:
        from . import rpc_layer
        if rpc_layer.w3 is None or not token or not holder:
            return 0
        contract = rpc_layer.w3.eth.contract(
            address=Web3.to_checksum_address(token),
            abi=_ERC20_BALANCE_ABI,
        )
        return int(contract.functions.balanceOf(Web3.to_checksum_address(holder)).call())
    except Exception:
        return 0


def _source_liquidity_holder(source_id: int) -> str:
    if source_id == int(FlashSourceId.AAVE_V3):
        return AAVE_V3_POOL_POLYGON
    if source_id == int(FlashSourceId.BALANCER_VAULT):
        return BALANCER_VAULT_POLYGON
    return _env(f"FLASH_SOURCE_{source_id}_LIQUIDITY_HOLDER")


def check_capital_source(source_id: int, debt_symbol: str, required_raw: int) -> CapitalSourceCheck:
    resolution = resolve_capital_source_adapter(source_id)
    adapter = resolution.adapter_address or ZERO_ADDRESS
    configured = bool(resolution.executable and adapter and adapter.lower() != ZERO_ADDRESS.lower())
    asset_supported = debt_symbol in _source_supported_assets(source_id)
    token = TOKEN_ADDRESSES.get(debt_symbol, "")
    holder = _source_liquidity_holder(source_id)
    available = _balance_of(token, holder) if configured and asset_supported and token and holder else 0

    reject = ""
    if not configured:
        reject = resolution.detail
    elif not asset_supported:
        reject = f"{debt_symbol} not in FLASH_SOURCE_{source_id}_ASSETS/FLASH_BASE_ASSETS"
    elif available < required_raw:
        reject = "availableRaw < debtToCoverRaw"

    return CapitalSourceCheck(
        source_id=source_id,
        source_name=FlashSourceId(source_id).name,
        configured_onchain=configured,
        adapter=adapter,
        asset_supported=asset_supported,
        available_raw=available,
        required_raw=required_raw,
        usable=configured and asset_supported and available >= required_raw,
        reject_reason=reject,
    )


def usable_capital_sources(debt_symbol: str, required_raw: int) -> list[CapitalSourceCheck]:
    return [
        check_capital_source(int(source_id), debt_symbol, required_raw)
        for source_id in FlashSourceId
    ]
