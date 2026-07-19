#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json

import requests
import websockets
from web3 import Web3


async def probe_wss(url: str, timeout: int) -> dict:
    request = {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}
    async with websockets.connect(url, open_timeout=timeout, close_timeout=timeout) as ws:
        await ws.send(json.dumps(request))
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    payload = json.loads(raw)
    return {
        "connected": "result" in payload,
        "chain_id": int(payload["result"], 16) if payload.get("result") else None,
        "raw": payload,
    }


def probe_http(url: str, timeout: int) -> dict:
    web3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": timeout}))
    connected = bool(web3.is_connected())
    chain_id = int(web3.eth.chain_id) if connected else None
    block_number = int(web3.eth.block_number) if connected else None
    return {"connected": connected, "chain_id": chain_id, "block_number": block_number}


def probe_http_raw(url: str, timeout: int) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return {
        "connected": "result" in data,
        "block_number": int(data["result"], 16) if data.get("result") else None,
        "raw": data,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Polygon HTTP/WSS RPC endpoints")
    parser.add_argument("--http", default="https://polygon.drpc.org")
    parser.add_argument("--wss", default="wss://polygon.drpc.org")
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    http = probe_http(args.http, args.timeout)
    raw = probe_http_raw(args.http, args.timeout)
    wss = asyncio.run(probe_wss(args.wss, args.timeout))
    result = {"http_web3": http, "http_raw": raw, "wss": wss}
    print(json.dumps(result, indent=2, sort_keys=True))
    ok = (
        http.get("connected")
        and http.get("chain_id") == 137
        and raw.get("block_number")
        and wss.get("connected")
        and wss.get("chain_id") == 137
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
