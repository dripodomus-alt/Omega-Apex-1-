#!/usr/bin/env python3
# ==============================================================================
# reverse_surplus_report.py -- read-only surplus/depth route report.
#
# This command does not sign, broadcast, or mutate chain state. It reuses the
# live pool loader, quoter-backed CLMM pricing, profitability model, and final
# executor eth_call truth gate, then prints the route surplus equation backward
# from gross output to net surplus.
# ==============================================================================

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Iterable

from . import rpc_layer
from .arbitrage import ArbitrageGraphEngine, detect_four_leg_cycles, detect_three_leg_cycles, merge_cycle_sets
from .execution_truth import ExecutionTruthResult, final_truth_rank, truth_summary
from .executable_quotes import quote_route_for_executor
from .flash_loan import FlashSource, MIN_NET_PROFIT_USD
from .preflight import run_preflight_simulation
from .flash_loan import evaluate_profitability
from .opportunity_ranker import (
    LiveOpportunity,
    RoutePriceStep,
    score_cross_pool_spreads,
    rerank_by_ml_alpha,
    score_opportunities,
    score_pegged_stable_spreads,
)
from .oracle_layer import PriceUnavailable, refresh_token_prices, token_price_usd
from .ranker import compute_all_pool_rates, detect_cross_pool_two_leg_spreads
from .rpc_layer import DEEP_POOL_REGISTRY, TOKEN_DECIMALS
from .sizing import estimate_pool_tvl_usd
from .sizing import optimize_route_principal
from .stable_strategies import detect_pegged_stable_spreads, spread_key


@dataclass(frozen=True)
class RouteSurplus:
    base_token: str
    principal_usd: Decimal
    principal_base: Decimal
    principal_raw: int
    gross_output_base: Decimal
    gross_output_raw: int
    gross_output_usd: Decimal
    raw_delta_usd: Decimal
    flash_fee_usd: Decimal
    gas_cost_usd: Decimal
    relay_tip_usd: Decimal
    risk_buffer_usd: Decimal
    other_costs_usd: Decimal
    net_surplus_usd: Decimal
    flash_fee_raw: int
    gas_cost_raw: int
    relay_cost_raw: int
    risk_buffer_raw: int
    other_costs_raw: int
    minimum_profit_raw: int
    executable_threshold_raw: int
    raw_executable_inequality_pass: bool
    two_leg: dict[str, Any]


def _money(value: Decimal | str | int | float) -> str:
    try:
        dec = Decimal(str(value))
    except Exception:
        return str(value)
    return f"{dec:.8f}"


def _raw_units(symbol: str, amount: Decimal) -> int:
    decimals = int(TOKEN_DECIMALS.get(symbol, 18))
    raw = Decimal(amount) * (Decimal(10) ** decimals)
    return int(raw.to_integral_value(rounding=ROUND_FLOOR))


def _asset_units_from_usd(symbol: str, usd_amount: Decimal, token_usd: Decimal) -> Decimal:
    if token_usd <= 0:
        return Decimal("0")
    return Decimal(usd_amount) / token_usd


def _token_depth_usd(pool: dict[str, Any], token: str) -> tuple[Decimal, str]:
    executable_depths = pool.get("executable_token_depth_usd")
    if isinstance(executable_depths, dict) and token in executable_depths:
        try:
            depth = Decimal(str(executable_depths[token]))
            if depth > 0:
                return depth, "executable_token_depth_usd"
        except ArithmeticError:
            pass

    tokens = pool.get("tokens", [])
    reserves = pool.get("reserves", [])
    if token in tokens and reserves and len(reserves) == len(tokens):
        try:
            reserve = Decimal(str(reserves[tokens.index(token)]))
            return reserve * token_price_usd(token), "reserve_x_oracle"
        except (PriceUnavailable, ArithmeticError, IndexError):
            pass

    tvl = estimate_pool_tvl_usd(pool)
    if tvl > 0:
        divisor = Decimal(max(1, len(tokens) or 2))
        return tvl / divisor, "tvl_even_split_estimate"
    return Decimal("0"), "unavailable"


