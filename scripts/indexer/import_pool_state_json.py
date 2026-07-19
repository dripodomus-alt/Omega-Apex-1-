#!/usr/bin/env python3
"""
Import normalized pool-state JSON lines into Omega's local indexer SQLite DB.

Expected JSONL row shape:
{
  "pool_address": "0x...",
  "protocol": "UniswapV2",
  "block_number": 123,
  "state": {
    "protocol": "UniswapV2",
    "tokens": ["USDC.e", "WETH"],
    "reserves": ["1000.0", "0.25"],
    "fee": "0.003"
  }
}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omega_v5.indexer_state import init_indexer_db, upsert_pool_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Import normalized pool-state JSONL")
    parser.add_argument("jsonl", help="Path to JSON lines file")
    args = parser.parse_args()
    path = Path(args.jsonl)
    if not path.exists():
        raise SystemExit(f"missing input file: {path}")

    init_indexer_db()
    imported = 0
    rejected = 0
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            upsert_pool_state(
                pool_address=row["pool_address"],
                protocol=row["protocol"],
                state=row["state"],
                block_number=int(row["block_number"]),
            )
            imported += 1
        except Exception as exc:
            rejected += 1
            print(f"reject line={line_no} error={type(exc).__name__}: {exc}", file=sys.stderr)
    print(json.dumps({"imported": imported, "rejected": rejected}, indent=2))
    return 0 if imported or not rejected else 1


if __name__ == "__main__":
    raise SystemExit(main())
