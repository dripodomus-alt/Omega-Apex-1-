#!/usr/bin/env python3
# ==============================================================================
# cycle_logger.py — C1×C2 hierarchical cycle logging (in-memory + JSONL + optional SQL)
# ==============================================================================
"""
Core logging law:
  1 opportunity_id
    ├── C1 cycle log
    └── C2 cycle log

C2 cannot exist without confirmed C1 success.
Fire-and-forget friendly: never raises into the hot path.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cycle_ids import (
    build_c1_cycle_id,
    build_c2_cycle_id,
    build_opportunity_id,
    config_hash as make_config_hash,
    event_id as make_event_id,
    route_hash as make_route_hash,
    state_hash as make_state_hash,
)
from .paths import output_path

logger = logging.getLogger("omega.cycle_logger")

CYCLE_EVENTS_PATH = output_path("cycle_events.jsonl")
OPPORTUNITIES_PATH = output_path("opportunities.jsonl")
MACHINE_STATE_PATH = output_path("cycle_machine_state.json")

_lock = threading.RLock()
_opportunities: Dict[str, "OpportunityRecord"] = {}
_events: List[Dict[str, Any]] = []
_MAX_EVENTS = 5000


class CycleType(str, Enum):
    DISCOVERY = "DISCOVERY"
    C1 = "C1"
    C2 = "C2"
    LIQUIDATION = "LIQUIDATION"


class CycleEventType(str, Enum):
    DISCOVERED = "DISCOVERED"
    PRICE_EDGE_VALIDATED = "PRICE_EDGE_VALIDATED"
    SIZE_SELECTED = "SIZE_SELECTED"
    PROFIT_VALIDATED = "PROFIT_VALIDATED"
    SIM_STARTED = "SIM_STARTED"
    SIM_PASSED = "SIM_PASSED"
    SIM_FAILED = "SIM_FAILED"
    PAYLOAD_BUILT = "PAYLOAD_BUILT"
    SUBMITTED_PRIVATE = "SUBMITTED_PRIVATE"
    SUBMITTED_PUBLIC = "SUBMITTED_PUBLIC"
    CONFIRMED = "CONFIRMED"
    REVERTED = "REVERTED"
    SETTLED = "SETTLED"
    C2_WINDOW_OPENED = "C2_WINDOW_OPENED"
    POST_C1_STATE_RELOADED = "POST_C1_STATE_RELOADED"
    C2_MIRROR_EVALUATED = "C2_MIRROR_EVALUATED"
    C2_REVERSE_EVALUATED = "C2_REVERSE_EVALUATED"
    C2_NOOP_SELECTED = "C2_NOOP_SELECTED"
    C2_EXPIRED = "C2_EXPIRED"
    ARCHIVED = "ARCHIVED"
    CANCELLED = "CANCELLED"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _dec(value: Any, default: str = "0") -> str:
    try:
        return str(Decimal(str(value)))
    except Exception:
        return default


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _append_jsonl(path: Path, row: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(_json_safe(row), separators=(",", ":")) + "\n"
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:
        logger.debug("cycle_logger jsonl write failed: %s", exc)


@dataclass
class C1CycleRecord:
    c1_cycle_id: str
    opportunity_id: str
    cycle_type: str = "C1"
    cycle_index: int = 1
    chain_id: int = 137
    discovery_block: int = 0
    execution_anchor_block: int = 0
    expires_at_block: int = 0
    borrow_asset: str = ""
    borrow_amount_raw: str = "0"
    borrow_amount_usd: str = "0"
    route_hash: str = ""
    state_hash: str = ""
    config_hash: str = ""
    expected_gross_usd: str = "0"
    expected_net_usd: str = "0"
    min_net_usd: str = "0"
    gas_estimate_usd: str = "0"
    flash_fee_usd: str = "0"
    risk_buffer_usd: str = "0"
    mev_buffer_usd: str = "0"
    simulation_status: str = "NOT_STARTED"
    payload_status: str = "NOT_BUILT"
    submission_status: str = "NOT_SUBMITTED"
    settlement_status: str = "NOT_SETTLED"
    tx_hash: Optional[str] = None
    submitted_block: Optional[int] = None
    confirmed_block: Optional[int] = None
    realized_gross_usd: Optional[str] = None
    realized_net_usd: Optional[str] = None
    realized_gas_usd: Optional[str] = None
    realized_profit_raw: Optional[str] = None
    reject_reason: Optional[str] = None
    created_at_ms: int = field(default_factory=_now_ms)
    updated_at_ms: int = field(default_factory=_now_ms)


@dataclass
class C2CycleRecord:
    c2_cycle_id: str
    opportunity_id: str
    parent_c1_cycle_id: str
    cycle_type: str = "C2"
    cycle_index: int = 2
    c1_tx_hash: str = ""
    c1_confirmed_block: int = 0
    c2_window_start_block: int = 0
    c2_window_end_block: int = 0
    c2_eval_block: int = 0
    post_c1_state_hash: str = ""
    pre_c2_route_hash: Optional[str] = None
    c2_route_hash: Optional[str] = None
    c2_decision: str = "PENDING"
    mirror_expected_net_usd: Optional[str] = None
    reverse_expected_net_usd: Optional[str] = None
    selected_expected_net_usd: Optional[str] = None
    borrow_asset: Optional[str] = None
    borrow_amount_raw: Optional[str] = None
    borrow_amount_usd: Optional[str] = None
    gas_estimate_usd: Optional[str] = None
    flash_fee_usd: Optional[str] = None
    risk_buffer_usd: Optional[str] = None
    mev_buffer_usd: Optional[str] = None
    simulation_status: str = "NOT_STARTED"
    payload_status: str = "NOT_BUILT"
    submission_status: str = "NOT_SUBMITTED"
    settlement_status: str = "NOT_SETTLED"
    tx_hash: Optional[str] = None
    submitted_block: Optional[int] = None
    confirmed_block: Optional[int] = None
    realized_gross_usd: Optional[str] = None
    realized_net_usd: Optional[str] = None
    realized_gas_usd: Optional[str] = None
    realized_profit_raw: Optional[str] = None
    reject_reason: Optional[str] = None
    created_at_ms: int = field(default_factory=_now_ms)
    updated_at_ms: int = field(default_factory=_now_ms)


@dataclass
class OpportunityRecord:
    opportunity_id: str
    chain_id: int
    discovered_block: int
    discovered_block_hash: str = ""
    detected_at_ms: int = field(default_factory=_now_ms)
    config_version: int = 0
    config_hash: str = ""
    borrow_asset: str = ""
    borrow_symbol: str = ""
    buy_venue: str = ""
    buy_pool: str = ""
    sell_venue: str = ""
    sell_pool: str = ""
    buy_family: str = ""
    sell_family: str = ""
    buy_leg_price: str = "0"
    sell_leg_price: str = "0"
    raw_spread_usd: str = "0"
    raw_spread_bps: str = "0"
    state_hash: str = ""
    route_hash: str = ""
    opportunity_status: str = "DISCOVERED"
    c1_cycle_id: Optional[str] = None
    c2_cycle_id: Optional[str] = None
    c1: Optional[C1CycleRecord] = None
    c2: Optional[C2CycleRecord] = None
    final_status: Optional[str] = None
    combined_realized_net_usd: Optional[str] = None
    created_at_ms: int = field(default_factory=_now_ms)
    updated_at_ms: int = field(default_factory=_now_ms)


class CycleLogger:
    """In-process hierarchical logger with JSONL durability."""

    def register_opportunity(
        self,
        *,
        chain_id: int = 137,
        discovered_block: int,
        buy_pool: str,
        sell_pool: str,
        borrow_asset: str,
        path: Optional[List[str]] = None,
        pool_sequence: Optional[List[str]] = None,
        buy_venue: str = "",
        sell_venue: str = "",
        buy_family: str = "",
        sell_family: str = "",
        buy_leg_price: Any = "0",
        sell_leg_price: Any = "0",
        raw_spread_usd: Any = "0",
        raw_spread_bps: Any = "0",
        config_version: int = 0,
        pool_state_fingerprint: Any = None,
        discovered_block_hash: str = "",
        metadata: Optional[dict] = None,
    ) -> OpportunityRecord:
        rh = make_route_hash(pool_sequence or [buy_pool, sell_pool], path)
        sh = make_state_hash(discovered_block, pool_state_fingerprint or pool_sequence)
        ch = make_config_hash(config_version)
        oid = build_opportunity_id(
            chain_id=chain_id,
            discovered_block=discovered_block,
            buy_pool=buy_pool,
            sell_pool=sell_pool,
            borrow_asset=borrow_asset,
            route_hash_value=rh,
            state_hash_value=sh,
            config_hash_value=ch,
        )
        rec = OpportunityRecord(
            opportunity_id=oid,
            chain_id=chain_id,
            discovered_block=discovered_block,
            discovered_block_hash=discovered_block_hash,
            config_version=config_version,
            config_hash=ch,
            borrow_asset=borrow_asset,
            borrow_symbol=borrow_asset,
            buy_venue=buy_venue,
            buy_pool=buy_pool,
            sell_venue=sell_venue,
            sell_pool=sell_pool,
            buy_family=buy_family,
            sell_family=sell_family,
            buy_leg_price=_dec(buy_leg_price),
            sell_leg_price=_dec(sell_leg_price),
            raw_spread_usd=_dec(raw_spread_usd),
            raw_spread_bps=_dec(raw_spread_bps),
            state_hash=sh,
            route_hash=rh,
            opportunity_status="C1_READY",
        )
        with _lock:
            _opportunities[oid] = rec
            _append_jsonl(OPPORTUNITIES_PATH, asdict(rec))
        self.log_event(
            opportunity_id=oid,
            cycle_id=oid,
            cycle_type=CycleType.DISCOVERY,
            event_type=CycleEventType.DISCOVERED,
            block_number=discovered_block,
            state_hash=sh,
            route_hash=rh,
            config_hash=ch,
            message="Opportunity discovered",
            metadata=metadata or {},
        )
        return rec

    def open_c1(
        self,
        opportunity_id: str,
        *,
        discovery_block: int,
        borrow_amount_usd: Any = "0",
        borrow_amount_raw: str = "0",
        expected_gross_usd: Any = "0",
        expected_net_usd: Any = "0",
        min_net_usd: Any = "5",
        gas_estimate_usd: Any = "0",
        flash_fee_usd: Any = "0",
        risk_buffer_usd: Any = "0",
        mev_buffer_usd: Any = "0",
        expires_at_block: Optional[int] = None,
    ) -> Optional[C1CycleRecord]:
        with _lock:
            opp = _opportunities.get(opportunity_id)
            if not opp:
                return None
            c1_id = build_c1_cycle_id(
                opportunity_id=opportunity_id,
                discovery_block=discovery_block,
                route_hash_value=opp.route_hash,
            )
            c1 = C1CycleRecord(
                c1_cycle_id=c1_id,
                opportunity_id=opportunity_id,
                chain_id=opp.chain_id,
                discovery_block=discovery_block,
                execution_anchor_block=discovery_block + 1,
                expires_at_block=expires_at_block or discovery_block + 4,
                borrow_asset=opp.borrow_asset,
                borrow_amount_raw=str(borrow_amount_raw),
                borrow_amount_usd=_dec(borrow_amount_usd),
                route_hash=opp.route_hash,
                state_hash=opp.state_hash,
                config_hash=opp.config_hash,
                expected_gross_usd=_dec(expected_gross_usd),
                expected_net_usd=_dec(expected_net_usd),
                min_net_usd=_dec(min_net_usd),
                gas_estimate_usd=_dec(gas_estimate_usd),
                flash_fee_usd=_dec(flash_fee_usd),
                risk_buffer_usd=_dec(risk_buffer_usd),
                mev_buffer_usd=_dec(mev_buffer_usd),
            )
            opp.c1 = c1
            opp.c1_cycle_id = c1_id
            opp.opportunity_status = "C1_OPEN"
            opp.updated_at_ms = _now_ms()
        self.log_event(
            opportunity_id=opportunity_id,
            cycle_id=c1_id,
            cycle_type=CycleType.C1,
            event_type=CycleEventType.SIZE_SELECTED,
            block_number=discovery_block,
            route_hash=c1.route_hash,
            state_hash=c1.state_hash,
            config_hash=c1.config_hash,
            message="C1 cycle opened",
            metadata={"expected_net_usd": c1.expected_net_usd},
        )
        return c1

    def update_c1(
        self,
        opportunity_id: str,
        *,
        simulation_status: Optional[str] = None,
        payload_status: Optional[str] = None,
        submission_status: Optional[str] = None,
        settlement_status: Optional[str] = None,
        tx_hash: Optional[str] = None,
        submitted_block: Optional[int] = None,
        confirmed_block: Optional[int] = None,
        realized_net_usd: Optional[Any] = None,
        realized_gross_usd: Optional[Any] = None,
        realized_gas_usd: Optional[Any] = None,
        realized_profit_raw: Optional[str] = None,
        reject_reason: Optional[str] = None,
        event_type: Optional[CycleEventType] = None,
        message: str = "",
        metadata: Optional[dict] = None,
    ) -> Optional[C1CycleRecord]:
        with _lock:
            opp = _opportunities.get(opportunity_id)
            if not opp or not opp.c1:
                return None
            c1 = opp.c1
            if simulation_status is not None:
                c1.simulation_status = simulation_status
            if payload_status is not None:
                c1.payload_status = payload_status
            if submission_status is not None:
                c1.submission_status = submission_status
            if settlement_status is not None:
                c1.settlement_status = settlement_status
            if tx_hash is not None:
                c1.tx_hash = tx_hash
            if submitted_block is not None:
                c1.submitted_block = submitted_block
            if confirmed_block is not None:
                c1.confirmed_block = confirmed_block
            if realized_net_usd is not None:
                c1.realized_net_usd = _dec(realized_net_usd)
            if realized_gross_usd is not None:
                c1.realized_gross_usd = _dec(realized_gross_usd)
            if realized_gas_usd is not None:
                c1.realized_gas_usd = _dec(realized_gas_usd)
            if realized_profit_raw is not None:
                c1.realized_profit_raw = realized_profit_raw
            if reject_reason is not None:
                c1.reject_reason = reject_reason
            c1.updated_at_ms = _now_ms()
            opp.updated_at_ms = c1.updated_at_ms

            # C1 failed → cancel C2
            failed = (
                (settlement_status or "").upper() in {"FAILED", "REVERTED"}
                or (submission_status or "").upper() in {"FAILED", "REVERTED"}
                or (simulation_status or "").upper() == "FAILED"
            )
            if failed:
                opp.opportunity_status = "CLOSED_C1_FAILED"
                opp.final_status = "CLOSED_C1_FAILED"
                if opp.c2 is None:
                    # mark cancelled placeholder
                    pass
                else:
                    opp.c2.c2_decision = "CANCELLED"
                    opp.c2.settlement_status = "CANCELLED"
                    opp.c2.reject_reason = reject_reason or "C1_NOT_CONFIRMED_SUCCESS"

            if (settlement_status or "").upper() == "SETTLED":
                opp.opportunity_status = "C1_SETTLED"

        if event_type:
            self.log_event(
                opportunity_id=opportunity_id,
                cycle_id=c1.c1_cycle_id,
                cycle_type=CycleType.C1,
                event_type=event_type,
                block_number=confirmed_block or submitted_block,
                tx_hash=tx_hash,
                route_hash=c1.route_hash,
                state_hash=c1.state_hash,
                config_hash=c1.config_hash,
                message=message or event_type.value,
                metadata=metadata or {},
            )
        return c1

    def open_c2(
        self,
        opportunity_id: str,
        *,
        c1_tx_hash: str,
        c1_confirmed_block: int,
        post_c1_state_hash: str,
        window_blocks: int = 5,
        c2_route_hash: str = "",
    ) -> Optional[C2CycleRecord]:
        with _lock:
            opp = _opportunities.get(opportunity_id)
            if not opp or not opp.c1:
                return None
            c1 = opp.c1
            # Hard rule: C2 only after confirmed C1 success
            if (c1.settlement_status or "").upper() not in {"SETTLED", "CONFIRMED"} and (
                c1.submission_status or ""
            ).upper() not in {"CONFIRMED", "SETTLED"}:
                if (c1.settlement_status or "").upper() not in {"SETTLED"} and not (
                    c1.tx_hash and c1.confirmed_block
                ):
                    self.log_event(
                        opportunity_id=opportunity_id,
                        cycle_id=c1.c1_cycle_id,
                        cycle_type=CycleType.C2,
                        event_type=CycleEventType.CANCELLED,
                        block_number=c1_confirmed_block,
                        message="C2 cancelled: C1 not CONFIRMED_SUCCESS",
                    )
                    return None

            c2_id = build_c2_cycle_id(
                opportunity_id=opportunity_id,
                c1_tx_hash=c1_tx_hash,
                c1_confirmed_block=c1_confirmed_block,
                post_c1_state_hash=post_c1_state_hash,
                c2_route_hash=c2_route_hash,
            )
            start = c1_confirmed_block + 1
            c2 = C2CycleRecord(
                c2_cycle_id=c2_id,
                opportunity_id=opportunity_id,
                parent_c1_cycle_id=c1.c1_cycle_id,
                c1_tx_hash=c1_tx_hash,
                c1_confirmed_block=c1_confirmed_block,
                c2_window_start_block=start,
                c2_window_end_block=start + window_blocks - 1,
                c2_eval_block=start,
                post_c1_state_hash=post_c1_state_hash,
                pre_c2_route_hash=opp.route_hash,
                c2_route_hash=c2_route_hash or None,
                borrow_asset=opp.borrow_asset,
            )
            opp.c2 = c2
            opp.c2_cycle_id = c2_id
            opp.opportunity_status = "C2_OPEN"
            opp.updated_at_ms = _now_ms()

        self.log_event(
            opportunity_id=opportunity_id,
            cycle_id=c2_id,
            cycle_type=CycleType.C2,
            event_type=CycleEventType.C2_WINDOW_OPENED,
            block_number=start,
            state_hash=post_c1_state_hash,
            message="C2 window opened",
        )
        self.log_event(
            opportunity_id=opportunity_id,
            cycle_id=c2_id,
            cycle_type=CycleType.C2,
            event_type=CycleEventType.POST_C1_STATE_RELOADED,
            block_number=start,
            state_hash=post_c1_state_hash,
            message="Post-C1 state reloaded",
        )
        return c2

    def decide_c2(
        self,
        opportunity_id: str,
        *,
        decision: str,
        mirror_expected_net_usd: Any = None,
        reverse_expected_net_usd: Any = None,
        selected_expected_net_usd: Any = None,
        c2_route_hash: str = "",
        c2_eval_block: Optional[int] = None,
        reject_reason: Optional[str] = None,
    ) -> Optional[C2CycleRecord]:
        decision_u = (decision or "DO_NOTHING").upper()
        with _lock:
            opp = _opportunities.get(opportunity_id)
            if not opp or not opp.c2:
                return None
            c2 = opp.c2
            c2.c2_decision = decision_u
            c2.mirror_expected_net_usd = (
                _dec(mirror_expected_net_usd) if mirror_expected_net_usd is not None else None
            )
            c2.reverse_expected_net_usd = (
                _dec(reverse_expected_net_usd) if reverse_expected_net_usd is not None else None
            )
            c2.selected_expected_net_usd = (
                _dec(selected_expected_net_usd) if selected_expected_net_usd is not None else _dec(0)
            )
            if c2_route_hash:
                c2.c2_route_hash = c2_route_hash
            if c2_eval_block is not None:
                c2.c2_eval_block = c2_eval_block
            if reject_reason:
                c2.reject_reason = reject_reason
            if decision_u == "DO_NOTHING":
                c2.simulation_status = "SKIPPED_NO_PROFITABLE_BRANCH"
                c2.payload_status = "NOT_BUILT"
                c2.submission_status = "NOT_SUBMITTED"
                c2.settlement_status = "NOOP"
                c2.realized_net_usd = "0"
                opp.final_status = "CLOSED_C1_ONLY_PROFITABLE"
                opp.opportunity_status = "CLOSED_C1_ONLY_PROFITABLE"
            elif decision_u == "EXPIRED":
                c2.settlement_status = "EXPIRED"
                c2.reject_reason = reject_reason or "C2_WINDOW_EXPIRED"
                opp.final_status = "CLOSED_C2_EXPIRED"
                opp.opportunity_status = "CLOSED_C2_EXPIRED"
            elif decision_u == "CANCELLED":
                c2.settlement_status = "CANCELLED"
                opp.final_status = "CLOSED_C1_FAILED"
            c2.updated_at_ms = _now_ms()
            opp.updated_at_ms = c2.updated_at_ms
            self._recompute_combined(opp)

        ev = CycleEventType.C2_NOOP_SELECTED
        if decision_u == "MIRROR":
            ev = CycleEventType.C2_MIRROR_EVALUATED
        elif decision_u == "REVERSE":
            ev = CycleEventType.C2_REVERSE_EVALUATED
        elif decision_u == "EXPIRED":
            ev = CycleEventType.C2_EXPIRED
        elif decision_u == "CANCELLED":
            ev = CycleEventType.CANCELLED

        self.log_event(
            opportunity_id=opportunity_id,
            cycle_id=c2.c2_cycle_id,
            cycle_type=CycleType.C2,
            event_type=ev,
            block_number=c2.c2_eval_block,
            route_hash=c2.c2_route_hash,
            state_hash=c2.post_c1_state_hash,
            message=f"C2 decision={decision_u}",
            metadata={
                "mirror_expected_net_usd": c2.mirror_expected_net_usd,
                "reverse_expected_net_usd": c2.reverse_expected_net_usd,
                "selected_expected_net_usd": c2.selected_expected_net_usd,
            },
        )
        if decision_u in {"DO_NOTHING", "EXPIRED", "CANCELLED"}:
            self._persist_machine_state(opportunity_id)
        return c2

    def update_c2(
        self,
        opportunity_id: str,
        *,
        simulation_status: Optional[str] = None,
        payload_status: Optional[str] = None,
        submission_status: Optional[str] = None,
        settlement_status: Optional[str] = None,
        tx_hash: Optional[str] = None,
        submitted_block: Optional[int] = None,
        confirmed_block: Optional[int] = None,
        realized_net_usd: Optional[Any] = None,
        realized_gross_usd: Optional[Any] = None,
        realized_gas_usd: Optional[Any] = None,
        realized_profit_raw: Optional[str] = None,
        reject_reason: Optional[str] = None,
        event_type: Optional[CycleEventType] = None,
        message: str = "",
        metadata: Optional[dict] = None,
    ) -> Optional[C2CycleRecord]:
        with _lock:
            opp = _opportunities.get(opportunity_id)
            if not opp or not opp.c2:
                return None
            c2 = opp.c2
            if simulation_status is not None:
                c2.simulation_status = simulation_status
            if payload_status is not None:
                c2.payload_status = payload_status
            if submission_status is not None:
                c2.submission_status = submission_status
            if settlement_status is not None:
                c2.settlement_status = settlement_status
            if tx_hash is not None:
                c2.tx_hash = tx_hash
            if submitted_block is not None:
                c2.submitted_block = submitted_block
            if confirmed_block is not None:
                c2.confirmed_block = confirmed_block
            if realized_net_usd is not None:
                c2.realized_net_usd = _dec(realized_net_usd)
            if realized_gross_usd is not None:
                c2.realized_gross_usd = _dec(realized_gross_usd)
            if realized_gas_usd is not None:
                c2.realized_gas_usd = _dec(realized_gas_usd)
            if realized_profit_raw is not None:
                c2.realized_profit_raw = realized_profit_raw
            if reject_reason is not None:
                c2.reject_reason = reject_reason
            c2.updated_at_ms = _now_ms()
            opp.updated_at_ms = c2.updated_at_ms
            if (settlement_status or "").upper() == "SETTLED":
                opp.opportunity_status = "CLOSED_PROFITABLE"
                opp.final_status = "CLOSED_PROFITABLE"
            self._recompute_combined(opp)

        if event_type:
            self.log_event(
                opportunity_id=opportunity_id,
                cycle_id=c2.c2_cycle_id,
                cycle_type=CycleType.C2,
                event_type=event_type,
                block_number=confirmed_block or submitted_block,
                tx_hash=tx_hash,
                route_hash=c2.c2_route_hash,
                state_hash=c2.post_c1_state_hash,
                message=message or event_type.value,
                metadata=metadata or {},
            )
        if (settlement_status or "").upper() in {"SETTLED", "FAILED", "REVERTED", "NOOP", "EXPIRED"}:
            self._persist_machine_state(opportunity_id)
        return c2

    def _recompute_combined(self, opp: OpportunityRecord) -> None:
        c1_net = Decimal(_dec(opp.c1.realized_net_usd if opp.c1 else 0))
        c2_net = Decimal(_dec(opp.c2.realized_net_usd if opp.c2 else 0))
        opp.combined_realized_net_usd = str(c1_net + c2_net)

    def log_event(
        self,
        *,
        opportunity_id: str,
        cycle_id: str,
        cycle_type: CycleType | str,
        event_type: CycleEventType | str,
        block_number: Optional[int] = None,
        tx_hash: Optional[str] = None,
        state_hash: Optional[str] = None,
        route_hash: Optional[str] = None,
        config_hash: Optional[str] = None,
        message: str = "",
        metadata: Optional[dict] = None,
    ) -> dict:
        ct = cycle_type.value if isinstance(cycle_type, Enum) else str(cycle_type)
        et = event_type.value if isinstance(event_type, Enum) else str(event_type)
        created = _now_ms()
        eid = make_event_id(
            opportunity_id=opportunity_id,
            cycle_id=cycle_id,
            event_type=et,
            block_number=block_number,
            created_at_ms=created,
        )
        row = {
            "event_id": eid,
            "opportunity_id": opportunity_id,
            "cycle_id": cycle_id,
            "cycle_type": ct,
            "event_type": et,
            "event_status": "OK",
            "block_number": block_number,
            "tx_hash": tx_hash,
            "state_hash": state_hash,
            "route_hash": route_hash,
            "config_hash": config_hash,
            "message": message,
            "metadata_json": _json_safe(metadata or {}),
            "created_at_ms": created,
        }
        with _lock:
            _events.append(row)
            if len(_events) > _MAX_EVENTS:
                del _events[: len(_events) - _MAX_EVENTS]
            _append_jsonl(CYCLE_EVENTS_PATH, row)
        try:
            logger.info(
                "cycle_event %s %s opp=%s cycle=%s block=%s",
                ct,
                et,
                opportunity_id[:20],
                cycle_id[:20],
                block_number,
            )
        except Exception:
            pass
        return row

    def machine_state(self, opportunity_id: str) -> Optional[dict]:
        with _lock:
            opp = _opportunities.get(opportunity_id)
            if not opp:
                return None
            c1 = opp.c1
            c2 = opp.c2
            status = opp.final_status or opp.opportunity_status
            return {
                "opportunity_id": opp.opportunity_id,
                "status": status,
                "blocks": {
                    "discovered": opp.discovered_block,
                    "c1_submitted": c1.submitted_block if c1 else None,
                    "c1_confirmed": c1.confirmed_block if c1 else None,
                    "c2_window_start": c2.c2_window_start_block if c2 else None,
                    "c2_window_end": c2.c2_window_end_block if c2 else None,
                    "c2_submitted": c2.submitted_block if c2 else None,
                    "c2_confirmed": c2.confirmed_block if c2 else None,
                },
                "c1": None
                if not c1
                else {
                    "cycle_id": c1.c1_cycle_id,
                    "route_hash": c1.route_hash,
                    "state_hash": c1.state_hash,
                    "status": c1.settlement_status or c1.submission_status,
                    "expected_net_usd": c1.expected_net_usd,
                    "realized_net_usd": c1.realized_net_usd,
                    "tx_hash": c1.tx_hash,
                },
                "c2": None
                if not c2
                else {
                    "cycle_id": c2.c2_cycle_id,
                    "parent_c1_cycle_id": c2.parent_c1_cycle_id,
                    "decision": c2.c2_decision,
                    "route_hash": c2.c2_route_hash,
                    "post_c1_state_hash": c2.post_c1_state_hash,
                    "status": c2.settlement_status or c2.submission_status,
                    "expected_net_usd": c2.selected_expected_net_usd,
                    "realized_net_usd": c2.realized_net_usd,
                    "tx_hash": c2.tx_hash,
                },
                "pnl": {
                    "c1_realized_net_usd": c1.realized_net_usd if c1 else "0",
                    "c2_realized_net_usd": c2.realized_net_usd if c2 else "0",
                    "combined_realized_net_usd": opp.combined_realized_net_usd or "0",
                },
            }

    def _persist_machine_state(self, opportunity_id: str) -> None:
        state = self.machine_state(opportunity_id)
        if not state:
            return
        path = Path(MACHINE_STATE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # merge into small recent map
            existing: dict = {}
            if path.exists():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    existing = {}
            if not isinstance(existing, dict):
                existing = {}
            recent = existing.get("recent", [])
            if not isinstance(recent, list):
                recent = []
            recent = [r for r in recent if r.get("opportunity_id") != opportunity_id]
            recent.insert(0, state)
            existing["recent"] = recent[:100]
            existing["updated_at_ms"] = _now_ms()
            tmp_fd, tmp_name = tempfile.mkstemp(prefix="cycle_ms_", suffix=".json", dir=str(path.parent))
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                    json.dump(existing, fh, indent=2)
                os.replace(tmp_name, path)
            finally:
                if os.path.exists(tmp_name):
                    try:
                        os.remove(tmp_name)
                    except OSError:
                        pass
        except Exception as exc:
            logger.debug("machine state persist failed: %s", exc)

    def get_opportunity(self, opportunity_id: str) -> Optional[OpportunityRecord]:
        with _lock:
            return _opportunities.get(opportunity_id)

    def list_recent_states(self, limit: int = 20) -> List[dict]:
        path = Path(MACHINE_STATE_PATH)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                recent = data.get("recent", [])
                if isinstance(recent, list):
                    return recent[:limit]
            except Exception:
                pass
        with _lock:
            ids = list(_opportunities.keys())[-limit:]
            out = []
            for oid in reversed(ids):
                st = self.machine_state(oid)
                if st:
                    out.append(st)
            return out

    def recent_events(self, limit: int = 50, opportunity_id: Optional[str] = None) -> List[dict]:
        with _lock:
            rows = list(_events)
        if opportunity_id:
            rows = [r for r in rows if r.get("opportunity_id") == opportunity_id]
        return rows[-limit:]

    def clear_memory(self) -> None:
        """Test helper only."""
        with _lock:
            _opportunities.clear()
            _events.clear()


# Module singleton
cycle_logger = CycleLogger()


def register_opportunity_from_live(
    op: Any,
    *,
    chain_id: int = 137,
    discovered_block: int = 0,
    config_version: int = 0,
) -> OpportunityRecord:
    """Convenience bridge from LiveOpportunity-like objects."""
    path = list(getattr(op, "path", []) or [])
    pools = list(getattr(op, "pool_sequence", []) or [])
    buy_pool = pools[0] if pools else ""
    sell_pool = pools[-1] if pools else buy_pool
    borrow = path[0] if path else getattr(op, "borrow_asset", "USDC")
    block = discovered_block or int(getattr(op, "block_detected", 0) or 0)
    prof = getattr(op, "profitability", None)
    net = getattr(prof, "net_profit_usd", Decimal("0")) if prof else Decimal("0")
    return cycle_logger.register_opportunity(
        chain_id=chain_id,
        discovered_block=block,
        buy_pool=str(buy_pool),
        sell_pool=str(sell_pool),
        borrow_asset=str(borrow),
        path=path,
        pool_sequence=pools,
        raw_spread_usd=net,
        config_version=config_version,
        metadata={"source": "live_opportunity"},
    )