def _route_depth(pools: dict[str, dict], op: LiveOpportunity) -> dict[str, Any]:
    hop_rows: list[dict[str, str]] = []
    depth_values: list[Decimal] = []

    for idx, pool_id in enumerate(op.pool_sequence):
        pool = pools.get(pool_id, {})
        token_in = op.path[idx] if idx < len(op.path) else ""
        token_out = op.path[idx + 1] if idx + 1 < len(op.path) else ""
        tvl = estimate_pool_tvl_usd(pool) if pool else Decimal("0")
        depth_in, depth_in_source = _token_depth_usd(pool, token_in) if pool and token_in else (Decimal("0"), "unavailable")
        depth_out, depth_out_source = _token_depth_usd(pool, token_out) if pool and token_out else (Decimal("0"), "unavailable")
        usable = min([value for value in (depth_in, depth_out, tvl) if value > 0] or [Decimal("0")])
        if usable > 0:
            depth_values.append(usable)
        hop_rows.append({
            "hop": str(idx + 1),
            "pool_id": pool_id,
            "protocol": str(pool.get("protocol", "")),
            "token_in": token_in,
            "token_out": token_out,
            "total_executable_liquidity_usd": str(pool.get("total_executable_liquidity_usd", tvl)),
            "pool_tvl_usd": str(tvl),
            "token_in_depth_usd": str(depth_in),
            "token_in_depth_source": depth_in_source,
            "token_out_depth_usd": str(depth_out),
            "token_out_depth_source": depth_out_source,
            "usable_depth_usd": str(usable),
        })

    two_leg_mid = {}
    if len(op.path) == 3 and len(op.pool_sequence) == 2:
        mid = op.path[1]
        buy_pool = pools.get(op.pool_sequence[0], {})
        sell_pool = pools.get(op.pool_sequence[1], {})
        buy_depth, buy_source = _token_depth_usd(buy_pool, mid)
        sell_depth, sell_source = _token_depth_usd(sell_pool, mid)
        two_leg_mid = {
            "mid_token": mid,
            "buy_pool_mid_depth_usd": str(buy_depth),
            "buy_pool_mid_depth_source": buy_source,
            "sell_pool_mid_depth_usd": str(sell_depth),
            "sell_pool_mid_depth_source": sell_source,
            "buy_pool_tvl_usd": str(estimate_pool_tvl_usd(buy_pool)),
            "sell_pool_tvl_usd": str(estimate_pool_tvl_usd(sell_pool)),
            "buy_pool_total_executable_liquidity_usd": str(buy_pool.get("total_executable_liquidity_usd", estimate_pool_tvl_usd(buy_pool))),
            "sell_pool_total_executable_liquidity_usd": str(sell_pool.get("total_executable_liquidity_usd", estimate_pool_tvl_usd(sell_pool))),
        }
    return {
        "route_limiting_depth_usd": str(min(depth_values) if depth_values else Decimal("0")),
        "hops": hop_rows,
        "two_leg_mid": two_leg_mid,
    }


