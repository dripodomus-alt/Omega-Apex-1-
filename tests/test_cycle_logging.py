#!/usr/bin/env python3
# ==============================================================================
# test_cycle_logging.py — C1×C2 logging model unit tests
# ==============================================================================

from __future__ import annotations

from decimal import Decimal

from omega_v5.cycle_ids import (
    build_c1_cycle_id,
    build_c2_cycle_id,
    build_opportunity_id,
    route_hash,
    state_hash,
    config_hash,
)
from omega_v5.cycle_logger import CycleEventType, cycle_logger


def setup_function(_fn=None):
    cycle_logger.clear_memory()


def test_opportunity_id_stable():
    a = build_opportunity_id(
        chain_id=137,
        discovered_block=90213722,
        buy_pool="0xBuy",
        sell_pool="0xSell",
        borrow_asset="USDC",
        route_hash_value="rh_abc",
        state_hash_value="sh_def",
        config_hash_value="ch_ghi",
    )
    b = build_opportunity_id(
        chain_id=137,
        discovered_block=90213722,
        buy_pool="0xBuy",
        sell_pool="0xSell",
        borrow_asset="USDC",
        route_hash_value="rh_abc",
        state_hash_value="sh_def",
        config_hash_value="ch_ghi",
    )
    assert a == b
    assert a.startswith("opp_137_90213722_")


def test_c1_c2_id_linkage():
    oid = build_opportunity_id(
        chain_id=137,
        discovered_block=1,
        buy_pool="0xa",
        sell_pool="0xb",
        borrow_asset="USDC",
        route_hash_value=route_hash(["0xa", "0xb"], ["USDC", "WETH", "USDC"]),
        state_hash_value=state_hash(1, "fp"),
        config_hash_value=config_hash(44),
    )
    c1 = build_c1_cycle_id(opportunity_id=oid, discovery_block=1, route_hash_value="rh")
    c2 = build_c2_cycle_id(
        opportunity_id=oid,
        c1_tx_hash="0xc1tx",
        c1_confirmed_block=2,
        post_c1_state_hash="sh_post",
        c2_route_hash="rh_rev",
    )
    assert c1.startswith("c1_")
    assert c2.startswith("c2_")
    assert c1 != c2


def test_full_profitable_c1_c2_flow():
    opp = cycle_logger.register_opportunity(
        chain_id=137,
        discovered_block=90213722,
        buy_pool="0xBuyPool",
        sell_pool="0xSellPool",
        borrow_asset="USDC",
        path=["USDC", "WETH", "USDC"],
        pool_sequence=["0xBuyPool", "0xSellPool"],
        buy_venue="QuickSwapV2",
        sell_venue="UniswapV3",
        buy_family="V2_CPMM",
        sell_family="V3_CLMM",
        buy_leg_price="2574.12",
        sell_leg_price="2577.89",
        raw_spread_usd="3.77",
        raw_spread_bps="14.645",
        config_version=44,
    )
    assert opp.opportunity_status == "C1_READY"

    c1 = cycle_logger.open_c1(
        opp.opportunity_id,
        discovery_block=90213722,
        borrow_amount_usd="10000",
        borrow_amount_raw="10000000000",
        expected_gross_usd="18.92",
        expected_net_usd="8.57",
        min_net_usd="5",
        gas_estimate_usd="2.85",
        flash_fee_usd="5.00",
    )
    assert c1 is not None

    cycle_logger.update_c1(
        opp.opportunity_id,
        simulation_status="PASSED",
        event_type=CycleEventType.SIM_PASSED,
    )
    cycle_logger.update_c1(
        opp.opportunity_id,
        payload_status="BUILT",
        submission_status="SUBMITTED_PRIVATE",
        tx_hash="0xc1tx",
        submitted_block=90213723,
        event_type=CycleEventType.SUBMITTED_PRIVATE,
    )
    cycle_logger.update_c1(
        opp.opportunity_id,
        submission_status="CONFIRMED",
        settlement_status="SETTLED",
        tx_hash="0xc1tx",
        confirmed_block=90213723,
        realized_net_usd="7.99",
        realized_gross_usd="17.41",
        realized_gas_usd="2.92",
        realized_profit_raw="7990000",
        event_type=CycleEventType.SETTLED,
    )

    c2 = cycle_logger.open_c2(
        opp.opportunity_id,
        c1_tx_hash="0xc1tx",
        c1_confirmed_block=90213723,
        post_c1_state_hash="0xstate_post_c1",
        window_blocks=5,
        c2_route_hash="0xroute_c2_reverse",
    )
    assert c2 is not None
    assert c2.parent_c1_cycle_id == c1.c1_cycle_id

    cycle_logger.decide_c2(
        opp.opportunity_id,
        decision="REVERSE",
        mirror_expected_net_usd="-1.42",
        reverse_expected_net_usd="6.36",
        selected_expected_net_usd="6.36",
        c2_route_hash="0xroute_c2_reverse",
        c2_eval_block=90213724,
    )
    cycle_logger.update_c2(
        opp.opportunity_id,
        simulation_status="PASSED",
        payload_status="BUILT",
        submission_status="SUBMITTED_PRIVATE",
        tx_hash="0xc2tx",
        submitted_block=90213724,
        event_type=CycleEventType.SUBMITTED_PRIVATE,
    )
    cycle_logger.update_c2(
        opp.opportunity_id,
        submission_status="CONFIRMED",
        settlement_status="SETTLED",
        tx_hash="0xc2tx",
        confirmed_block=90213724,
        realized_net_usd="5.68",
        realized_gross_usd="12.92",
        realized_gas_usd="2.74",
        realized_profit_raw="5680000",
        event_type=CycleEventType.SETTLED,
    )

    state = cycle_logger.machine_state(opp.opportunity_id)
    assert state is not None
    assert state["status"] == "CLOSED_PROFITABLE"
    assert Decimal(state["pnl"]["c1_realized_net_usd"]) == Decimal("7.99")
    assert Decimal(state["pnl"]["c2_realized_net_usd"]) == Decimal("5.68")
    assert Decimal(state["pnl"]["combined_realized_net_usd"]) == Decimal("13.67")
    assert state["c2"]["decision"] == "REVERSE"
    assert state["c2"]["parent_c1_cycle_id"] == c1.c1_cycle_id

    events = cycle_logger.recent_events(opportunity_id=opp.opportunity_id, limit=100)
    types = {e["event_type"] for e in events}
    assert "DISCOVERED" in types
    assert "SETTLED" in types
    assert "C2_WINDOW_OPENED" in types


