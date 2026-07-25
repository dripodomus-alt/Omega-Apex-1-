#!/usr/bin/env python3
# ==============================================================================
# pipeline_validation.py -- read-only validation for discovery -> execution handoff.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from web3 import Web3

from . import rpc_layer
from .arbitrage import (
    ArbitrageGraphEngine,
)
from .adapter_registry import configured_adapters, resolve_capital_source_adapter
from .adapter_registry import AdapterSemanticError
from .aave_liquidations import AaveLiquidationScanner
from .config import (
    CHAIN_ID,
    CONFIRM_FLAG,
    ENABLE_LIQUIDATION_PIPELINE,
    EXEC_MODE,
    FORK_SIM_RPC_URL,
    MIN_FLASH_PRINCIPAL_USD,
    MAX_FLASH_PRINCIPAL_USD,
    FLASH_ROUTE_TVL_FRACTIONS,
    MAX_ROUTE_IMPACT,
    LIVE_FLAG,
    REQUIRED_CONFIRM,
)
from .execution import (
    EXECUTE_FLASH_ARB_SELECTOR,
    build_c1_payload_envelope,
    build_c2_payload_envelope,
    build_tx_payload,
    execution_armed,
    execution_guard_status,
    executor_owner,
    executor_code_status,
    simulation_from_address,
)
from .flash_loan import FlashSource
from .fork_rpc import resolve_fork_upstream
from .liquidity_registry import build_verified_pool_registry, registry_summary
from .liquidation_execution import (
    build_liquidation_tx,
    build_liquidation_payload_envelope,
    simulate_liquidation,
)
from .opportunity_ranker import (
    LiveOpportunity,
    score_pegged_stable_spreads,
    score_cross_pool_spreads,
    score_opportunities,
)
from .execution_truth import final_truth_rank, truth_summary
from .oracle_layer import refresh_token_prices
from .ranker import compute_all_pool_rates, detect_cross_pool_two_leg_spreads
from .route_execution_stager import pre_rank_routes
from .redis_cache import status as redis_status
from .revert_decoder import format_revert
from .rpc_layer import DEEP_POOL_REGISTRY
from .runtime_control import runtime_mode, runtime_settings
from .stable_strategies import detect_pegged_stable_spreads, spread_key


ROOT = Path(__file__).resolve().parents[1]
LIVE_POOL_SCAN_REPORT = ROOT / "out" / "live_pool_scan_report.json"
PIPELINE_VALIDATION_REPORT = ROOT / "out" / "pipeline_validation_latest.json"


def _candidate_signature(candidate: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if hasattr(candidate, "path") and hasattr(candidate, "pool_sequence"):
        return (
            tuple(str(item) for item in getattr(candidate, "path", ()) or ()),
            tuple(str(item) for item in getattr(candidate, "pool_sequence", ()) or ()),
        )
    if isinstance(candidate, dict):
        path = tuple(str(item) for item in candidate.get("path", []) or [])
        pools = tuple(
            str(edge.get("pool_id") or "")
            for edge in candidate.get("edges", []) or []
            if isinstance(edge, dict)
        )
        return path, pools
    return tuple(), tuple()


def _dedupe_candidates(candidates: Iterable[object]) -> list[object]:
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    deduped: list[object] = []
    for candidate in candidates:
        signature = _candidate_signature(candidate)
        if not signature[0] or signature in seen:
            continue
        seen.add(signature)
        deduped.append(candidate)
    return deduped


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)) or default)
    except Exception:
        return default


def _json_ready(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(v) for v in value]
    return value


def _liquidity_summary(pools: dict) -> dict[str, object]:
    positive: list[Decimal] = []
    zero = 0
    missing = 0
    for pool in pools.values():
        if "total_executable_liquidity_usd" not in pool:
            missing += 1
            continue
        try:
            value = Decimal(str(pool.get("total_executable_liquidity_usd") or 0))
        except Exception:
            value = Decimal("0")
        if value > 0:
            positive.append(value)
        else:
            zero += 1
    return {
        "with_positive_total_executable_liquidity": len(positive),
        "zero_total_executable_liquidity": zero,
        "missing_schema": missing,
        "min_positive_usd": min(positive) if positive else Decimal("0"),
        "max_positive_usd": max(positive) if positive else Decimal("0"),
        "sum_positive_usd": sum(positive, Decimal("0")),
    }


