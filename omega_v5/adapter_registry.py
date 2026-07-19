#!/usr/bin/env python3
# ==============================================================================
# adapter_registry.py -- fail-closed capital-source adapter mapping.
#
# OmegaAtomicExecutor dispatches through adapterForSource[flashSource]. Its
# executeFlashArb address[] argument is the pool route, not a per-DEX adapter
# list. This module keeps that contract boundary explicit.
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable, Sequence

from web3 import Web3

from .config import EXECUTOR_CONTRACT, _env
from .flash_loan import FlashSource


ZERO_ADDRESS = "0x" + "00" * 20
SUPPORTED_ROUTE_PROTOCOLS = {
    "UniswapV2",
    "UniswapV3",
    "QuickSwapV3",
    "Algebra",
    "Curve",
    "Balancer",
}
ROUTE_POOL_KIND = {
    "UniswapV2": 1,
    "UniswapV3": 2,
    "QuickSwapV3": 3,
    "Algebra": 3,
    "Curve": 4,
    "Balancer": 5,
}


class FlashSourceId(IntEnum):
    AAVE_V3 = 0
    BALANCER_VAULT = 1
    V2_FLASH_SWAP = 2
    V3_FLASH_CALLBACK = 3


FLASH_SOURCE_ENV_KEYS = {
    FlashSourceId.AAVE_V3: "AAVE_V3_CAPITAL_ADAPTER",
    FlashSourceId.BALANCER_VAULT: "BALANCER_VAULT_CAPITAL_ADAPTER",
    FlashSourceId.V2_FLASH_SWAP: "V2_FLASH_SWAP_ADAPTER",
    FlashSourceId.V3_FLASH_CALLBACK: "V3_FLASH_CALLBACK_ADAPTER",
}

FLASH_SOURCE_ENV_ALIASES = {
    FlashSourceId.BALANCER_VAULT: ("BALANCER_V3_VAULT_CAPITAL_ADAPTER",),
}

FLASH_SOURCE_NAMES = {
    FlashSourceId.AAVE_V3: "Aave V3 capital adapter",
    FlashSourceId.BALANCER_VAULT: "Balancer Vault capital adapter",
    FlashSourceId.V2_FLASH_SWAP: "V2 flash-swap adapter",
    FlashSourceId.V3_FLASH_CALLBACK: "V3 flash-callback adapter",
}

