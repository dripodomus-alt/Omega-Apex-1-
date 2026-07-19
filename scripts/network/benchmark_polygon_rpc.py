#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from omega_v5.config import (
    BROADCAST_RPC_URL,
    CHAIN_ID,
    EXACT_CALL_RPC_URL,
    HTTP_URL,
    HTTP_URL_2,
    PRIMARY_READ_RPC_URL,
    RPC_ROTATION_HTTP_URLS,
    TELEMETRY_RPC_URL,
)


DEFAULT_ENDPOINTS = [
    "https://polygon.drpc.org",
    "https://tenderly.rpc.polygon.community",
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon.publicnode.com",
    "https://polygon-mainnet.gateway.tatum.io",
    "https://polygon-public.nodies.app",
    "https://1rpc.io/matic",
    "https://rpc-mainnet.matic.quiknode.pro",
    "https://polygon.api.onfinality.io/public",
]


@dataclass(frozen=True)
class EndpointProbe:
    url: str
    sample: int
    ok: bool
    latency_ms: float
    chain_id: int | None
    block: int | None
    error: str = ""


def _is_http(url: str) -> bool:
    return isinstance(url, str) and url.lower().startswith(("http://", "https://")) and "${" not in url


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if _is_http(value.strip())))


def _mask_url(url: str) -> str:
    if "//" not in url:
        return url
    scheme, rest = url.split("//", 1)
    host = rest.split("/", 1)[0]
    return f"{scheme}//{host}/..."


def _rpc_call(session: requests.Session, url: str, method: str, timeout: float) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": []}
    response = session.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(json.dumps(data["error"], sort_keys=True))
    return data.get("result")


def probe_once(url: str, sample: int, timeout: float) -> EndpointProbe:
    started = time.perf_counter()
    try:
        with requests.Session() as session:
            chain_hex = _rpc_call(session, url, "eth_chainId", timeout)
            block_hex = _rpc_call(session, url, "eth_blockNumber", timeout)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        chain_id = int(chain_hex, 16) if chain_hex else None
        block = int(block_hex, 16) if block_hex else None
        ok = chain_id == CHAIN_ID and bool(block)
        return EndpointProbe(url, sample, ok, latency_ms, chain_id, block, "" if ok else "wrong_chain_or_empty_block")
    except Exception as exc:
        return EndpointProbe(
            url=url,
            sample=sample,
            ok=False,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            chain_id=None,
            block=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def summarize(url: str, probes: list[EndpointProbe], freshest_block: int) -> dict[str, Any]:
    ok = [probe for probe in probes if probe.ok]
    errors = [probe.error for probe in probes if probe.error]
    latencies = [probe.latency_ms for probe in ok]
    block = max((probe.block or 0 for probe in ok), default=0)
    block_lag = max(0, freshest_block - block) if ok else None
    median_latency = statistics.median(latencies) if latencies else None
    if not latencies:
        p95_latency = None
    elif len(latencies) < 2:
        p95_latency = max(latencies)
    else:
        p95_latency = statistics.quantiles(latencies, n=20)[18]
    success_rate = len(ok) / len(probes) if probes else 0
    latency_penalty = min(60, int((median_latency or 10000) / 20))
    freshness_penalty = min(40, int(block_lag or 0) * 8)
    score = max(0, int(100 * success_rate) - latency_penalty - freshness_penalty)
    return {
        "url_masked": _mask_url(url),
        "ok_samples": len(ok),
        "total_samples": len(probes),
        "success_rate": round(success_rate, 3),
        "median_latency_ms": round(float(median_latency), 2) if median_latency is not None else None,
        "p95_latency_ms": round(float(p95_latency), 2) if p95_latency is not None else None,
        "chain_id": CHAIN_ID if ok else None,
        "block": block or None,
        "block_lag": block_lag,
        "score": score,
        "last_error": errors[-1] if errors else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark and rank Polygon HTTP RPC endpoints")
    parser.add_argument("--samples", type=int, default=3, help="samples per endpoint")
    parser.add_argument("--timeout", type=float, default=4.0, help="request timeout seconds")
    parser.add_argument("--workers", type=int, default=8, help="parallel endpoint probes")
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.add_argument("--include-env", action="store_true", help="include active env RPCs and broadcast RPC")
    parser.add_argument("--url", action="append", default=[], help="additional endpoint URL; may be repeated")
    args = parser.parse_args()

    endpoints = [*DEFAULT_ENDPOINTS, *RPC_ROTATION_HTTP_URLS, *args.url]
    if args.include_env:
        endpoints.extend([PRIMARY_READ_RPC_URL, EXACT_CALL_RPC_URL, TELEMETRY_RPC_URL, HTTP_URL_2, HTTP_URL, BROADCAST_RPC_URL])
    endpoints = _dedupe(endpoints)

    probes_by_url: dict[str, list[EndpointProbe]] = {url: [] for url in endpoints}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [
            executor.submit(probe_once, url, sample, args.timeout)
            for url in endpoints
            for sample in range(max(1, args.samples))
        ]
        for future in as_completed(futures):
            probe = future.result()
            probes_by_url[probe.url].append(probe)

    freshest_block = max((probe.block or 0 for probes in probes_by_url.values() for probe in probes if probe.ok), default=0)
    rows = [summarize(url, probes, freshest_block) for url, probes in probes_by_url.items()]
    rows.sort(key=lambda row: (row["score"], -(row["median_latency_ms"] or 999999)), reverse=True)

    output = {"chain_id": CHAIN_ID, "freshest_block": freshest_block or None, "ranked_endpoints": rows}
    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print(f"chain_id={CHAIN_ID} freshest_block={freshest_block or 'n/a'} endpoints={len(rows)}")
        print("rank score ok/total median_ms p95_ms block_lag endpoint")
        for idx, row in enumerate(rows, start=1):
            print(
                f"{idx:>4} {row['score']:>5} "
                f"{row['ok_samples']}/{row['total_samples']} "
                f"{str(row['median_latency_ms']):>9} "
                f"{str(row['p95_latency_ms']):>7} "
                f"{str(row['block_lag']):>9} "
                f"{row['url_masked']}"
            )
            if row["score"] == 0 and row["last_error"]:
                print(f"     error={row['last_error'][:180]}")
    return 0 if rows and rows[0]["score"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
