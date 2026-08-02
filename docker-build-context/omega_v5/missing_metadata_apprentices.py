#!/usr/bin/env python3
# ==============================================================================
# missing_metadata_apprentices.py -- multi-runner missing metadata research.
#
# Apprentice runners can search web/API/AI sources and propose candidate
# metadata. They never mutate runtime registries. A deterministic validation
# layer marks candidates promotable only after source and on-chain checks pass.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from web3 import Web3

from . import rpc_layer
from .asset_state_research import LATEST_RESEARCH_REPORT
from .paths import output_path


LATEST_REPORT = output_path("missing_metadata_apprentices_latest.json")
HISTORY_REPORT = output_path("missing_metadata_apprentices_history.jsonl")
APPRENTICE_RUNNERS = (
    "venue_protocol_apprentice",
    "public_market_apprentice",
    "web_search_apprentice",
    "openai_metadata_apprentice",
    "gemini_metadata_apprentice",
    "grok_metadata_apprentice",
)

_ERC20_METADATA_ABI = [
    {"name": "symbol", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "string"}]},
    {"name": "name", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "string"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
]


@dataclass(frozen=True)
class MetadataCase:
    symbol: str
    address: str
    blockers: tuple[str, ...]
    attempted_sources: tuple[str, ...]
    pool_ids: tuple[str, ...]


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def _load_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        return json.loads(open(path, "r", encoding="utf-8").read())
    except Exception:
        return {}


def missing_cases_from_asset_report(report: dict[str, Any], *, include_price_missing: bool = True) -> list[MetadataCase]:
    cases: list[MetadataCase] = []
    for row in report.get("assets", []) or []:
        if not isinstance(row, dict):
            continue
        resolution = row.get("metadata_resolution") if isinstance(row.get("metadata_resolution"), dict) else {}
        blockers = list(resolution.get("blockers") or [])
        execution_blockers = list(row.get("execution_blockers") or [])
        if include_price_missing and "price_unavailable" in execution_blockers:
            blockers.append("price_unavailable_requires_external_research")
        if not blockers:
            continue
        cases.append(MetadataCase(
            symbol=str(row.get("symbol") or ""),
            address=str(row.get("address") or ""),
            blockers=tuple(dict.fromkeys(str(item) for item in blockers)),
            attempted_sources=tuple(str(item) for item in resolution.get("attempted_sources") or []),
            pool_ids=tuple(str(item) for item in row.get("pool_ids") or []),
        ))
    return [case for case in cases if case.symbol]


def _search_query(case: MetadataCase) -> str:
    address_part = f" {case.address}" if case.address else ""
    return f"Polygon token metadata {case.symbol}{address_part} decimals contract address Coingecko DexScreener CoinMarketCap"


def _venue_protocol_apprentice(case: MetadataCase) -> dict[str, Any]:
    """
    Return protocol interaction recipes for retrieving missing metadata/state.

    This runner is intentionally deterministic: it records the functions that
    should be used by discovery/readers for the venue family rather than asking
    an LLM to infer execution metadata.
    """
    pool_text = " ".join(case.pool_ids).upper()
    recipes: list[dict[str, Any]] = [{
        "family": "ERC20",
        "functions": ["symbol()", "name()", "decimals()", "totalSupply()"],
        "purpose": "token metadata baseline for any asset address",
    }]
    if "V3" in pool_text or "ALGEBRA" in pool_text:
        recipes.append({
            "family": "UniswapV3/Algebra CLMM",
            "functions": ["token0()", "token1()", "fee() or globalState().lastFee", "tickSpacing()", "slot0() or globalState()", "liquidity()"],
            "purpose": "pool token identity, fee tier, tick/price, and active liquidity",
        })
    if "QS" in pool_text or "UNISWAPV2" in pool_text or "V2" in pool_text:
        recipes.append({
            "family": "UniswapV2 compatible",
            "functions": ["token0()", "token1()", "getReserves()", "factory().getPair(tokenA,tokenB)"],
            "purpose": "pool token identity, reserves, and canonical pair validation",
        })
    if "CURVE" in pool_text:
        recipes.append({
            "family": "Curve registry/pool",
            "functions": ["coins(i)", "balances(i)", "decimals() or registry decimals", "A()", "fee()"],
            "purpose": "coin metadata, pool balances, amplification, and fee state",
        })
    if "BALANCER" in pool_text or "BAL" in pool_text:
        recipes.append({
            "family": "Balancer Vault",
            "functions": ["getPool(poolId)", "getPoolTokens(poolId)", "weightedPool.getNormalizedWeights()", "weightedPool.getSwapFeePercentage()"],
            "purpose": "vault pool token identities, balances, weights, and swap fee",
        })
    return {
        "runner": "venue_protocol_apprentice",
        "status": "ok",
        "case_symbol": case.symbol,
        "pool_ids": list(case.pool_ids),
        "recipes": recipes,
        "policy": "read-only protocol function plan; no registry mutation",
    }


