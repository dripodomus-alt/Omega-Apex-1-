#!/usr/bin/env python3
# ==============================================================================
# fork_rpc.py -- resolve a concrete Polygon RPC URL for Foundry/Anvil forks.
#
# DODOEX/web3-rpc-provider returns endpoint metadata, while Anvil requires a
# direct JSON-RPC URL. This module bridges that gap and fails over to configured
# provider/proxy URLs when the DODO service is not running.
# ==============================================================================

from __future__ import annotations

import argparse
from typing import Iterable

from web3 import Web3

from .config import (
    CHAIN_ID,
    DODO_RPC_PROXY_URL,
    FORK_UPSTREAM_RPC_URL,
    HTTP_URL,
    HTTP_URL_2,
)
from .rpc_layer import dodo_provider_endpoints
from .redis_cache import get_json, key as redis_key, set_json


def _candidate_urls() -> list[str]:
    urls: list[str] = []
    urls.extend(dodo_provider_endpoints(CHAIN_ID, warn=False))
    urls.extend([
        DODO_RPC_PROXY_URL,
        FORK_UPSTREAM_RPC_URL,
        HTTP_URL,
        HTTP_URL_2,
        "https://polygon-bor-rpc.publicnode.com",
        "https://polygon-rpc.com",
    ])
    return list(dict.fromkeys(url for url in urls if url))


def _validate_rpc(url: str) -> tuple[bool, str]:
    cache_key = redis_key("rpc_validation", CHAIN_ID, url)
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return bool(cached.get("ok")), str(cached.get("detail", "cached"))

    try:
        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 10}))
        chain_id = w3.eth.chain_id
        block = w3.eth.block_number
    except Exception as exc:
        detail = f"{type(exc).__name__}"
        set_json(cache_key, {"ok": False, "detail": detail}, ttl=10)
        return False, detail
    if chain_id != CHAIN_ID:
        detail = f"wrong_chain_id={chain_id}"
        set_json(cache_key, {"ok": False, "detail": detail}, ttl=10)
        return False, detail
    detail = f"chain_id={chain_id} block={block}"
    set_json(cache_key, {"ok": True, "detail": detail}, ttl=30)
    return True, detail


def resolve_fork_upstream(validate: bool = True) -> tuple[str, str]:
    for url in _candidate_urls():
        if not validate:
            return url, "not_validated"
        ok, detail = _validate_rpc(url)
        if ok:
            return url, detail
    return "", "no_valid_polygon_rpc"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve Polygon fork RPC for Anvil")
    parser.add_argument("--print-url", action="store_true", help="Print only the resolved URL")
    parser.add_argument("--no-validate", action="store_true", help="Skip chain-id/block validation")
    args = parser.parse_args(list(argv) if argv is not None else None)

    url, detail = resolve_fork_upstream(validate=not args.no_validate)
    if not url:
        print(detail)
        return 1
    print(url if args.print_url else f"{url} {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