ADAPTER_FOR_SOURCE_ABI = [
    {
        "name": "adapterForSource",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "flashSource", "type": "uint8"}],
        "outputs": [{"name": "", "type": "address"}],
    }
]
ROUTE_POOL_KIND_ABI = [
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


@dataclass(frozen=True)
class AdapterResolution:
    ok: bool
    adapters: list[str]
    missing_protocols: list[str]
    detail: str
    target_mode: str = "capital_source_adapter"
    executable: bool = False
    flash_source_id: int | None = None
    adapter_address: str = ""


class AdapterSemanticError(RuntimeError):
    """Raised when source adapters or route pools cannot be proven executable."""


def _valid_address(value: str) -> bool:
    return bool(value) and Web3.is_address(value)


def _normalise_source(source: FlashSource | str | int) -> FlashSourceId:
    if isinstance(source, FlashSourceId):
        return source
    if isinstance(source, int):
        return FlashSourceId(source)
    if isinstance(source, FlashSource):
        return (
            FlashSourceId.AAVE_V3
            if source == FlashSource.AAVE
            else FlashSourceId.BALANCER_VAULT
        )
    source_text = str(source).upper()
    if source_text in {"AAVE", "AAVE_V3", "0"}:
        return FlashSourceId.AAVE_V3
    if source_text in {"BALANCER", "BALANCER_VAULT", "1"}:
        return FlashSourceId.BALANCER_VAULT
    if source_text in {"V2_FLASH_SWAP", "2"}:
        return FlashSourceId.V2_FLASH_SWAP
    if source_text in {"V3_FLASH_CALLBACK", "3"}:
        return FlashSourceId.V3_FLASH_CALLBACK
    raise AdapterSemanticError(f"unsupported flash source: {source}")


def flash_source_id(source: FlashSource | str | int) -> int:
    return int(_normalise_source(source))


def configured_adapters() -> dict[str, str]:
    """Return locally configured capital-source adapter addresses."""
    adapters: dict[str, str] = {}
    for source_id, env_key in FLASH_SOURCE_ENV_KEYS.items():
        keys = (env_key, *FLASH_SOURCE_ENV_ALIASES.get(source_id, ()), f"FLASH_SOURCE_{int(source_id)}_ADAPTER")
        for key in keys:
            value = _env(key)
            if _valid_address(value):
                adapters[key] = Web3.to_checksum_address(value)
                break
    return adapters


def _code_status(address: str) -> tuple[bool, str]:
    try:
        from . import rpc_layer
    except Exception:
        return True, "RPC unavailable; bytecode check deferred"
    if rpc_layer.w3 is None or not rpc_layer.RPC_LIVE:
        return True, "RPC unavailable; bytecode check deferred"
    try:
        code = rpc_layer.w3.eth.get_code(Web3.to_checksum_address(address)).hex()
    except Exception as exc:
        return False, f"adapter bytecode read failed: {exc}"
    if code in ("", "0x"):
        return False, f"adapter has no bytecode: {address}"
    return True, "adapter bytecode present"


def _read_onchain_adapter(source_id: FlashSourceId) -> tuple[str, str]:
    try:
        from . import rpc_layer
    except Exception as exc:
        return "", f"RPC module unavailable: {exc}"
    if rpc_layer.w3 is None or not rpc_layer.RPC_LIVE:
        return "", "RPC unavailable; cannot read executor adapterForSource"
    if not EXECUTOR_CONTRACT:
        return "", "EXECUTOR_CONTRACT_ADDR missing; cannot read adapterForSource"
    try:
        contract = rpc_layer.w3.eth.contract(
            address=Web3.to_checksum_address(EXECUTOR_CONTRACT),
            abi=ADAPTER_FOR_SOURCE_ABI,
        )
        value = contract.functions.adapterForSource(int(source_id)).call()
    except Exception as exc:
        return "", f"adapterForSource({int(source_id)}) read failed: {exc}"
    if not _valid_address(value) or value.lower() == ZERO_ADDRESS.lower():
        return "", f"adapterForSource({int(source_id)}) is unset"
    return Web3.to_checksum_address(value), f"adapterForSource({int(source_id)}) configured on executor"


def resolve_capital_source_adapter(source: FlashSource | str | int) -> AdapterResolution:
    source_id = _normalise_source(source)
    env_key = FLASH_SOURCE_ENV_KEYS[source_id]
    configured = ""
    configured_key = env_key
    for key in (env_key, *FLASH_SOURCE_ENV_ALIASES.get(source_id, ()), f"FLASH_SOURCE_{int(source_id)}_ADAPTER"):
        value = _env(key)
        if value:
            configured = value
            configured_key = key
            break
    detail_parts: list[str] = []

    if _valid_address(configured):
        adapter = Web3.to_checksum_address(configured)
        detail_parts.append(f"{configured_key} configured locally")
    else:
        adapter, detail = _read_onchain_adapter(source_id)
        detail_parts.append(detail)

    if not adapter:
        return AdapterResolution(
            ok=False,
            adapters=[],
            missing_protocols=[env_key],
            detail="; ".join(detail_parts),
            executable=False,
            flash_source_id=int(source_id),
        )

    code_ok, code_detail = _code_status(adapter)
    detail_parts.append(code_detail)
    if not code_ok:
        return AdapterResolution(
            ok=False,
            adapters=[adapter],
            missing_protocols=[],
            detail="; ".join(detail_parts),
            executable=False,
            flash_source_id=int(source_id),
            adapter_address=adapter,
        )

    return AdapterResolution(
        ok=True,
        adapters=[adapter],
        missing_protocols=[],
        detail="; ".join(detail_parts),
        executable=True,
        flash_source_id=int(source_id),
        adapter_address=adapter,
    )


def validate_route_shape(path: Sequence[str], pool_addresses: Sequence[str]) -> None:
    if len(path) < 3:
        raise AdapterSemanticError("route path must contain at least token_in, mid_token, token_out")
    if path[0] != path[-1]:
        raise AdapterSemanticError("canonical route must close as A -> ... -> A")
    if len(pool_addresses) != len(path) - 1:
        raise AdapterSemanticError(
            f"pool address count {len(pool_addresses)} does not match route hops {len(path) - 1}"
        )
    if len(set(address.lower() for address in pool_addresses)) != len(pool_addresses):
        raise AdapterSemanticError("route reuses the same pool address")
    for address in pool_addresses:
        if not _valid_address(address) or address.lower() == ZERO_ADDRESS.lower():
            raise AdapterSemanticError(f"invalid route pool address: {address}")


def validate_route_protocols(protocol_seq: Sequence[str]) -> None:
    unsupported = sorted({protocol for protocol in protocol_seq if protocol not in SUPPORTED_ROUTE_PROTOCOLS})
    if unsupported:
        raise AdapterSemanticError(
            "route contains protocols without executable source-adapter swap support: "
            + ", ".join(unsupported)
        )


def resolve_route_pool_addresses(
    pool_sequence: Sequence[str],
    pools: dict | None = None,
    explicit_addresses: Sequence[str] | None = None,
) -> list[str]:
    if explicit_addresses:
        return [Web3.to_checksum_address(address) for address in explicit_addresses]

    pools = pools or {}
    targets: list[str] = []
    missing: list[str] = []
    for pool_id in pool_sequence:
        pool = pools.get(pool_id)
        if pool is None:
            try:
                from .rpc_layer import DEEP_POOL_REGISTRY
                pool = DEEP_POOL_REGISTRY.get(pool_id)
            except Exception:
                pool = None
        address = (pool or {}).get("address", "")
        if _valid_address(address):
            targets.append(Web3.to_checksum_address(address))
        else:
            missing.append(pool_id)

    if missing:
        raise AdapterSemanticError(f"missing live pool addresses for: {', '.join(missing)}")
    return targets


def require_executable_source_adapter(source: FlashSource | str | int) -> AdapterResolution:
    resolution = resolve_capital_source_adapter(source)
    if not resolution.ok or not resolution.executable:
        raise AdapterSemanticError(resolution.detail)
    return resolution


def validate_onchain_route_pool_kinds(
    adapter_address: str,
    pool_addresses: Sequence[str],
    protocol_seq: Sequence[str],
) -> None:
    """Fail before signing if the adapter route-kind allowlist cannot execute the route."""
    try:
        from . import rpc_layer
    except Exception:
        return
    if rpc_layer.w3 is None or not rpc_layer.RPC_LIVE:
        return
    if len(pool_addresses) != len(protocol_seq):
        raise AdapterSemanticError(
            f"pool/protocol length mismatch: pools={len(pool_addresses)} protocols={len(protocol_seq)}"
        )
    contract = rpc_layer.w3.eth.contract(
        address=Web3.to_checksum_address(adapter_address),
        abi=ROUTE_POOL_KIND_ABI,
    )
    try:
        enforced = bool(contract.functions.routePoolKindEnforced().call())
    except Exception as exc:
        raise AdapterSemanticError(f"routePoolKindEnforced read failed: {exc}") from exc
    if not enforced:
        return

    missing: list[str] = []
    mismatched: list[str] = []
    for pool, protocol in zip(pool_addresses, protocol_seq):
        expected = ROUTE_POOL_KIND.get(protocol)
        if expected is None:
            raise AdapterSemanticError(f"unsupported executable route protocol: {protocol}")
        try:
            actual = int(contract.functions.routePoolKind(Web3.to_checksum_address(pool)).call())
        except Exception as exc:
            raise AdapterSemanticError(f"routePoolKind({pool}) read failed: {exc}") from exc
        if actual == 0:
            missing.append(pool)
        elif actual != expected:
            mismatched.append(f"{pool}: expected {expected} for {protocol}, got {actual}")
    if missing:
        raise AdapterSemanticError(
            "adapter routePoolKind unset for live route pool(s): " + ", ".join(missing)
        )
    if mismatched:
        raise AdapterSemanticError(
            "adapter routePoolKind mismatch: " + "; ".join(mismatched)
        )


def configured_source_report(sources: Iterable[int] = range(4)) -> list[AdapterResolution]:
    return [resolve_capital_source_adapter(int(source)) for source in sources]
