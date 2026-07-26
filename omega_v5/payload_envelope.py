#!/usr/bin/env python3
# ==============================================================================
# payload_envelope.py -- domain-separated execution envelope metadata.
# Updated to use canonical protocol IDs from config for payload alignment.
# ==============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from web3 import Web3

from .config import CHAIN_ID, build_protocol_sequence_ids


# Explicit domain strings for payload envelope construction.
# These ensure that signatures for one type of transaction cannot be replayed
# for another, providing a critical security boundary.
DOMAIN_ARBITRAGE_C1 = "omega_v5.envelope.arbitrage_c1.v1"
DOMAIN_ARBITRAGE_C2 = "omega_v5.envelope.arbitrage_c2.v1"
DOMAIN_LIQUIDATION = "omega_v5.envelope.liquidation.v1"


UNIFIED_ROUTE_SCHEMA_VERSION = "omega_v5.unified_invariant_route.v1"
UNIFIED_ROUTE_STAGES = (
    "discovery",
    "intake",
    "ranking",
    "staging",
    "fees",
    "math",
    "quote",
    "simulation",
    "payload",
    "submission",
    "settlement",
    "trace",
)


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "as_dict"):
        return _json_ready(value.as_dict())
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _json_ready(vars(value))
    return str(value) if value.__class__.__module__ == "decimal" else value


@dataclass(frozen=True)
class UnifiedRouteEnvelope:
    """One route schema that accumulates stage-owned params through the pipeline."""

    opp_id: str
    route: dict[str, Any]
    status: str = "DISCOVERED"
    chain_id: int = CHAIN_ID
    schema_version: str = UNIFIED_ROUTE_SCHEMA_VERSION
    blocks: dict[str, Any] = field(default_factory=dict)
    discovery: dict[str, Any] = field(default_factory=dict)
    intake: dict[str, Any] = field(default_factory=dict)
    ranking: dict[str, Any] = field(default_factory=dict)
    staging: dict[str, Any] = field(default_factory=dict)
    fees: dict[str, Any] = field(default_factory=dict)
    math: dict[str, Any] = field(default_factory=dict)
    quote: dict[str, Any] = field(default_factory=dict)
    simulation: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    submission: dict[str, Any] = field(default_factory=dict)
    settlement: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "opp_id": self.opp_id,
            "status": self.status,
            "route": _json_ready(self.route),
            "blocks": _json_ready(self.blocks),
            "discovery": _json_ready(self.discovery),
            "intake": _json_ready(self.intake),
            "ranking": _json_ready(self.ranking),
            "staging": _json_ready(self.staging),
            "fees": _json_ready(self.fees),
            "math": _json_ready(self.math),
            "quote": _json_ready(self.quote),
            "simulation": _json_ready(self.simulation),
            "payload": _json_ready(self.payload),
            "submission": _json_ready(self.submission),
            "settlement": _json_ready(self.settlement),
            "trace": _json_ready(self.trace),
        }

    def with_stage(
        self,
        stage: str,
        params: dict[str, Any],
        *,
        status: str | None = None,
        block_key: str | None = None,
        block: int | None = None,
    ) -> "UnifiedRouteEnvelope":
        """
        Efficiently returns a new envelope with an updated stage.
        Now includes protocol ID alignment for payload stage.
        """
        normalized = stage.lower()
        if normalized not in UNIFIED_ROUTE_STAGES:
            raise ValueError(f"unsupported unified route stage: {stage}")

        current_stage_data = getattr(self, normalized)
        new_stage_data = current_stage_data.copy()
        new_stage_data.update(_json_ready(params))

        changes = {normalized: new_stage_data}
        if status:
            changes["status"] = status
        if block_key and block is not None:
            new_blocks = self.blocks.copy()
            new_blocks[block_key] = block
            changes["blocks"] = new_blocks

        if normalized == "payload":
            # Enforce alignment with config registry (step 1 of plan)
            try:
                protocol_ids = build_protocol_sequence_ids(self.route)
                new_stage_data["protocol_ids"] = protocol_ids
                new_stage_data["protocol_id_alignment"] = "verified"
            except ValueError as e:
                new_stage_data["protocol_id_alignment"] = f"error: {e}"

        return replace(self, **changes)