def _route_surplus(pools: dict[str, dict], op: LiveOpportunity) -> RouteSurplus | None:
    cached = op.metadata.get("_reverse_surplus_cache") if isinstance(op.metadata, dict) else None
    if isinstance(cached, RouteSurplus):
        return cached

    base = op.path[0]
    try:
        base_usd = token_price_usd(base)
    except PriceUnavailable:
        return None
    if base_usd <= 0:
        return None

    principal_usd = Decimal(str(op.profitability.flashloan.principal_usd))
    principal_base = principal_usd / base_usd
    quote = quote_route_for_executor(op.path, op.pool_sequence, pools, principal_base)
    if quote.amount_out <= 0:
        return None

    gross_output_base = quote.amount_out
    gross_output_usd = gross_output_base * base_usd
    raw_delta_usd = gross_output_usd - principal_usd
    p = op.profitability
    other_costs_usd = Decimal("0")
    net_surplus_usd = (
        raw_delta_usd
        - p.flashloan.fee_usd
        - p.gas_cost_usd
        - p.relay_tip_usd
        - p.risk_buffer_usd
        - other_costs_usd
    )

    flash_fee_base = _asset_units_from_usd(base, p.flashloan.fee_usd, base_usd)
    gas_cost_base = _asset_units_from_usd(base, p.gas_cost_usd, base_usd)
    relay_base = _asset_units_from_usd(base, p.relay_tip_usd, base_usd)
    risk_base = _asset_units_from_usd(base, p.risk_buffer_usd, base_usd)
    other_base = _asset_units_from_usd(base, other_costs_usd, base_usd)
    minimum_profit_base = _asset_units_from_usd(base, MIN_NET_PROFIT_USD, base_usd)

    principal_raw = _raw_units(base, principal_base)
    gross_output_raw = _raw_units(base, gross_output_base)
    flash_fee_raw = _raw_units(base, flash_fee_base)
    gas_cost_raw = _raw_units(base, gas_cost_base)
    relay_cost_raw = _raw_units(base, relay_base)
    risk_buffer_raw = _raw_units(base, risk_base)
    other_costs_raw = _raw_units(base, other_base)
    minimum_profit_raw = _raw_units(base, minimum_profit_base)
    threshold_raw = (
        principal_raw
        + flash_fee_raw
        + gas_cost_raw
        + relay_cost_raw
        + risk_buffer_raw
        + other_costs_raw
        + minimum_profit_raw
    )

    two_leg: dict[str, Any] = {}
    if len(op.path) == 3 and len(op.pool_sequence) == 2:
        mid = op.path[1]
        leg1 = quote_route_for_executor(op.path[:2], op.pool_sequence[:1], pools, principal_base)
        if leg1.amount_out > 0:
            mid_units = leg1.amount_out
            buy_cost = principal_usd / mid_units
            sell_value = gross_output_usd / mid_units
            spread = sell_value - buy_cost
            recomputed_raw_delta = spread * mid_units
            two_leg = {
                "mid_token": mid,
                "Q_mid_units": str(mid_units),
                "buy_cost_per_mid_unit_usd": str(buy_cost),
                "sell_value_per_mid_unit_usd": str(sell_value),
                "spread_per_mid_unit_usd": str(spread),
                "raw_delta_from_spread_usd": str(recomputed_raw_delta),
                "raw_delta_identity_pass": abs(recomputed_raw_delta - raw_delta_usd) <= Decimal("0.00000001"),
            }

    return RouteSurplus(
        base_token=base,
        principal_usd=principal_usd,
        principal_base=principal_base,
        principal_raw=principal_raw,
        gross_output_base=gross_output_base,
        gross_output_raw=gross_output_raw,
        gross_output_usd=gross_output_usd,
        raw_delta_usd=raw_delta_usd,
        flash_fee_usd=p.flashloan.fee_usd,
        gas_cost_usd=p.gas_cost_usd,
        relay_tip_usd=p.relay_tip_usd,
        risk_buffer_usd=p.risk_buffer_usd,
        other_costs_usd=other_costs_usd,
        net_surplus_usd=net_surplus_usd,
        flash_fee_raw=flash_fee_raw,
        gas_cost_raw=gas_cost_raw,
        relay_cost_raw=relay_cost_raw,
        risk_buffer_raw=risk_buffer_raw,
        other_costs_raw=other_costs_raw,
        minimum_profit_raw=minimum_profit_raw,
        executable_threshold_raw=threshold_raw,
        raw_executable_inequality_pass=gross_output_raw > threshold_raw,
        two_leg=two_leg,
    )


def _scan_ranked(principal: Decimal) -> tuple[dict[str, dict], dict, list[LiveOpportunity], dict[str, Any]]:
    pools = rpc_layer.load_all_live_pools(DEEP_POOL_REGISTRY)
    refresh_token_prices(force=True)
    rates = compute_all_pool_rates(pools)
    two_leg = detect_cross_pool_two_leg_spreads(rates)
    stable = detect_pegged_stable_spreads(two_leg)
    stable_keys = {spread_key(item.spread) for item in stable}
    non_stable = [spread for spread in two_leg if spread_key(spread) not in stable_keys]
    engine = ArbitrageGraphEngine(rates)
    cycles = merge_cycle_sets(
        engine.bellman_ford_all_sources(),
        detect_three_leg_cycles(rates),
        detect_four_leg_cycles(rates),
    )
    ranked = sorted(
        score_pegged_stable_spreads(stable, pools, principal, FlashSource.BALANCER)
        + score_cross_pool_spreads(non_stable, pools, principal, FlashSource.BALANCER)
        + score_opportunities(cycles, pools, rates, principal, FlashSource.BALANCER),
        key=lambda item: item.profitability.net_profit_usd,
        reverse=True,
    )
    # --- ML Alpha Re-ranking ---
    # Re-rank the opportunities based on the ML model's prediction of success.
    # This is a fail-closed operation; if the model is not ready, it returns the original list.
    ranked = rerank_by_ml_alpha(ranked)


    # --- Pre-flight Simulation Integration ---
    # Here, we take the top-ranked opportunities and run them through the
    # pre-flight simulation truth gate.
    preflight_results = []
    for op in ranked[:max(1, int(args.max_opps))]:
        sim_ok, sim_profit_raw = run_preflight_simulation(op.as_dict())
        preflight_results.append({
            "opp_id": op.opp_id,
            "simulation_ok": sim_ok,
            "simulated_net_profit_raw": sim_profit_raw,
        })

    stats = {
        "pools_loaded": len(pools),
        "rate_pairs": len(rates),
        "directional_quotes": sum(len(items) for items in rates.values()),
        "two_leg_spreads": len(two_leg),
        "stable_spreads": len(stable),
        "cycles_detected": len(cycles),
        "ranked_profit_gate": len(ranked),
        "preflight_simulations_run": len(preflight_results),
    }
    return pools, rates, ranked, stats