def test_c1_fail_cancels_c2():
    opp = cycle_logger.register_opportunity(
        chain_id=137,
        discovered_block=100,
        buy_pool="0x1",
        sell_pool="0x2",
        borrow_asset="USDC",
        pool_sequence=["0x1", "0x2"],
    )
    cycle_logger.open_c1(opp.opportunity_id, discovery_block=100, expected_net_usd="1")
    cycle_logger.update_c1(
        opp.opportunity_id,
        simulation_status="PASSED",
        submission_status="SUBMITTED_PRIVATE",
        tx_hash="0xfail",
        submitted_block=101,
    )
    cycle_logger.update_c1(
        opp.opportunity_id,
        settlement_status="REVERTED",
        submission_status="REVERTED",
        reject_reason="SIM_PASSED_BUT_TX_REVERTED",
        event_type=CycleEventType.REVERTED,
    )
    # open_c2 should refuse without confirmed success
    c2 = cycle_logger.open_c2(
        opp.opportunity_id,
        c1_tx_hash="0xfail",
        c1_confirmed_block=101,
        post_c1_state_hash="sh",
    )
    # After revert, settlement is REVERTED — open_c2 must cancel
    assert c2 is None
    rec = cycle_logger.get_opportunity(opp.opportunity_id)
    assert rec.final_status == "CLOSED_C1_FAILED"


def test_c2_do_nothing():
    opp = cycle_logger.register_opportunity(
        chain_id=137,
        discovered_block=200,
        buy_pool="0xa",
        sell_pool="0xb",
        borrow_asset="USDC",
        pool_sequence=["0xa", "0xb"],
    )
    cycle_logger.open_c1(opp.opportunity_id, discovery_block=200)
    cycle_logger.update_c1(
        opp.opportunity_id,
        settlement_status="SETTLED",
        submission_status="CONFIRMED",
        tx_hash="0xc1ok",
        confirmed_block=201,
        realized_net_usd="7.99",
        event_type=CycleEventType.SETTLED,
    )
    cycle_logger.open_c2(
        opp.opportunity_id,
        c1_tx_hash="0xc1ok",
        c1_confirmed_block=201,
        post_c1_state_hash="post",
    )
    cycle_logger.decide_c2(
        opp.opportunity_id,
        decision="DO_NOTHING",
        mirror_expected_net_usd="-0.84",
        reverse_expected_net_usd="2.11",
        selected_expected_net_usd="0",
        reject_reason="NO_C2_BRANCH_ABOVE_MIN_NET_PROFIT",
    )
    state = cycle_logger.machine_state(opp.opportunity_id)
    assert state["status"] == "CLOSED_C1_ONLY_PROFITABLE"
    assert Decimal(state["pnl"]["combined_realized_net_usd"]) == Decimal("7.99")
    assert state["c2"]["decision"] == "DO_NOTHING"


def test_c2_expired():
    opp = cycle_logger.register_opportunity(
        chain_id=137,
        discovered_block=300,
        buy_pool="0xa",
        sell_pool="0xb",
        borrow_asset="WETH",
        pool_sequence=["0xa", "0xb"],
    )
    cycle_logger.open_c1(opp.opportunity_id, discovery_block=300)
    cycle_logger.update_c1(
        opp.opportunity_id,
        settlement_status="SETTLED",
        submission_status="CONFIRMED",
        tx_hash="0xc1",
        confirmed_block=301,
        realized_net_usd="1.00",
        event_type=CycleEventType.SETTLED,
    )
    cycle_logger.open_c2(
        opp.opportunity_id,
        c1_tx_hash="0xc1",
        c1_confirmed_block=301,
        post_c1_state_hash="post",
    )
    cycle_logger.decide_c2(
        opp.opportunity_id,
        decision="EXPIRED",
        c2_eval_block=310,
        reject_reason="C2_WINDOW_EXPIRED",
    )
    state = cycle_logger.machine_state(opp.opportunity_id)
    assert state["status"] == "CLOSED_C2_EXPIRED"
