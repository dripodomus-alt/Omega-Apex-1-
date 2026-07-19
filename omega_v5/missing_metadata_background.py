#!/usr/bin/env python3
# ==============================================================================
# missing_metadata_background.py -- non-blocking metadata research worker.
#
# This process communicates with discovery through artifacts and optional Redis
# streams/hashes only. It never imports or calls the execution cycle.
# ==============================================================================

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from .asset_state_research import LATEST_RESEARCH_REPORT
from .missing_metadata_apprentices import (
    LATEST_REPORT as APPRENTICE_REPORT,
    MetadataCase,
    assign_apprentice_runner,
    missing_cases_from_asset_report,
    run_assigned_apprentice_for_case,
    write_report,
)
from .paths import output_path
from .redis_cache import hgetall_json, key as redis_key, xadd


LATEST_BACKGROUND_REPORT = output_path("missing_metadata_background_latest.json")
HISTORY_BACKGROUND_REPORT = output_path("missing_metadata_background_history.jsonl")


def _load_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        return json.loads(open(path, "r", encoding="utf-8").read())
    except Exception:
        return {}


def _queued_cases_from_redis() -> list[MetadataCase]:
    rows = hgetall_json(redis_key("missing_metadata", "cases"))
    cases: list[MetadataCase] = []
    for row in rows.values():
        if not isinstance(row, dict):
            continue
        cases.append(MetadataCase(
            symbol=str(row.get("symbol") or ""),
            address=str(row.get("address") or ""),
            blockers=tuple(str(item) for item in row.get("blockers") or []),
            attempted_sources=tuple(str(item) for item in row.get("attempted_sources") or []),
            pool_ids=tuple(str(item) for item in row.get("pool_ids") or []),
        ))
    return [case for case in cases if case.symbol]


def collect_missing_metadata_cases(*, include_price_missing: bool = True) -> list[MetadataCase]:
    asset_report = _load_json(LATEST_RESEARCH_REPORT)
    cases = missing_cases_from_asset_report(asset_report, include_price_missing=include_price_missing)
    queued = _queued_cases_from_redis()
    by_key: dict[tuple[str, str], MetadataCase] = {}
    for case in cases + queued:
        by_key[(case.symbol, case.address)] = case
    return list(by_key.values())


def run_background_cycle(
    *,
    limit: int = 25,
    search_limit: int = 5,
    include_price_missing: bool = True,
    cursor: int = 0,
) -> dict[str, Any]:
    started = time.time()
    cases = collect_missing_metadata_cases(include_price_missing=include_price_missing)
    if not cases:
        payload = {
            "ok": True,
            "mode": "background_missing_metadata_research",
            "loop_state": "idle_no_missing_metadata_cases",
            "source": str(LATEST_RESEARCH_REPORT),
            "case_count": 0,
            "processed": 0,
            "next_cursor": 0,
            "results": [],
            "policy": _policy(),
        }
        _write_background_report(payload)
        return payload

    start = max(0, cursor) % len(cases)
    ordered = cases[start:] + cases[:start]
    selected = ordered[:max(0, limit)]
    results = []
    for offset, case in enumerate(selected):
        runner = assign_apprentice_runner(case, index=start + offset)
        result = run_assigned_apprentice_for_case(case, runner_name=runner, search_limit=search_limit)
        results.append(result)
        xadd(redis_key("missing_metadata", "research_results"), result, maxlen=10000)

    apprentice_payload = {
        "ok": True,
        "mode": "read_only_missing_metadata_apprentices_assigned_background",
        "source_report": str(LATEST_RESEARCH_REPORT),
        "elapsed_seconds": round(time.time() - started, 3),
        "case_count": len(cases),
        "processed": len(results),
        "promotable_count": sum(len(row["promotable_candidates"]) for row in results),
        "policy": _policy(),
        "results": results,
    }
    write_report(apprentice_payload)
    payload = {
        **apprentice_payload,
        "mode": "background_missing_metadata_research",
        "loop_state": "active_missing_metadata_research",
        "next_cursor": (start + len(selected)) % len(cases),
        "apprentice_artifact": str(APPRENTICE_REPORT),
        "background_artifact": str(LATEST_BACKGROUND_REPORT),
        "main_pipeline_interaction": "artifact_and_optional_redis_only_no_execution_loop_import",
        "continuous_cycle": {
            "active_while_cases_exist": True,
            "case_count": len(cases),
            "selected_this_cycle": len(selected),
            "next_cursor": (start + len(selected)) % len(cases),
        },
    }
    _write_background_report(payload)
    return payload