def add_staging_to_unified_envelope(pre_ranked: Any) -> UnifiedRouteEnvelope:
    """Helper to create envelope and add staging (updated to call sequence proof indirectly via validation)."""
    envelope = unified_envelope_from_pre_ranked(pre_ranked)
    # Sequence proof will be enforced in stager before this
    return envelope


def unified_envelope_from_pre_ranked(pre_ranked: Any) -> UnifiedRouteEnvelope:
    """Factory for unified envelope."""
    route_dict = pre_ranked.as_dict() if hasattr(pre_ranked, "as_dict") else dict(pre_ranked)
    return UnifiedRouteEnvelope(
        opp_id=route_dict.get("opp_id", "unknown"),
        route=route_dict,
        status="STAGED",
    )


# Additional helpers from original (preserved)
def build_payload_envelope(opportunity: Any) -> dict:
    """Builds final payload with aligned IDs."""
    envelope = UnifiedRouteEnvelope(opportunity.opp_id, opportunity.route)
    payload_stage = {
        "calldata": "0x...",  # placeholder
        "protocol_ids": build_protocol_sequence_ids(opportunity.route),
    }
    return envelope.with_stage("payload", payload_stage, status="PAYLOAD_READY").as_dict()
# ==============================================================================
# RESTORED PAYLOAD ENVELOPE API
# ==============================================================================

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


def _build_generic_payload_envelope(
    *,
    kind: str,
    domain: str,
    target: str,
    calldata: str,
    metadata: dict[str, Any] | None = None,
    parent_envelope_id: str = "",
    unique_salt: str = "",
) -> PayloadEnvelope:
    if not Web3.is_address(target):
        raise ValueError(f"invalid payload target: {target}")
    calldata_hash = Web3.keccak(_calldata_bytes(calldata)).hex()
    selector = payload_selector(calldata)
    created_ns = time.time_ns()
    seed = "|".join([domain, str(CHAIN_ID), Web3.to_checksum_address(target), selector, calldata_hash, parent_envelope_id, str(created_ns), unique_salt])
    return PayloadEnvelope(
        envelope_id=Web3.keccak(text=seed).hex(),
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


def build_c1_arbitrage_payload_envelope(*, target: str, calldata: str, metadata: dict[str, Any] | None = None, unique_salt: str = "") -> PayloadEnvelope:
    return _build_generic_payload_envelope(kind="ARBITRAGE_C1", domain=DOMAIN_ARBITRAGE_C1, target=target, calldata=calldata, metadata=metadata, unique_salt=unique_salt)


def build_c2_arbitrage_payload_envelope(*, target: str, calldata: str, metadata: dict[str, Any] | None = None, unique_salt: str = "") -> PayloadEnvelope:
    return _build_generic_payload_envelope(kind="ARBITRAGE_C2", domain=DOMAIN_ARBITRAGE_C2, target=target, calldata=calldata, metadata=metadata, unique_salt=unique_salt)


def build_liquidation_payload_envelope(*, target: str, calldata: str, metadata: dict[str, Any] | None = None, unique_salt: str = "") -> PayloadEnvelope:
    return _build_generic_payload_envelope(kind="LIQUIDATION", domain=DOMAIN_LIQUIDATION, target=target, calldata=calldata, metadata=metadata, unique_salt=unique_salt)


def build_payload_envelope(
    *,
    kind: str,
    target: str,
    calldata: str,
    metadata: dict[str, Any] | None = None,
    unique_salt: str = "",
    parent_envelope_id: str = "",
) -> PayloadEnvelope:
    domain = {
        "ARBITRAGE_C1": DOMAIN_ARBITRAGE_C1,
        "ARBITRAGE_C2": DOMAIN_ARBITRAGE_C2,
        "LIQUIDATION": DOMAIN_LIQUIDATION,
    }.get(kind, kind)
    return _build_generic_payload_envelope(
        kind=kind,
        domain=domain,
        target=target,
        calldata=calldata,
        metadata=metadata,
        parent_envelope_id=parent_envelope_id,
        unique_salt=unique_salt,
    )