def _diagnostic_two_leg_candidates(
    *,
    pools: dict[str, dict],
    rates: dict,
    principal_usd: Decimal,
    limit: int,
) -> list[ExecutionTruthResult]:
    rows: list[tuple[Decimal, ExecutionTruthResult]] = []
    approximate: list[tuple[Decimal, dict, dict, str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for (token_a, token_b), buy_quotes in rates.items():
        sell_quotes = rates.get((token_b, token_a), [])
        if not sell_quotes:
            continue
        for buy in buy_quotes[:4]:
            for sell in sell_quotes[:4]:
                if buy.get("route_class") != "NATIVE_POOL_ROUTE" or sell.get("route_class") != "NATIVE_POOL_ROUTE":
                    continue
                if buy.get("liquidity_key") == sell.get("liquidity_key"):
                    continue
                key = (token_a, token_b, str(buy.get("liquidity_key")), str(sell.get("liquidity_key")))
                if key in seen:
                    continue
                seen.add(key)
                try:
                    approximate_score = Decimal(str(buy["rate"])) * Decimal(str(sell["rate"]))
                except Exception:
                    continue
                approximate.append((approximate_score, buy, sell, token_a, token_b))

    approximate.sort(key=lambda item: item[0], reverse=True)
    for _, buy, sell, token_a, token_b in approximate:
        pool_sequence = [str(buy["pool_id"]), str(sell["pool_id"])]
        if any(pool_id not in pools for pool_id in pool_sequence):
            continue
        try:
            base_usd = token_price_usd(token_a)
        except PriceUnavailable:
            continue
        sizing = optimize_route_principal(principal_usd, pool_sequence, pools)
        if base_usd <= 0 or sizing.selected_principal_usd <= 0:
            continue
        principal_base = sizing.selected_principal_usd / base_usd
        route_quote = quote_route_for_executor([token_a, token_b, token_a], pool_sequence, pools, principal_base)
        if route_quote.amount_out <= 0:
            continue
        gross_out_usd = route_quote.amount_out * base_usd
        profitability = evaluate_profitability(
            gross_out_usd,
            sizing.selected_principal_usd,
            hops=2,
            flash_source=FlashSource.BALANCER,
            asset=token_a,
        )
        buy_rate = Decimal(str(buy["rate"]))
        sell_rate = Decimal(str(sell["rate"]))
        pricing_steps = [
            RoutePriceStep(
                step_id=1,
                label="BUY_LEG1_PRICE",
                token_in=token_a,
                token_out=token_b,
                pool_id=str(buy["pool_id"]),
                protocol=str(buy["protocol"]),
                liquidity_key=str(buy["liquidity_key"]),
                rate=buy_rate,
                effective_price=(Decimal("1") / buy_rate) if buy_rate > 0 else Decimal("0"),
                price_unit=f"{token_a} per {token_b}",
                invariant=str(buy.get("invariant", "")),
            ),
            RoutePriceStep(
                step_id=2,
                label="SELL_LEG2_PRICE",
                token_in=token_b,
                token_out=token_a,
                pool_id=str(sell["pool_id"]),
                protocol=str(sell["protocol"]),
                liquidity_key=str(sell["liquidity_key"]),
                rate=sell_rate,
                effective_price=sell_rate,
                price_unit=f"{token_a} per {token_b}",
                invariant=str(sell.get("invariant", "")),
            ),
        ]
        metadata = {
            "opp_id": f"DIAG-{len(rows) + 1:04d}",
            "strategy": "DIAGNOSTIC_TWO_LEG",
            "schema_version": "omega_v5.diagnostic_opportunity.v1",
            "pricing_step_schema": "mandatory",
            "price_rule": "diagnostic quote-aligned two-leg round trip",
            "hop_count": 2,
            "pricing_steps": [step.__dict__ for step in pricing_steps],
            "liquidity_keys": [str(buy["liquidity_key"]), str(sell["liquidity_key"])],
            "pool_addresses": [str(pools[pool_sequence[0]].get("address", "")), str(pools[pool_sequence[1]].get("address", ""))],
            "sizing": {
                "requested_principal_usd": str(sizing.requested_principal_usd),
                "selected_principal_usd": str(sizing.selected_principal_usd),
                "min_pool_tvl_usd": str(sizing.min_pool_tvl_usd),
                "route_cap_usd": str(sizing.route_cap_usd),
                "minimum_principal_usd": str(sizing.minimum_principal_usd),
                "max_route_tvl_fraction": str(sizing.max_route_fraction),
                "sizing_method": sizing.method,
                "sizing_reason": sizing.reason,
                "flash_size_ladder_usd": [str(step) for step in sizing.ladder_steps_usd],
            },
        }
        op = LiveOpportunity(
            path=[token_a, token_b, token_a],
            pool_sequence=pool_sequence,
            protocol_seq=[str(buy["protocol"]), str(sell["protocol"])],
            gross_rate=(gross_out_usd / sizing.selected_principal_usd) if sizing.selected_principal_usd > 0 else Decimal("0"),
            gross_out_usd=gross_out_usd,
            profitability=profitability,
            block_detected=rpc_layer.BLOCK,
            flash_source=FlashSource.BALANCER,
            metadata=metadata,
        )
        displayed_surplus = _route_surplus(pools, op)
        if displayed_surplus is not None:
            op.metadata["_reverse_surplus_cache"] = displayed_surplus
        sort_net = displayed_surplus.net_surplus_usd if displayed_surplus is not None else profitability.net_profit_usd
        detail_gross = displayed_surplus.gross_output_usd if displayed_surplus is not None else gross_out_usd
        detail = (
            "quote_aligned_profitability_gate_failed:"
            f"net_usd={sort_net}:"
            f"principal_usd={sizing.selected_principal_usd}:gross_out_usd={detail_gross}"
        )
        result = ExecutionTruthResult(
            original=op,
            opportunity=None,
            executable=False,
            tested_sizes_usd=[str(sizing.selected_principal_usd)],
            exact_call_detail=detail,
            rejection_class="quote_aligned_not_profitable",
            quote_detail=detail,
        )
        rows.append((sort_net, result))

    rows.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in rows[:limit]]


def _failure_stage(result: ExecutionTruthResult) -> str:
    cls = result.rejection_class
    detail = result.exact_call_detail or result.quote_detail
    if cls == "executor_semantics_quote_failed":
        return "quote_unproven"
    if cls == "quote_aligned_not_profitable":
        return "quote_aligned_not_profitable"
    if cls in {"route_pool_kind_unset", "bad_route_semantics", "unsupported_pool", "payload_build_failed", "candidate_retarget_failed"}:
        return "route_semantics_failed"
    if cls in {"slippage_or_profit_floor", "executor_revert", "eth_call_failed", "decoded_non_positive_profit"}:
        return "executor_eth_call_failed"
    if "depth" in str(detail).lower() or "tvl" in str(detail).lower():
        return "pool_depth_unavailable"
    return cls or "route_semantics_failed"


def _needed_for_execution(stage: str) -> str:
    return {
        "quote_unproven": "valid quoter output for every CLMM hop at the selected flash size",
        "quote_aligned_not_profitable": "higher raw delta, lower gas/fees, or smaller route impact after exact quote alignment",
        "executor_eth_call_failed": "executor eth_call must pass under adapter slippage/profit floor",
        "pool_depth_unavailable": "fresh pool TVL/depth state from live sources",
        "route_semantics_failed": "valid adapter route semantics, pool kind mapping, and calldata shape",
    }.get(stage, "a route that passes quote, profitability, and executor truth gates")


def _print_route(
    *,
    rank: int,
    op: LiveOpportunity,
    pools: dict[str, dict],
    executable_status: str,
    truth: ExecutionTruthResult | None = None,
) -> bool:
    surplus = _route_surplus(pools, op)
    if surplus is None:
        print(f"\n#{rank:02d} {op.opp_id} {executable_status} path={' -> '.join(op.path)}")
        print("  surplus_math=unavailable reason=quote_or_price_unavailable")
        return False

    depth = _route_depth(pools, op)
    print(f"\n#{rank:02d} {op.opp_id} {executable_status}")
    print(f"  path={' -> '.join(op.path)}")
    print(f"  strategy={op.strategy} protocols={op.protocol_seq}")
    print(f"  pools={op.pool_sequence}")
    print(f"  route_limiting_depth_usd={_money(depth['route_limiting_depth_usd'])}")
    if depth["two_leg_mid"]:
        mid = depth["two_leg_mid"]
        print(
            "  mid_pool_depth="
            f"{mid['mid_token']} buy_pool=${_money(mid['buy_pool_mid_depth_usd'])}({mid['buy_pool_mid_depth_source']}) "
            f"sell_pool=${_money(mid['sell_pool_mid_depth_usd'])}({mid['sell_pool_mid_depth_source']})"
        )
        print(
            "  mid_pool_tvl="
            f"buy_pool=${_money(mid['buy_pool_tvl_usd'])} sell_pool=${_money(mid['sell_pool_tvl_usd'])}"
        )
    else:
        for hop in depth["hops"]:
            print(
                f"  hop{hop['hop']}_depth pool={hop['pool_id']} tvl=${_money(hop['pool_tvl_usd'])} "
                f"{hop['token_in']}=${_money(hop['token_in_depth_usd'])} "
                f"{hop['token_out']}=${_money(hop['token_out_depth_usd'])}"
            )

    sizing = op.metadata.get("sizing", {}) if isinstance(op.metadata, dict) else {}
    print(
        "  flash_size="
        f"requested_usd={sizing.get('requested_principal_usd', surplus.principal_usd)} "
        f"selected_usd={_money(surplus.principal_usd)} "
        f"route_cap_usd={sizing.get('route_cap_usd', 'n/a')} "
        f"minimum_usd={sizing.get('minimum_principal_usd', 'n/a')} "
        f"selected_{surplus.base_token}={surplus.principal_base} "
        f"selected_raw={surplus.principal_raw} "
        f"reason={sizing.get('sizing_reason', sizing.get('reason', 'profitability.flashloan.principal_usd'))}"
    )
    print(
        "  raw_surplus="
        f"P=${_money(surplus.principal_usd)} "
        f"R=${_money(surplus.gross_output_usd)} "
        f"RawDeltaUSD=R-P=${_money(surplus.raw_delta_usd)}"
    )
    print(
        "  accounting_schema="
        "omega_v5.arbitrage_accounting.v2 "
        "RawDeltaUSD=GrossOutputUSD-PrincipalUSD "
        "RawDeltaUSD=SpreadUSDPerUnit*UnitsPurchased "
        "NetDeltaUSD=RawDeltaUSD-ExpensesUSD "
        "do_not_subtract_principal_again=True"
    )
    if surplus.two_leg:
        two = surplus.two_leg
        print(
            "  two_leg_unit_math="
            f"Q={two['Q_mid_units']} {two['mid_token']} "
            f"buy_usd_per_mid={two['buy_cost_per_mid_unit_usd']} "
            f"sell_usd_per_mid={two['sell_value_per_mid_unit_usd']} "
            f"spread_usd_per_mid={two['spread_per_mid_unit_usd']} "
            f"spread_x_Q=${_money(two['raw_delta_from_spread_usd'])} "
            f"identity_pass={two['raw_delta_identity_pass']}"
        )
    print(
        "  net_surplus_equation="
        f"{_money(surplus.raw_delta_usd)}"
        f" - flash_fee({_money(surplus.flash_fee_usd)})"
        f" - gas({_money(surplus.gas_cost_usd)})"
        f" - relay({_money(surplus.relay_tip_usd)})"
        f" - risk({_money(surplus.risk_buffer_usd)})"
        f" - other({_money(surplus.other_costs_usd)})"
        f" = {_money(surplus.net_surplus_usd)}"
    )
    print(
        "  raw_executable_equation="
        f"sellAmountOutRaw({surplus.gross_output_raw}) > "
        f"principal({surplus.principal_raw}) + flashFee({surplus.flash_fee_raw}) + gas({surplus.gas_cost_raw}) "
        f"+ relay({surplus.relay_cost_raw}) + risk({surplus.risk_buffer_raw}) "
        f"+ other({surplus.other_costs_raw}) + minProfit({surplus.minimum_profit_raw}) "
        f"= {surplus.executable_threshold_raw} pass={surplus.raw_executable_inequality_pass}"
    )
    if truth and not truth.executable:
        stage = _failure_stage(truth)
        print(f"  diagnostic_stage={stage}")
        print(f"  rejection_detail={(truth.exact_call_detail or truth.quote_detail)[:420]}")
        print(f"  needed_for_execution={_needed_for_execution(stage)}")
    return True


def report(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only reverse surplus route report")
    parser.add_argument("--rpc-url", default="", help="Polygon read RPC URL")
    parser.add_argument("--principal", default="50000", help="Requested principal USD")
    parser.add_argument("--top", type=int, default=20, help="Rows to print")
    parser.add_argument("--max-opps", type=int, default=50, help="Ranked opportunities to exact-call truth test")
    parser.add_argument("--include-diagnostics", action="store_true", help="Print non-executable diagnostics after executable routes")
    args = parser.parse_args(list(argv) if argv is not None else None)

    top = max(1, int(args.top))
    principal = Decimal(str(args.principal))
    if not rpc_layer.connect(http_urls=[args.rpc_url] if args.rpc_url else None, wss_url="", prefer_wss=False):
        print("reverse_surplus_report=FAIL reason=rpc_connect_false", flush=True)
        return 1
    print(f"reverse_surplus_report_rpc=OK block={rpc_layer.BLOCK}")

    pools, rates, ranked, stats = _scan_ranked(principal)
    print(
        "scan_summary="
        f"pools_loaded={stats['pools_loaded']} "
        f"rate_pairs={stats['rate_pairs']} "
        f"directional_quotes={stats['directional_quotes']} "
        f"two_leg_spreads={stats['two_leg_spreads']} "
        f"stable_spreads={stats['stable_spreads']} "
        f"cycles_detected={stats['cycles_detected']} "
        f"ranked_profit_gate={stats['ranked_profit_gate']}"
    )
    print(
        "preflight_summary="
        f"simulations_run={stats['preflight_simulations_run']} "
        f"executable_found={sum(1 for r in stats.get('preflight_results', []) if r.get('simulated_net_profit_raw', 0) > 0)}"
    )

    try:
        from .gas_oracle import base_fee_gwei as _base_fee_gwei

        base_fee_gwei, gas_fee_source = _base_fee_gwei()
        print(f"gas_fee_source={gas_fee_source} base_fee_gwei={base_fee_gwei}")
    except Exception as exc:
        print(f"reverse_surplus_report=BLOCKED reason=gas_price_read_failed detail={type(exc).__name__}: {exc}")
        return 2

    executable, truth_results = final_truth_rank(
        ranked,
        pools,
        base_fee_gwei=base_fee_gwei,
        max_candidates=max(1, int(args.max_opps)),
    )
    summary = truth_summary(truth_results)
    print(
        "truth_summary="
        f"inspected={summary['inspected']} "
        f"executable_count={summary['executable']} "
        f"rejections={summary['rejection_classes']}"
    )

    printed = 0
    print("\nEXECUTABLE_SURPLUS_ROUTES")
    if not executable:
        print("  executable_count=0 reason=no route passed final executor truth gate")
    for op in executable[:top]:
        printed += 1
        _print_route(rank=printed, op=op, pools=pools, executable_status="EXECUTABLE", truth=None)

    if args.include_diagnostics and printed < top:
        print("\nDIAGNOSTIC_NON_EXECUTABLE_ROUTES")
        diagnostics = [row for row in truth_results if not row.executable]
        if len(diagnostics) < top - printed:
            diagnostics.extend(
                _diagnostic_two_leg_candidates(
                    pools=pools,
                    rates=rates,
                    principal_usd=principal,
                    limit=(top - printed - len(diagnostics)),
                )
            )
        if not diagnostics:
            print("  diagnostic_count=0 reason=no profit-gated route candidates were available to truth-test")
        for row in diagnostics[: top - printed]:
            printed += 1
            _print_route(
                rank=printed,
                op=row.original,
                pools=pools,
                executable_status="NON_EXECUTABLE",
                truth=row,
            )

    print(f"\nreverse_surplus_report=PASS printed_rows={printed} requested_top={top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(report())
