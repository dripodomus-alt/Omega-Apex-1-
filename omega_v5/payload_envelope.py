#!/usr/bin/env python3
# ==============================================================================
# payload_envelope.py -- domain-separated execution envelope metadata.
# ==============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any

from web3 import Web3

from .config import CHAIN_ID


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

        This method avoids full object reconstruction by using `dataclasses.replace`
        and only copying the dictionaries that are being modified. This is
        significantly more performant than the previous `as_dict()` and
        re-initialization pattern.
        """
        normalized = stage.lower()
        if normalized not in UNIFIED_ROUTE_STAGES:
            raise ValueError(f"unsupported unified route stage: {stage}")

        # Create a mutable copy of the target stage's data
        current_stage_data = getattr(self, normalized)
        new_stage_data = current_stage_data.copy()
        new_stage_data.update(_json_ready(params))

        # Prepare the changes for dataclasses.replace
        changes = {normalized: new_stage_data}
        if status:
            changes["status"] = status
        if block_key:
            # Create a mutable copy of the blocks dictionary to update it
            new_blocks = self.blocks.copy()
            new_blocks[block_key] = block
            changes["blocks"] = new_blocks

        # Return a new, updated, immutable instance
        return replace(self, **changes)


def build_unified_route_envelope(
    *,
    opp_id: str,
    path: tuple[str, ...] | list[str],
    pool_sequence: tuple[str, ...] | list[str],
    protocol_seq: tuple[str, ...] | list[str],
    discovery_block: int = 0,
    status: str = "DISCOVERED",
    discovery: dict[str, Any] | None = None,
    intake: dict[str, Any] | None = None,
) -> UnifiedRouteEnvelope:
    route = {
        "path": [str(item) for item in path],
        "pool_sequence": [str(item) for item in pool_sequence],
        "protocol_seq": [str(item) for item in protocol_seq],
    }
    if len(route["pool_sequence"]) != max(0, len(route["path"]) - 1):
        raise ValueError("unified route schema mismatch: pool_sequence must match route hops")
    if len(route["protocol_seq"]) != len(route["pool_sequence"]):
        raise ValueError("unified route schema mismatch: protocol_seq must match pool_sequence")
    return UnifiedRouteEnvelope(
        opp_id=str(opp_id),
        route=route,
        status=status,
        blocks={"discovered": int(discovery_block or 0)},
        discovery=discovery or {},
        intake=intake or {},
    )


def unified_envelope_from_pre_ranked(route: Any) -> UnifiedRouteEnvelope:
    return build_unified_route_envelope(
        opp_id=str(getattr(route, "opp_id", "")),
        path=getattr(route, "path", ()),
        pool_sequence=getattr(route, "pool_sequence", ()),
        protocol_seq=getattr(route, "protocol_seq", ()),
        discovery_block=int(getattr(route, "discovery_block", 0) or 0),
        discovery={
            "liquidity_keys": list(getattr(route, "liquidity_keys", ())),
            "route_class_seq": list(getattr(route, "route_class_seq", ())),
            "edge_entries": list(getattr(route, "edge_entries", ())),
            "identity": getattr(route, "identity", {}),
        },
        intake={
            "approximate_gross_rate": getattr(route, "approximate_gross_rate", ""),
            "approximate_raw_delta_usd": getattr(route, "approximate_raw_delta_usd", ""),
            "approximate_raw_delta_bps": getattr(route, "approximate_raw_delta_bps", ""),
        },
    )

def unified_envelope_from_live_opportunity(op: Any) -> UnifiedRouteEnvelope:
    envelope = build_unified_route_envelope(
        opp_id=str(getattr(op, "opp_id", "")),
        path=getattr(op, "path", ()),
        pool_sequence=getattr(op, "pool_sequence", ()),
        protocol_seq=getattr(op, "protocol_seq", ()),
        discovery_block=int(getattr(op, "block_detected", 0) or 0),
        status="RANKED",
    )
    profitability = getattr(op, "profitability", None)
    return envelope.with_stage(
        "ranking",
        {
            "gross_rate": getattr(op, "gross_rate", ""),
            "gross_out_usd": getattr(op, "gross_out_usd", ""),
            "metadata": getattr(op, "metadata", {}),
            "net_profit_usd": getattr(profitability, "net_profit_usd", ""),
        },
        status="RANKED",
    )


def _decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _fee_ledger_from_net_formula(staged_row: dict[str, Any], math_params: dict[str, Any]) -> dict[str, Any]:
    normalization = staged_row.get("usd_normalization", {}) if isinstance(staged_row, dict) else {}
    calibration_id = (
        staged_row.get("calibration_id")
        or normalization.get("calibration_id")
        or "omega_v5.nusd.v1:unresolved"
    )
    component_keys = (
        ("flashloan_fee", "flashloan_fee_usd"),
        ("gas_fee", "gas_cost_usd"),
        ("relay_fee", "relay_or_private_submit_cost_usd"),
        ("risk_buffer", "risk_buffer_usd"),
        ("slippage_buffer", "extra_slippage_buffer_usd"),
        ("pool_hop_fees", "hop_fees_usd"),
        ("price_impact_cost", "price_impact_cost_usd"),
        ("adapter_fee", "adapter_fee_usd"),
        ("builder_tip", "builder_fee_usd"),
        ("approval_fee", "approval_fee_usd"),
    )
    components: list[dict[str, Any]] = []
    total = Decimal("0")
    for component, source_key in component_keys:
        if source_key not in math_params:
            continue
        fee = _decimal_or_zero(math_params.get(source_key))
        total += fee
        components.append({
            "fee_component": component,
            "source_key": source_key,
            "normalized_unit": "NUSD",
            "fee_usd": str(fee),
            "block_number": staged_row.get("current_block"),
            "calibration_id": calibration_id,
            "conversion_status": "normalized_usd_from_math",
        })
    return {
        "schema_version": "omega_v5.fee_ledger.v1",
        "calibration_id": calibration_id,
        "normalized_unit": "NUSD",
        "total_fee_usd": str(total),
        "components": components,
        "component_count": len(components),
        "alignment_rule": "route_math_sums_only_normalized_fee_usd",
    }


def _with_opp_id(envelope: UnifiedRouteEnvelope, opp_id: str) -> UnifiedRouteEnvelope:
    if not opp_id or opp_id == envelope.opp_id:
        return envelope
    return UnifiedRouteEnvelope(
        opp_id=opp_id,
        route=envelope.route,
        status=envelope.status,
        chain_id=envelope.chain_id,
        schema_version=envelope.schema_version,
        blocks=envelope.blocks,
        discovery=envelope.discovery,
        intake=envelope.intake,
        ranking=envelope.ranking,
        staging=envelope.staging,
        fees=envelope.fees,
        math=envelope.math,
        quote=envelope.quote,
        simulation=envelope.simulation,
        payload=envelope.payload,
        submission=envelope.submission,
        settlement=envelope.settlement,
        trace=envelope.trace,
    )


def add_staging_to_unified_envelope(
    envelope: UnifiedRouteEnvelope,
    staged_row: dict[str, Any],
) -> UnifiedRouteEnvelope:
    math_params = staged_row.get("net_formula", {}) if isinstance(staged_row, dict) else {}
    envelope = _with_opp_id(envelope, str(staged_row.get("opp_id") or staged_row.get("opportunity_id") or ""))
    next_envelope = envelope.with_stage(
        "staging",
        {
            "status": staged_row.get("status"),
            "stage": staged_row.get("stage"),
            "principal_usd": staged_row.get("principal_usd"),
            "flash_source": staged_row.get("flash_source"),
            "opportunity_id_frozen": staged_row.get("opportunity_id_frozen"),
            "identity": staged_row.get("identity", {}),
            "route_pair_id": staged_row.get("route_pair_id"),
            "quote_snapshot_id": staged_row.get("quote_snapshot_id"),
            "simulation_id": staged_row.get("simulation_id", ""),
            "execution_attempt_id": staged_row.get("execution_attempt_id", ""),
            "transaction_hash": staged_row.get("transaction_hash", ""),
        },
        status=str(staged_row.get("status") or envelope.status).upper(),
        block_key="staged",
        block=staged_row.get("current_block"),
    )
    if math_params:
        next_envelope = next_envelope.with_stage(
            "fees",
            _fee_ledger_from_net_formula(staged_row, math_params),
            status=next_envelope.status,
        )
        next_envelope = next_envelope.with_stage("math", math_params, status=next_envelope.status)
    quote_keys = (
        "amount_out",
        "amount_out_min",
        "slippage_bps",
        "min_amount_out_bps",
        "hop_fees_usd",
    )
    quote = {key: staged_row.get(key) for key in quote_keys if key in staged_row}
    return next_envelope.with_stage("quote", quote, status=next_envelope.status) if quote else next_envelope


def add_payload_to_unified_envelope(
    envelope: UnifiedRouteEnvelope,
    tx: dict[str, Any],
    payload_envelope: PayloadEnvelope | None = None,
) -> UnifiedRouteEnvelope:
    calldata = tx.get("data", "") if isinstance(tx, dict) else ""
    payload = {
        "to": tx.get("to"),
        "chain_id": tx.get("chainId"),
        "gas": tx.get("gas"),
        "type": tx.get("type"),
        "selector": payload_selector(calldata) if isinstance(calldata, str) and len(calldata) >= 10 else "",
        "calldata_bytes": max(0, (len(calldata) - 2) // 2) if isinstance(calldata, str) and calldata.startswith("0x") else 0,
    }
    if payload_envelope is not None:
        payload["payload_envelope"] = payload_envelope.as_dict()
    return envelope.with_stage("payload", payload, status="PAYLOAD_READY")


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
    """
    Internal helper to construct a domain-separated payload envelope.
    This function is the single source of truth for envelope ID generation.
    """
    if not Web3.is_address(target):
        raise ValueError(f"invalid payload target: {target}")
    calldata_hash = Web3.keccak(_calldata_bytes(calldata)).hex()
    selector = payload_selector(calldata)
    created_ns = time.time_ns()
    # The seed for the envelope ID is a pipe-separated string of all critical,
    # domain-separating fields. This ensures uniqueness and prevents replay.
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


def build_c1_arbitrage_payload_envelope(
    *,
    target: str,
    calldata: str,
    metadata: dict[str, Any] | None = None,
    unique_salt: str = "",
) -> PayloadEnvelope:
    """Builds a domain-separated payload envelope for a C1 arbitrage transaction."""
    return _build_generic_payload_envelope(
        kind="ARBITRAGE_C1",
        domain=DOMAIN_ARBITRAGE_C1,
        target=target,
        calldata=calldata,
        metadata=metadata,
        unique_salt=unique_salt,
    )


def build_c2_arbitrage_payload_envelope(
    *,
    target: str,
    calldata: str,
    parent_c1_envelope_id: str,
    metadata: dict[str, Any] | None = None,
    unique_salt: str = "",
) -> PayloadEnvelope:
    """
    Builds a domain-separated payload envelope for a C2 arbitrage transaction.
    The C2 envelope is explicitly linked to its parent C1 envelope.
    """
    if not parent_c1_envelope_id:
        raise ValueError("C2 arbitrage payloads must be linked to a parent C1 envelope ID.")
    return _build_generic_payload_envelope(
        kind="ARBITRAGE_C2",
        domain=DOMAIN_ARBITRAGE_C2,
        target=target,
        calldata=calldata,
        parent_envelope_id=parent_c1_envelope_id,
        metadata=metadata,
        unique_salt=unique_salt,
    )


def build_liquidation_payload_envelope(
    *,
    target: str,
    calldata: str,
    metadata: dict[str, Any] | None = None,
    unique_salt: str = "",
) -> PayloadEnvelope:
    """Builds a domain-separated payload envelope for a liquidation transaction."""
    return _build_generic_payload_envelope(
        kind="LIQUIDATION",
        domain=DOMAIN_LIQUIDATION,
        target=target,
        calldata=calldata,
        metadata=metadata,
        unique_salt=unique_salt,
    )