def _public_market_apprentice(case: MetadataCase) -> dict[str, Any]:
    """Use public market metadata endpoints that require no configured AI key."""
    rows: list[dict[str, Any]] = []
    if case.address and Web3.is_address(case.address):
        try:
            resp = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{case.address}", timeout=12)
            resp.raise_for_status()
            pairs = [row for row in resp.json().get("pairs", []) or [] if row.get("chainId") == "polygon"]
            if pairs:
                best = max(pairs, key=lambda row: float(row.get("liquidity", {}).get("usd") or 0))
                base = best.get("baseToken", {}) if isinstance(best.get("baseToken"), dict) else {}
                rows.append({
                    "source": "dexscreener_token",
                    "pairAddress": best.get("pairAddress", ""),
                    "url": best.get("url", ""),
                    "priceUsd": best.get("priceUsd", ""),
                    "liquidity": best.get("liquidity", {}),
                    "baseToken": base,
                })
        except Exception as exc:
            rows.append({"source": "dexscreener_token", "status": "error", "detail": f"{type(exc).__name__}: {exc}"})
    else:
        rows.append({"source": "dexscreener_token", "status": "skipped", "detail": "case address missing or invalid"})

    return {
        "runner": "public_market_apprentice",
        "status": "ok" if rows else "skipped",
        "results": rows,
        "candidate": _candidate_from_public_market(case, rows),
    }


def _candidate_from_public_market(case: MetadataCase, rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        base = row.get("baseToken") if isinstance(row.get("baseToken"), dict) else {}
        address = str(base.get("address") or case.address or "")
        symbol = str(base.get("symbol") or case.symbol or "")
        if address and symbol:
            return {
                "symbol": symbol,
                "name": str(base.get("name") or ""),
                "address": address,
                "decimals": None,
                "price_sources": [row.get("url", "")],
                "evidence_urls": [row.get("url", "")],
                "confidence": 0.55,
                "notes": "Public market source can support identity/price discovery, but decimals still require deterministic validation.",
            }
    return {}


def _web_search(case: MetadataCase, *, limit: int = 5) -> dict[str, Any]:
    provider = os.environ.get("METADATA_SEARCH_PROVIDER", "").strip().lower()
    query = _search_query(case)
    try:
        if provider == "brave" and os.environ.get("BRAVE_SEARCH_API_KEY"):
            resp = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": os.environ["BRAVE_SEARCH_API_KEY"]},
                params={"q": query, "count": limit},
                timeout=15,
            )
            resp.raise_for_status()
            rows = resp.json().get("web", {}).get("results", []) or []
            return {"runner": "web_search_apprentice", "provider": "brave", "status": "ok", "query": query, "results": rows[:limit]}
        if provider == "bing" and os.environ.get("BING_SEARCH_API_KEY"):
            resp = requests.get(
                "https://api.bing.microsoft.com/v7.0/search",
                headers={"Ocp-Apim-Subscription-Key": os.environ["BING_SEARCH_API_KEY"]},
                params={"q": query, "count": limit},
                timeout=15,
            )
            resp.raise_for_status()
            rows = resp.json().get("webPages", {}).get("value", []) or []
            return {"runner": "web_search_apprentice", "provider": "bing", "status": "ok", "query": query, "results": rows[:limit]}
        if provider == "serpapi" and os.environ.get("SERPAPI_API_KEY"):
            resp = requests.get(
                "https://serpapi.com/search.json",
                params={"engine": "google", "q": query, "api_key": os.environ["SERPAPI_API_KEY"], "num": limit},
                timeout=20,
            )
            resp.raise_for_status()
            rows = resp.json().get("organic_results", []) or []
            return {"runner": "web_search_apprentice", "provider": "serpapi", "status": "ok", "query": query, "results": rows[:limit]}
        if provider == "tavily" and os.environ.get("TAVILY_API_KEY"):
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": os.environ["TAVILY_API_KEY"], "query": query, "max_results": limit},
                timeout=20,
            )
            resp.raise_for_status()
            rows = resp.json().get("results", []) or []
            return {"runner": "web_search_apprentice", "provider": "tavily", "status": "ok", "query": query, "results": rows[:limit]}
        return {
            "runner": "web_search_apprentice",
            "provider": provider or "disabled",
            "status": "skipped",
            "query": query,
            "reason": "set METADATA_SEARCH_PROVIDER plus provider API key",
        }
    except Exception as exc:
        return {"runner": "web_search_apprentice", "provider": provider, "status": "error", "query": query, "error": f"{type(exc).__name__}: {exc}"}


