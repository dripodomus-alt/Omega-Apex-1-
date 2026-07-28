#!/usr/bin/env python3
# ==============================================================================
# check_c1_c2_logging_gate.py — Readiness gate for C1×C2 logging model
# ==============================================================================
"""Exit 0 if schema + logger round-trip pass. Safe, no network."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from omega_v5.cycle_logger import CycleEventType, cycle_logger


def main() -> int:
    errors: list[str] = []

    schema = ROOT / "omega_v5" / "db" / "schema.sql"
    if not schema.exists():
        errors.append("schema.sql missing")
    else:
        text = schema.read_text(encoding="utf-8")
        for table in ("opportunities", "c1_cycles", "c2_cycles", "cycle_events"):
            if f"CREATE TABLE IF NOT EXISTS {table}" not in text:
                errors.append(f"schema missing table: {table}")

    cycle_logger.clear_memory()
    opp = cycle_logger.register_opportunity(
        chain_id=137,
        discovered_block=1,
        buy_pool="0xbuy",
        sell_pool="0xsell",
        borrow_asset="USDC",
        pool_sequence=["0xbuy", "0xsell"],
    )
    cycle_logger.open_c1(opp.opportunity_id, discovery_block=1, expected_net_usd="10")
    cycle_logger.update_c1(
        opp.opportunity_id,
        settlement_status="SETTLED",
        submission_status="CONFIRMED",
        tx_hash="0xc1",
        confirmed_block=2,
        realized_net_usd="8",
        event_type=CycleEventType.SETTLED,
    )
    c2 = cycle_logger.open_c2(
        opp.opportunity_id,
        c1_tx_hash="0xc1",
        c1_confirmed_block=2,
        post_c1_state_hash="post",
    )
    if c2 is None:
        errors.append("open_c2 failed after C1 settle")
    else:
        cycle_logger.decide_c2(opp.opportunity_id, decision="DO_NOTHING")
        state = cycle_logger.machine_state(opp.opportunity_id)
        if not state or Decimal(state["pnl"]["combined_realized_net_usd"]) != Decimal("8"):
            errors.append("combined pnl mismatch")

    # orphan C2 rule
    cycle_logger.clear_memory()
    opp2 = cycle_logger.register_opportunity(
        chain_id=137,
        discovered_block=3,
        buy_pool="0xa",
        sell_pool="0xb",
        borrow_asset="USDC",
        pool_sequence=["0xa", "0xb"],
    )
    cycle_logger.open_c1(opp2.opportunity_id, discovery_block=3)
    cycle_logger.update_c1(
        opp2.opportunity_id,
        settlement_status="REVERTED",
        submission_status="REVERTED",
        event_type=CycleEventType.REVERTED,
    )
    if cycle_logger.open_c2(
        opp2.opportunity_id,
        c1_tx_hash="0xbad",
        c1_confirmed_block=4,
        post_c1_state_hash="x",
    ) is not None:
        errors.append("C2 must not open after C1 revert")

    if errors:
        print("C1×C2 Logging Gate: FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("C1×C2 Logging Gate: PASS")
    print("  schema tables present")
    print("  opportunity → C1 settle → C2 noop OK")
    print("  C1 fail cancels C2 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