def _write_live_pool_scan_report(
    *,
    elapsed_seconds: Decimal,
    pools: dict,
    registry_summary_rows: dict,
    rate_pairs: int,
    directional_quotes: int,
    failures: list[str],
) -> None:
    report = {
        "ok": not failures,
        "mode": "read_only_no_broadcast",
        "chain_id": CHAIN_ID,
        "elapsed_seconds": elapsed_seconds,
        "block": rpc_layer.BLOCK,
        "pools_loaded": len(pools),
        "protocol_counts": dict(Counter(pool.get("protocol") for pool in pools.values())),
        "rate_pairs": rate_pairs,
        "directional_quotes": directional_quotes,
        "registry_rows": len(pools),
        "registry_execution_summary": registry_summary_rows,
        "liquidity": _liquidity_summary(pools),
        "quality": getattr(rpc_layer, "LAST_POOL_QUALITY_STATS", {}),
        "discovery": {
            "factory": getattr(rpc_layer, "FACTORY_DISCOVERY_STATS", {}),
            "polygon_token_list": getattr(rpc_layer, "POLYGON_TOKEN_LIST_DISCOVERY_STATS", {}),
            "dynamic_pool_registry": getattr(rpc_layer, "DYNAMIC_POOL_REGISTRY_STATS", {}),
            "curve_pool_registry": getattr(rpc_layer, "CURVE_POOL_REGISTRY_STATS", {}),
            "subgraph_pool_intel": getattr(rpc_layer, "SUBGRAPH_POOL_INTEL_STATS", {}),
        },
        "failures": list(failures),
        "updated_at": int(time.time()),
    }
    LIVE_POOL_SCAN_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LIVE_POOL_SCAN_REPORT.write_text(
        json.dumps(_json_ready(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_pipeline_validation_report(report: dict[str, object]) -> None:
    PIPELINE_VALIDATION_REPORT.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_VALIDATION_REPORT.write_text(
        json.dumps(_json_ready(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _check_local_rpc(url: str) -> bool:
    try:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 3}))
        return w3.eth.chain_id == CHAIN_ID
    except Exception:
        return False


def _simulate_call(tx: dict, from_addr: str | None = None) -> tuple[bool, str]:
    call_tx = {
        "to": tx["to"],
        "data": tx["data"],
        "value": tx.get("value", 0),
    }
    if from_addr:
        call_tx["from"] = from_addr
    try:
        result = rpc_layer.w3.eth.call(call_tx, block_identifier="latest")
        return True, result.hex()
    except Exception as exc:
        return False, f"{type(exc).__name__}: {format_revert(exc)}"


def validate(
    rpc_url: str,
    max_opps: int = 3,
    simulate_call: bool = True,
    *,
    stager_max_token_paths: int | None = None,
    stager_max_pre_ranked: int | None = None,
    stager_max_quote_options_per_pair: int | None = None,
) -> int:
    started = time.time()
    failures: list[str] = []
    report: dict[str, object] = {
        "ok": False,
        "chain_id": CHAIN_ID,
        "target_rpc": rpc_url,
        "simulate_call": simulate_call,
        "max_opps": max_opps,
        "payload_execution_eligible": False,
        "exact_call_gate": "NOT_RUN",
        "executor_truth": {
            "inspected": 0,
            "executable": 0,
            "exact_calls": 0,
            "unique_route_signatures": 0,
            "skipped_bad_route_signatures": 0,
            "rejection_classes": {},
            "diagnostics": [],
        },
    }
    stager_max_token_paths = (
        _int_env("OMEGA_VALIDATION_STAGER_MAX_TOKEN_PATHS", 500)
        if stager_max_token_paths is None
        else stager_max_token_paths
    )
    stager_max_pre_ranked = (
        _int_env("OMEGA_VALIDATION_STAGER_MAX_PRE_RANKED", 100)
        if stager_max_pre_ranked is None
        else stager_max_pre_ranked
    )
    stager_max_quote_options_per_pair = (
        _int_env("OMEGA_VALIDATION_STAGER_MAX_QUOTE_OPTIONS", 2)
        if stager_max_quote_options_per_pair is None
        else stager_max_quote_options_per_pair
    )

    print("Omega V5 pipeline validation")
    print(f"target_rpc={rpc_url}")
    print(
        "env_live_intent="
        f"{EXEC_MODE == 'live' and LIVE_FLAG == '1' and CONFIRM_FLAG == REQUIRED_CONFIRM} "
        f"exec_mode={EXEC_MODE} live_flag={LIVE_FLAG} "
        f"confirm_ok={CONFIRM_FLAG == REQUIRED_CONFIRM} "
        f"effective_runtime_mode={runtime_mode()}"
    )
    settings = runtime_settings()
    effective_execution_cap = 1 if settings.get("canary_mode") else settings.get("execute_top")
    report["runtime"] = {
        "effective_runtime_mode": runtime_mode(),
        "settings": settings,
        "effective_execution_cap": effective_execution_cap,
        "canary_mode": bool(settings.get("canary_mode")),
    }
    print(
        f"runtime_execution_settings=execute_top:{settings.get('execute_top')} "
        f"canary_mode:{settings.get('canary_mode')} "
        f"effective_execution_cap:{effective_execution_cap}"
    )

    redis_ok, redis_detail = redis_status()
    print(f"redis_cache_ok={redis_ok} detail={redis_detail}")

    if not rpc_layer.connect(http_urls=[rpc_url], wss_url="", prefer_wss=False):
        print("rpc_connect=False")
        report["failures"] = ["rpc_connect"]
        _write_pipeline_validation_report(report)
        return 1
    print(f"rpc_connect=True chain_id={rpc_layer.w3.eth.chain_id} block={rpc_layer.BLOCK}")
    if rpc_layer.w3.eth.chain_id != CHAIN_ID:
        failures.append("rpc_chain_id_mismatch")

    code_ok, code_detail = executor_code_status()
    print(f"executor_code_ok={code_ok} detail={code_detail}")
    if not code_ok:
        failures.append("executor_code")
    owner = executor_owner()
    sim_from = simulation_from_address()
    print(f"executor_owner={owner or 'UNKNOWN'}")
    print(f"simulation_from={sim_from or 'NOT SET'}")

    print("loading_pools=True")
    pools = rpc_layer.load_all_live_pools(DEEP_POOL_REGISTRY)
    discovery_stats = getattr(rpc_layer, "FACTORY_DISCOVERY_STATS", {})
    if discovery_stats:
        print(f"factory_discovery_stats={discovery_stats}")
    print(f"pools_loaded={len(pools)} base_registry_size={len(DEEP_POOL_REGISTRY)} active_registry_size={len(pools)}")
    pool_quality_stats = getattr(rpc_layer, "LAST_POOL_QUALITY_STATS", {})
    if pool_quality_stats:
        print(f"pool_quality_stats={pool_quality_stats}")
    if len(pools) < 10:
        failures.append("pool_load_low")
    v2_usdc_variants: dict[str, int] = {}
    v2_mismatches = 0
    for pool in pools.values():
        if pool.get("protocol") != "UniswapV2":
            continue
        meta = pool.get("_meta", {})
        variant = str(meta.get("usdc_variant") or "none")
        v2_usdc_variants[variant] = v2_usdc_variants.get(variant, 0) + 1
        if meta.get("composition_mismatch"):
            v2_mismatches += 1
    print(f"v2_usdc_variants={v2_usdc_variants} v2_composition_mismatches={v2_mismatches}")

    prices = refresh_token_prices(force=True)
    print(f"prices_loaded={len(prices)}")
    if not prices:
        failures.append("prices")

    registry_rows = build_verified_pool_registry(pools)
    reg_summary = registry_summary(registry_rows)
    hot_rows = sum(1 for row in registry_rows if row.lane == "hot")
    warm_rows = sum(1 for row in registry_rows if row.lane == "warm")
    discovery_rows = sum(1 for row in registry_rows if row.lane == "discovery")
    print(
        f"verified_pool_registry_rows={len(registry_rows)} "
        f"hot={hot_rows} warm={warm_rows} discovery={discovery_rows} "
        f"execution_statuses={reg_summary}"
    )

    # --- PERFORMANCE BOTTLENECK IDENTIFIED & RESOLVED ---
    # The original implementation performed rate calculation, spread detection, and
    # opportunity scoring in multiple, sequential Python functions. This was the
    # primary bottleneck, preventing the system from reaching its maximum potential.
    #
    # The following change offloads the entire discovery-to-ranking pipeline to the
    # compiled Rust engine, aligning the code with the documented architecture where
    # "RustMath" is the authority. This single, powerful call replaces the previous
    # slow, iterative Python logic.

    print("Invoking RustMath engine for unified discovery and ranking...")
    arb_engine = ArbitrageGraphEngine(pools, prices)  # Engine now initialized with all necessary context

    # --- Optimal Sizing Configuration ---
    # Instead of a fixed principal, we pass sizing parameters to the Rust engine,
    # allowing it to find the optimal trade size for each route up to the
    # configured maximums. This is critical for maximizing profitability.
    sizing_params = {
        "min_principal_usd": str(MIN_FLASH_PRINCIPAL_USD),
        "max_principal_usd": str(MAX_FLASH_PRINCIPAL_USD),
        "tvl_fractions": [str(f) for f in FLASH_ROUTE_TVL_FRACTIONS],
        "max_impact_bps": int(MAX_ROUTE_IMPACT * 10000),
    }

    # This single, high-performance call replaces the previous Python-based:
    # compute_all_pool_rates, detect_*_spreads, bellman_ford, pre_rank_routes, and score_* functions.
    ranked, discovery_report = arb_engine.find_and_rank_opportunities(
        sizing_params=sizing_params,
        flash_source=FlashSource.BALANCER,
        stager_max_token_paths=stager_max_token_paths,
        stager_max_pre_ranked=stager_max_pre_ranked,
        stager_max_quote_options_per_pair=stager_max_quote_options_per_pair,
    )

    # The Rust engine returns a comprehensive report for logging and visibility.
    rate_pairs = discovery_report.get("rate_pairs", 0)
    directional_quotes = discovery_report.get("directional_quotes", 0)
    if directional_quotes <= 0:
        failures.append("rates")

    _write_live_pool_scan_report(
        elapsed_seconds=Decimal(str(round(time.time() - started, 3))),
        pools=pools,
        registry_summary_rows=reg_summary,
        rate_pairs=rate_pairs,
        directional_quotes=directional_quotes,
        failures=failures,
    )
    print(f"live_pool_scan_report={LIVE_POOL_SCAN_REPORT}")

    print(
        f"cycles_detected={discovery_report.get('cycles_detected', 0)} "
        f"bellman_cycles={discovery_report.get('bellman_cycles', 0)} "
        f"stager_blueprints={discovery_report.get('stager_blueprints', 0)} "
        f"stager_raw_positive={discovery_report.get('stager_raw_positive', 0)}"
    )
    print(
        "gate_passed_by_hop="
        f"2:{discovery_report.get('gate_passed_by_hop', {}).get('2', 0)} "
        f"3:{discovery_report.get('gate_passed_by_hop', {}).get('3', 0)} "
        f"4:{discovery_report.get('gate_passed_by_hop', {}).get('4', 0)}"
    )
    print(f"gate_passed_opportunities={len(ranked)}")

    from .gas_oracle import base_fee_gwei as _base_fee_gwei

    base_fee_gwei, base_fee_source = _base_fee_gwei()
    print(f"gas_fee_source={base_fee_source} base_fee_gwei={base_fee_gwei}")
    truth_ranked: list[LiveOpportunity] = []
    truth_results = []
    if simulate_call and ranked:
        truth_ranked, truth_results = final_truth_rank(
            ranked,
            pools,
            base_fee_gwei=base_fee_gwei,
            max_candidates=max(1, max_opps),
        )
        summary = truth_summary(truth_results)
        diagnostics = [
            {
                "opp_id": row.original.opp_id,
                "path": list(row.original.path),
                "protocols": list(row.original.protocol_seq),
                "route_signature": row.route_signature,
                "exact_calls": row.exact_calls,
                "tested_sizes_usd": list(row.tested_sizes_usd),
                "executable": row.executable,
                "rejection_class": row.rejection_class or ("executable" if row.executable else "rejected"),
                "detail": row.exact_call_detail[:500],
            }
            for row in truth_results[:20]
        ]
        report["executor_truth"] = {
            **summary,
            "diagnostics": diagnostics,
        }
        print(
            f"executor_truth_inspected={summary['inspected']} "
            f"executor_truth_executable={summary['executable']} "
            f"executor_truth_exact_calls={summary['exact_calls']} "
            f"executor_truth_unique_signatures={summary['unique_route_signatures']} "
            f"executor_truth_skipped_bad_signatures={summary['skipped_bad_route_signatures']} "
            f"executor_truth_rejections={summary['rejection_classes']}"
        )
        if truth_results:
            first = truth_results[0]
            print(
                f"executor_truth_first opp_id={first.original.opp_id} "
                f"executable={first.executable} "
                f"route_signature={first.route_signature or 'NONE'} "
                f"exact_calls={first.exact_calls} "
                f"tested_sizes_usd={first.tested_sizes_usd} "
                f"selected_size_usd={first.selected_size_usd or 'NONE'} "
                f"rejection_class={first.rejection_class or 'NONE'} "
                f"detail={first.exact_call_detail[:240]}"
            )
            for idx, row in enumerate(truth_results[:5], 1):
                print(
                    f"executor_truth_diag_{idx}=opp_id:{row.original.opp_id} "
                    f"path:{'->'.join(row.original.path)} "
                    f"protocols:{'->'.join(row.original.protocol_seq)} "
                    f"signature:{row.route_signature or 'NONE'} "
                    f"exact_calls:{row.exact_calls} "
                    f"tested_sizes:{row.tested_sizes_usd} "
                    f"class:{row.rejection_class or ('executable' if row.executable else 'rejected')} "
                    f"detail:{row.exact_call_detail[:180]}"
                )

    if ENABLE_LIQUIDATION_PIPELINE:
        try:
            liquidation_packets = AaveLiquidationScanner(pools).scan()
            liq_promoted = [packet for packet in liquidation_packets if packet.nextStage == "LIQUIDATION"]
            liq_rejected = len(liquidation_packets) - len(liq_promoted)
            print(
                f"liquidation_packets={len(liquidation_packets)} "
                f"liquidation_ready={len(liq_promoted)} rejected={liq_rejected}"
            )
            if liquidation_packets:
                top_liq = liquidation_packets[0]
                print(
                    f"top_liquidation nextStage={top_liq.nextStage} borrower={top_liq.borrower} "
                    f"debt={top_liq.debt_symbol} collateral={top_liq.collateral_symbol} "
                    f"net_usd={top_liq.expected_net_profit_usd} "
                    f"selected_source={top_liq.selected_capital_source.source_name if top_liq.selected_capital_source else 'NONE'} "
                    f"rejects={top_liq.reject_reasons}"
                )
            if liq_promoted:
                try:
                    liq_tx = build_liquidation_tx(
                        liq_promoted[0],
                        pools,
                        nonce=0,
                        base_fee_gwei=Decimal("50"),
                    )
                    selector = str(liq_tx["data"])[:10]
                    print(
                        f"liquidation_payload_ok=True to={liq_tx['to']} "
                        f"selector={selector} gas={liq_tx['gas']}"
                    )
                    liq_env = build_liquidation_payload_envelope(liq_promoted[0], liq_tx)
                    print(
                        f"liquidation_envelope_id={liq_env.envelope_id} "
                        f"domain={liq_env.domain} selector={liq_env.selector}"
                    )
                    if simulate_call:
                        ok, detail = simulate_liquidation(liq_tx, from_addr=sim_from or None)
                        print(f"liquidation_eth_call_ok={ok} detail={detail}")
                except Exception as exc:
                    print(f"liquidation_payload_ok=False detail={type(exc).__name__}: {exc}")
        except Exception as exc:
            print(f"liquidation_pipeline=BLOCKED detail={type(exc).__name__}: {exc}")

    tx = None
    payload_ranked = truth_ranked if simulate_call else ranked
    selected_payload_op = None
    payload_rejections: list[str] = []
    if payload_ranked:
        for shown, candidate in enumerate(ranked[:max(1, max_opps)], 1):
            raw_spread = candidate.metadata.get("raw_spread_engine", {})
            normalized = raw_spread.get("normalized_quote", {})
            accounting = normalized.get("accounting", {}) if isinstance(normalized, dict) else {}
            accounting_sections = sorted(accounting.keys()) if isinstance(accounting, dict) else []
            delta = accounting.get("delta", {}) if isinstance(accounting, dict) else {}
            print(
                f"ranked_candidate_{shown}=opp_id:{candidate.opp_id} "
                f"net_usd:{candidate.profitability.net_profit_usd} "
                f"path:{'->'.join(candidate.path)} "
                f"strategy:{candidate.strategy} "
                f"spread_usd_per_unit:{raw_spread.get('sized_spread_usd_per_unit', 'n/a')} "
                f"units:{raw_spread.get('mid_token_units_purchased', 'n/a')} "
                f"raw_delta_usd:{raw_spread.get('raw_delta_usd', 'n/a')} "
                f"normalized_base:{normalized.get('baseToken', 'n/a')} "
                f"normalized_mid:{normalized.get('midToken', 'n/a')} "
                f"sell_in_equals_buy_out:{normalized.get('sellAmountInEqualsBuyAmountOut', 'n/a')} "
                f"gross_profit_raw:{normalized.get('grossProfitRaw', 'n/a')} "
                f"net_profit_raw:{normalized.get('netProfitRaw', 'n/a')} "
                f"raw_inequality_pass:{normalized.get('executableInequalityPass', 'n/a')} "
                f"accounting_schema:{accounting.get('schema', 'n/a') if isinstance(accounting, dict) else 'n/a'} "
                f"accounting_sections:{accounting_sections} "
                f"raw_delta_formula:{delta.get('raw_delta_formula_1', 'n/a') if isinstance(delta, dict) else 'n/a'}"
            )
        for candidate in payload_ranked[:max(1, max_opps)]:
            try:
                candidate_tx = build_tx_payload(
                    candidate,
                    nonce=0,
                    base_fee_gwei=Decimal("50"),
                    allow_pool_target_fallback=False,
                )
                selected_payload_op = candidate
                tx = candidate_tx
                break
            except AdapterSemanticError as exc:
                detail = f"{candidate.opp_id}:{exc}"
                payload_rejections.append(detail)
                print(f"payload_candidate_rejected opp_id={candidate.opp_id} reason=adapter_semantics detail={str(exc)[:240]}")
            except Exception as exc:
                detail = f"{candidate.opp_id}:{type(exc).__name__}: {exc}"
                payload_rejections.append(detail)
                print(f"payload_candidate_rejected opp_id={candidate.opp_id} reason={type(exc).__name__} detail={str(exc)[:240]}")

        op = selected_payload_op
        if op is None:
            print(
                "payload_source=none reason=no route-kind-configured payload candidate "
                f"rejections={payload_rejections[:5]}"
            )
            print("payload_execution_eligible=False exact_call_gate=NO_ROUTE_KIND_CONFIGURED_ROUTE")
        else:
            print(f"payload_source=ranked opp_id={op.opp_id}")
            metadata = op.schema_metadata()
            labels = [step["label"] for step in metadata["pricing_steps"]]
            print(
                f"schema_version={metadata['schema_version']} "
                f"pricing_steps={labels} "
                f"flash_principal_usd={metadata['flash_principal_usd']}"
            )
            if op.strategy in {"CROSS_POOL_TWO_LEG", "PEGGED_STABLE_TWO_LEG"}:
                required = {"BUY_LEG1_PRICE", "SELL_LEG2_PRICE"}
                if not required.issubset(set(labels)):
                    failures.append("mandatory_price_steps")
            adapter_resolution = resolve_capital_source_adapter(op.flash_source)
            print(
                f"capital_source_adapter_ok={adapter_resolution.ok} "
                f"capital_source_executable={adapter_resolution.executable} "
                f"flash_source_id={adapter_resolution.flash_source_id} "
                f"target_mode={adapter_resolution.target_mode} "
                f"configured_source_envs={list(configured_adapters().keys())} "
                f"detail={adapter_resolution.detail}"
            )

            calldata = tx["data"]
            selector_ok = isinstance(calldata, str) and calldata.startswith(EXECUTE_FLASH_ARB_SELECTOR)
            print(
                f"payload_ok={selector_ok} to={tx['to']} selector={str(calldata)[:10]} "
                f"calldata_bytes={(len(calldata) - 2) // 2}"
            )
            c1_env = build_c1_payload_envelope(op, tx)
            c2_env = build_c2_payload_envelope(
                parent_envelope_id=c1_env.envelope_id,
                c2_id=f"C2-{op.opp_id}",
                decision="PENDING_REAL_C1_RECEIPT",
                target=tx["to"],
            )
            print(
                f"c1_envelope_id={c1_env.envelope_id} "
                f"domain={c1_env.domain} selector={c1_env.selector}"
            )
            print(
                f"c2_envelope_id={c2_env.envelope_id} "
                f"domain={c2_env.domain} parent={c2_env.parent_envelope_id} "
                f"selector={c2_env.selector}"
            )
            if not selector_ok:
                failures.append("payload_selector")
    else:
        if ranked and simulate_call:
            print("payload_source=none reason=no exact-call executable opportunity after final truth gate")
            print("payload_execution_eligible=False exact_call_gate=NO_EXECUTOR_TRUTH_ROUTE")
            report["payload_execution_eligible"] = False
            report["exact_call_gate"] = "NO_EXECUTOR_TRUTH_ROUTE"
        else:
            print("payload_source=none reason=no live opportunity passed final net-profit gate")
            report["payload_execution_eligible"] = False
            report["exact_call_gate"] = "NO_LIVE_PROFIT_GATE_ROUTE"

    if tx and simulate_call:
        ok, detail = _simulate_call(tx, from_addr=sim_from or None)
        print(f"eth_call_ok={ok} detail={detail[:240]}")
        print(
            "payload_execution_eligible="
            f"{ok} exact_call_gate={'PASS' if ok else 'REJECTED_PRE_BROADCAST'}"
        )
        report["payload_execution_eligible"] = bool(ok)
        report["exact_call_gate"] = "PASS" if ok else "REJECTED_PRE_BROADCAST"
        report["payload_eth_call_detail"] = detail[:500]

    guards = execution_guard_status()
    print(f"execution_armed={execution_armed()} guards={guards}")
    report["execution_armed"] = execution_armed()
    report["guards"] = guards
    if execution_armed():
        failures.append("unexpected_live_armed")

    if failures:
        print(f"pipeline_validation=FAIL failures={failures}")
        report["ok"] = False
        report["failures"] = failures
        report["elapsed_seconds"] = Decimal(str(round(time.time() - started, 3)))
        _write_pipeline_validation_report(report)
        return 1

    print("pipeline_validation=PASS")
    report["ok"] = True
    report["failures"] = []
    report["elapsed_seconds"] = Decimal(str(round(time.time() - started, 3)))
    _write_pipeline_validation_report(report)
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Omega V5 pipeline without broadcasting")
    parser.add_argument("--rpc-url", default="", help="RPC URL to validate against")
    parser.add_argument("--use-fork", action="store_true", help="Prefer FORK_SIM_RPC_URL")
    parser.add_argument("--no-eth-call", action="store_true", help="Skip eth_call payload simulation")
    parser.add_argument("--max-opps", type=int, default=50, help="Ranked opportunities to exact-call truth test")
    parser.add_argument("--stager-max-token-paths", type=int, default=None, help="Validation-only token path budget")
    parser.add_argument("--stager-max-pre-ranked", type=int, default=None, help="Validation-only pre-ranked route budget")
    parser.add_argument("--stager-max-quote-options", type=int, default=None, help="Validation-only quote options per pair")
    args = parser.parse_args(list(argv) if argv is not None else None)

    rpc_url = args.rpc_url
    if not rpc_url and args.use_fork and _check_local_rpc(FORK_SIM_RPC_URL):
        rpc_url = FORK_SIM_RPC_URL
    if not rpc_url:
        rpc_url, _ = resolve_fork_upstream(validate=True)
    if not rpc_url:
        print("pipeline_validation=FAIL failures=['no_rpc_url']")
        return 1
    return validate(
        rpc_url,
        max_opps=max(1, args.max_opps),
        simulate_call=not args.no_eth_call,
        stager_max_token_paths=args.stager_max_token_paths,
        stager_max_pre_ranked=args.stager_max_pre_ranked,
        stager_max_quote_options_per_pair=args.stager_max_quote_options,
    )


if __name__ == "__main__":
    raise SystemExit(main())