def next_cycle_sleep_seconds(
    payload: dict[str, Any],
    *,
    active_interval_seconds: int,
    idle_interval_seconds: int,
    elapsed_seconds: float = 0.0,
) -> int:
    """
    Keep the apprentice loop hot while unresolved metadata exists.

    When there are no cases, the worker idles and polls at the slower interval.
    """
    case_count = int(payload.get("case_count") or 0)
    processed = int(payload.get("processed") or 0)
    target = active_interval_seconds if case_count > 0 and processed > 0 else idle_interval_seconds
    return max(1, int(target - elapsed_seconds))


def _policy() -> dict[str, Any]:
    return {
        "runs_in_background": True,
        "autonomous_constant_cycle_while_missing_metadata_exists": True,
        "main_pipeline_blocking": False,
        "communicates_with": ["asset_state_research artifact", "optional Redis missing_metadata cases/results"],
        "assigned_runner_count": 6,
        "assigned_runners": [
            "venue_protocol_apprentice",
            "public_market_apprentice",
            "web_search_apprentice",
            "openai_metadata_apprentice",
            "gemini_metadata_apprentice",
            "grok_metadata_apprentice",
        ],
        "ai_output_can_promote_directly": False,
        "final_gate": "deterministic candidate validation",
        "apprentices_write_registry_proposals": True,
        "registry_mutation_requires_discovery_review": True,
    }


def _write_background_report(payload: dict[str, Any]) -> None:
    LATEST_BACKGROUND_REPORT.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_BACKGROUND_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LATEST_BACKGROUND_REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    with HISTORY_BACKGROUND_REPORT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run non-blocking missing metadata background apprentices.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=int(os.environ.get("MISSING_METADATA_BACKGROUND_INTERVAL_SECONDS", "300") or "300"))
    parser.add_argument("--active-interval-seconds", type=int, default=int(os.environ.get("MISSING_METADATA_BACKGROUND_ACTIVE_INTERVAL_SECONDS", "15") or "15"))
    parser.add_argument("--idle-interval-seconds", type=int, default=int(os.environ.get("MISSING_METADATA_BACKGROUND_IDLE_INTERVAL_SECONDS", os.environ.get("MISSING_METADATA_BACKGROUND_INTERVAL_SECONDS", "300")) or "300"))
    parser.add_argument("--limit", type=int, default=int(os.environ.get("MISSING_METADATA_BACKGROUND_LIMIT", "25") or "25"))
    parser.add_argument("--search-limit", type=int, default=int(os.environ.get("MISSING_METADATA_BACKGROUND_SEARCH_LIMIT", "5") or "5"))
    parser.add_argument("--exclude-price-missing", action="store_true")
    args = parser.parse_args()

    cursor = 0
    while True:
        started = time.time()
        try:
            payload = run_background_cycle(
                limit=max(0, args.limit),
                search_limit=max(1, args.search_limit),
                include_price_missing=not args.exclude_price_missing,
                cursor=cursor,
            )
            cursor = int(payload.get("next_cursor") or 0)
            print(
                "missing_metadata_background=OK "
                f"cases={payload.get('case_count')} processed={payload.get('processed')} "
                f"promotable={payload.get('promotable_count')} "
                f"next_cursor={payload.get('next_cursor')} path={LATEST_BACKGROUND_REPORT}",
                flush=True,
            )
        except Exception as exc:
            payload = {
                "ok": False,
                "mode": "background_missing_metadata_research",
                "error": f"{type(exc).__name__}: {exc}",
                "policy": _policy(),
            }
            _write_background_report(payload)
            print(f"missing_metadata_background=ERROR type={type(exc).__name__} detail={exc}", flush=True)

        if args.once:
            return
        elapsed = time.time() - started
        active_interval = max(1, int(args.active_interval_seconds))
        idle_interval = max(1, int(args.idle_interval_seconds or args.interval_seconds))
        sleep_seconds = next_cycle_sleep_seconds(
            payload,
            active_interval_seconds=active_interval,
            idle_interval_seconds=idle_interval,
            elapsed_seconds=elapsed,
        )
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