def _extract_text_from_openai_response(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text") if isinstance(content, dict) else None
            if text:
                chunks.append(str(text))
    return "\n".join(chunks)


def _candidate_prompt(case: MetadataCase, search_result: dict[str, Any]) -> str:
    return (
        "Return strict JSON only. Research Polygon token metadata and propose at most one candidate.\n"
        "Schema: {\"symbol\":\"\",\"name\":\"\",\"address\":\"\",\"decimals\":null,"
        "\"price_sources\":[],\"evidence_urls\":[],\"confidence\":0.0,\"notes\":\"\"}\n"
        "Do not invent metadata. If evidence is insufficient, return confidence 0 and empty fields.\n"
        f"Case: symbol={case.symbol} address={case.address} blockers={list(case.blockers)} "
        f"attempted_sources={list(case.attempted_sources)} pool_ids={list(case.pool_ids)}\n"
        f"Search evidence: {json.dumps(search_result, ensure_ascii=True)[:12000]}"
    )


def _parse_json_candidate(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(stripped[start:end + 1])
                return payload if isinstance(payload, dict) else {}
            except Exception:
                return {}
    return {}


def _openai_apprentice(case: MetadataCase, search_result: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_METADATA_MODEL", "gpt-5-mini")
    if not api_key:
        return {"runner": "openai_metadata_apprentice", "status": "skipped", "reason": "OPENAI_API_KEY not set"}
    try:
        resp = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": _candidate_prompt(case, search_result)},
            timeout=60,
        )
        resp.raise_for_status()
        text = _extract_text_from_openai_response(resp.json())
        return {"runner": "openai_metadata_apprentice", "status": "ok", "model": model, "candidate": _parse_json_candidate(text), "raw_text": text[:2000]}
    except Exception as exc:
        return {"runner": "openai_metadata_apprentice", "status": "error", "model": model, "error": f"{type(exc).__name__}: {exc}"}


def _gemini_apprentice(case: MetadataCase, search_result: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    model = os.environ.get("GEMINI_METADATA_MODEL", "gemini-3-pro")
    if not api_key:
        return {"runner": "gemini_metadata_apprentice", "status": "skipped", "reason": "GEMINI_API_KEY/GOOGLE_API_KEY not set"}
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": _candidate_prompt(case, search_result)}]}]},
            timeout=60,
        )
        resp.raise_for_status()
        parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", []) or []
        text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        return {"runner": "gemini_metadata_apprentice", "status": "ok", "model": model, "candidate": _parse_json_candidate(text), "raw_text": text[:2000]}
    except Exception as exc:
        return {"runner": "gemini_metadata_apprentice", "status": "error", "model": model, "error": f"{type(exc).__name__}: {exc}"}


def _grok_apprentice(case: MetadataCase, search_result: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")
    model = os.environ.get("XAI_METADATA_MODEL", "grok-4.5")
    if not api_key:
        return {"runner": "grok_metadata_apprentice", "status": "skipped", "reason": "XAI_API_KEY/GROK_API_KEY not set"}
    try:
        resp = requests.post(
            "https://api.x.ai/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "input": _candidate_prompt(case, search_result)},
            timeout=60,
        )
        resp.raise_for_status()
        text = _extract_text_from_openai_response(resp.json())
        return {"runner": "grok_metadata_apprentice", "status": "ok", "model": model, "candidate": _parse_json_candidate(text), "raw_text": text[:2000]}
    except Exception as exc:
        return {"runner": "grok_metadata_apprentice", "status": "error", "model": model, "error": f"{type(exc).__name__}: {exc}"}


def _validate_candidate(candidate: dict[str, Any], case: MetadataCase) -> dict[str, Any]:
    address = str(candidate.get("address") or case.address or "")
    symbol = str(candidate.get("symbol") or case.symbol or "")
    decimals = candidate.get("decimals")
    evidence_urls = candidate.get("evidence_urls") or candidate.get("price_sources") or []
    if not isinstance(evidence_urls, list):
        evidence_urls = []
    failures: list[str] = []
    if not Web3.is_address(address):
        failures.append("candidate_address_invalid")
    try:
        decimals_int = int(decimals)
        if decimals_int < 0 or decimals_int > 36:
            failures.append("candidate_decimals_out_of_range")
    except Exception:
        decimals_int = None
        failures.append("candidate_decimals_missing")
    if not evidence_urls:
        failures.append("candidate_evidence_urls_missing")

    onchain: dict[str, Any] = {"status": "skipped", "reason": "rpc_not_connected"}
    if Web3.is_address(address) and rpc_layer.w3 is not None and rpc_layer.RPC_LIVE:
        try:
            checksum = Web3.to_checksum_address(address)
            code = rpc_layer.w3.eth.get_code(checksum)
            if not code:
                failures.append("candidate_address_has_no_code")
                onchain = {"status": "fail", "reason": "address_has_no_code"}
            else:
                contract = rpc_layer.w3.eth.contract(address=checksum, abi=_ERC20_METADATA_ABI)
                onchain_symbol = contract.functions.symbol().call()
                onchain_name = contract.functions.name().call()
                onchain_decimals = int(contract.functions.decimals().call())
                onchain = {
                    "status": "pass",
                    "symbol": onchain_symbol,
                    "name": onchain_name,
                    "decimals": onchain_decimals,
                }
                if decimals_int is not None and onchain_decimals != decimals_int:
                    failures.append("candidate_decimals_mismatch_onchain")
        except Exception as exc:
            failures.append("candidate_onchain_read_failed")
            onchain = {"status": "fail", "reason": f"{type(exc).__name__}: {exc}"[:300]}

    existing_symbol = rpc_layer.ADDRESS_TO_SYMBOL.get(address.lower()) if Web3.is_address(address) else None
    if existing_symbol and existing_symbol != case.symbol:
        failures.append(f"candidate_address_conflicts_existing_symbol:{existing_symbol}")

    return {
        "status": "promotable" if not failures else "rejected",
        "symbol": symbol,
        "address": address,
        "decimals": decimals_int,
        "evidence_urls": evidence_urls,
        "failures": failures,
        "onchain": onchain,
        "promotion_policy": "proposal_only_discovery_review_required",
    }


def run_apprentices_for_case(case: MetadataCase, *, search_limit: int = 5) -> dict[str, Any]:
    search_result = _web_search(case, limit=search_limit)
    runner_rows = [
        _venue_protocol_apprentice(case),
        _public_market_apprentice(case),
        search_result,
        _openai_apprentice(case, search_result),
        _gemini_apprentice(case, search_result),
        _grok_apprentice(case, search_result),
    ]
    validations: list[dict[str, Any]] = []
    for row in runner_rows:
        candidate = row.get("candidate") if isinstance(row, dict) else None
        if isinstance(candidate, dict) and candidate:
            validation_row = {
                "runner": row.get("runner"),
                "validation": _validate_candidate(candidate, case),
                "candidate": candidate,
            }
            _write_proposal_if_complete(case, validation_row)
            validations.append(validation_row)
    return {
        "case": case.__dict__,
        "runners": runner_rows,
        "validations": validations,
        "promotable_candidates": [row for row in validations if row["validation"]["status"] == "promotable"],
    }


def assign_apprentice_runner(case: MetadataCase, *, index: int = 0) -> str:
    blockers = set(case.blockers)
    if case.pool_ids and any("metadata_" in blocker for blocker in blockers):
        return "venue_protocol_apprentice"
    if case.address and "price_unavailable_requires_external_research" in blockers:
        return "public_market_apprentice"
    return APPRENTICE_RUNNERS[index % len(APPRENTICE_RUNNERS)]


def run_assigned_apprentice_for_case(
    case: MetadataCase,
    *,
    runner_name: str,
    search_limit: int = 5,
) -> dict[str, Any]:
    search_result = {"runner": "web_search_apprentice", "status": "not_required"}
    if runner_name == "venue_protocol_apprentice":
        row = _venue_protocol_apprentice(case)
    elif runner_name == "public_market_apprentice":
        row = _public_market_apprentice(case)
    elif runner_name == "web_search_apprentice":
        row = _web_search(case, limit=search_limit)
    elif runner_name == "openai_metadata_apprentice":
        search_result = _web_search(case, limit=search_limit)
        row = _openai_apprentice(case, search_result)
    elif runner_name == "gemini_metadata_apprentice":
        search_result = _web_search(case, limit=search_limit)
        row = _gemini_apprentice(case, search_result)
    elif runner_name == "grok_metadata_apprentice":
        search_result = _web_search(case, limit=search_limit)
        row = _grok_apprentice(case, search_result)
    else:
        row = {
            "runner": runner_name,
            "status": "error",
            "error": f"unknown runner; expected one of {APPRENTICE_RUNNERS}",
        }

    validations: list[dict[str, Any]] = []
    candidate = row.get("candidate") if isinstance(row, dict) else None
    if isinstance(candidate, dict) and candidate:
        validation_row = {
            "runner": row.get("runner"),
            "validation": _validate_candidate(candidate, case),
            "candidate": candidate,
        }
        _write_proposal_if_complete(case, validation_row)
        validations.append(validation_row)
    return {
        "case": case.__dict__,
        "assigned_runner": runner_name,
        "search_context": search_result,
        "runners": [row],
        "validations": validations,
        "promotable_candidates": [item for item in validations if item["validation"]["status"] == "promotable"],
    }


def _write_proposal_if_complete(case: MetadataCase, validation_row: dict[str, Any]) -> None:
    try:
        from .apprentice_metadata_registry import write_missing_metadata_proposal

        write_missing_metadata_proposal(
            case=case.__dict__,
            runner=str(validation_row.get("runner") or ""),
            candidate=validation_row.get("candidate") if isinstance(validation_row.get("candidate"), dict) else {},
            validation=validation_row.get("validation") if isinstance(validation_row.get("validation"), dict) else {},
        )
    except Exception:
        return


def run_missing_metadata_apprentices(
    *,
    input_report: str = "",
    limit: int = 25,
    include_price_missing: bool = True,
    search_limit: int = 5,
    connect_rpc: bool = True,
) -> dict[str, Any]:
    if connect_rpc and rpc_layer.w3 is None:
        rpc_layer.connect(http_urls=[os.environ.get("POLYGON_RPC_URL") or os.environ.get("RPC_URL") or ""], wss_url="", prefer_wss=False)
    source_path = input_report or str(LATEST_RESEARCH_REPORT)
    asset_report = _load_json(source_path)
    cases = missing_cases_from_asset_report(asset_report, include_price_missing=include_price_missing)
    selected = cases[:max(0, limit)]
    started = time.time()
    results = [run_apprentices_for_case(case, search_limit=search_limit) for case in selected]
    payload = {
        "ok": True,
        "mode": "read_only_missing_metadata_apprentices",
        "source_report": source_path,
        "elapsed_seconds": round(time.time() - started, 3),
        "case_count": len(cases),
        "processed": len(results),
        "promotable_count": sum(len(row["promotable_candidates"]) for row in results),
        "provider_status": {
            "web_search": os.environ.get("METADATA_SEARCH_PROVIDER", "disabled"),
            "openai": "enabled" if os.environ.get("OPENAI_API_KEY") else "missing_key",
            "gemini": "enabled" if (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")) else "missing_key",
            "grok": "enabled" if (os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")) else "missing_key",
        },
        "policy": {
            "do_not_stop_on_first_missing_metadata": True,
            "ai_output_can_promote_directly": False,
            "required_final_gate": "deterministic_validation_apprentice",
            "apprentices_write_registry_proposals": True,
            "registry_mutation_requires_discovery_review": True,
        },
        "results": results,
    }
    write_report(payload)
    return payload


def write_report(payload: dict[str, Any]) -> None:
    LATEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LATEST_REPORT.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True), encoding="utf-8")
    with HISTORY_REPORT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_json_ready(payload), sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run missing metadata apprentice researchers.")
    parser.add_argument("--input-report", default="")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--search-limit", type=int, default=5)
    parser.add_argument("--exclude-price-missing", action="store_true")
    parser.add_argument("--no-rpc", action="store_true")
    args = parser.parse_args()
    report = run_missing_metadata_apprentices(
        input_report=args.input_report,
        limit=max(0, args.limit),
        include_price_missing=not args.exclude_price_missing,
        search_limit=max(1, args.search_limit),
        connect_rpc=not args.no_rpc,
    )
    print(
        "missing_metadata_apprentices=OK "
        f"cases={report['case_count']} processed={report['processed']} "
        f"promotable={report['promotable_count']} path={LATEST_REPORT}",
        flush=True,
    )


if __name__ == "__main__":
    main()
