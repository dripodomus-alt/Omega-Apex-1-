#!/usr/bin/env python3
# ==============================================================================
# payload_envelope.py -- domain-separated execution envelope metadata.
# ==============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from web3 import Web3

from .config import CHAIN_ID


ENVELOPE_DOMAINS = {
    "ARBITRAGE_C1": "omega_v5.envelope.arbitrage_c1.v1",
    "ARBITRAGE_C2": "omega_v5.envelope.arbitrage_c2.v1",
    "LIQUIDATION": "omega_v5.envelope.liquidation.v1",
}


@dataclass(frozen=True)
class PayloadEnvelope:
    envelope_id: str
    domain: str
    kind: str
    chain_id: int
    target: str
    selector: str
    calldata_hash: str
    parent_envelope_id: str = ""
    created_ns: int = field(default_factory=time.time_ns)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "domain": self.domain,
            "kind": self.kind,
            "chain_id": self.chain_id,
            "target": self.target,
            "selector": self.selector,
        "calldata_builder": "python",
        "onchain_engine": "solidity",
            "calldata_hash": self.calldata_hash,
            "parent_envelope_id": self.parent_envelope_id,
            "created_ns": self.created_ns,
            "metadata": dict(self.metadata),
        }


def _calldata_bytes(calldata: str) -> bytes:
    if not isinstance(calldata, str) or not calldata.startswith("0x"):
        raise ValueError("calldata must be a 0x-prefixed hex string")
    return bytes.fromhex(calldata[2:])


def payload_selector(calldata: str) -> str:
    data = _calldata_bytes(calldata)
    if len(data) < 4:
        raise ValueError("calldata must include a 4-byte selector")
    return "0x" + data[:4].hex()


def build_payload_envelope(
    *,
    kind: str,
    target: str,
    calldata: str,
    metadata: dict[str, Any] | None = None,
    parent_envelope_id: str = "",
    unique_salt: str = "",
) -> PayloadEnvelope:
    domain = ENVELOPE_DOMAINS.get(kind)
    if not domain:
        raise ValueError(f"unsupported payload envelope kind: {kind}")
    if not Web3.is_address(target):
        raise ValueError(f"invalid payload target: {target}")
    calldata_hash = Web3.keccak(_calldata_bytes(calldata)).hex()
    selector = payload_selector(calldata)
    created_ns = time.time_ns()
    seed = "|".join([
        domain,
        str(CHAIN_ID),
        Web3.to_checksum_address(target),
        selector,
        calldata_hash,
        parent_envelope_id,
        str(created_ns),
        unique_salt,
    ])
    envelope_id = Web3.keccak(text=seed).hex()
    return PayloadEnvelope(
        envelope_id=envelope_id,
        domain=domain,
        kind=kind,
        chain_id=CHAIN_ID,
        target=Web3.to_checksum_address(target),
        selector=selector,
        calldata_hash=calldata_hash,
        parent_envelope_id=parent_envelope_id,
        created_ns=created_ns,
        metadata=metadata or {},
    )
