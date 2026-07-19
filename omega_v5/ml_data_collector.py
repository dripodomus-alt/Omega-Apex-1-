#!/usr/bin/env python3
# ==============================================================================
# ml_data_collector.py -- ML Alpha training data collection daemon.
#
# Listens to Redis streams for truth-gate results and PnL events to build a
# labeled dataset for training the route_surplus_ranker model.
# ==============================================================================

import json
import os
import logging
import time
from decimal import Decimal

from . import redis_cache
from .config import OMEGA_ML_MODEL_DIR
from .opportunity_ranker import LiveOpportunity
from .transport_lanes import STREAM_EXECUTABLE_ROUTES, STREAM_TRUTH_CANDIDATES

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


DATASET_FILE = os.path.join(OMEGA_ML_MODEL_DIR, "vqc_ranker_dataset.jsonl")


def extract_features(op: LiveOpportunity) -> dict:
    """Extracts features from a LiveOpportunity for model training."""
    try:
        from .rpc_layer import TOKEN_DECIMALS

        base_asset_decimals = TOKEN_DECIMALS.get(op.path[0], 18)
        principal_raw = int(
            op.profitability.flashloan.principal_usd
            * (Decimal(10) ** base_asset_decimals)
            / op.profitability.flashloan.asset_price_usd
        )
    except Exception: # noqa: E722
        principal_raw = 0

    return {
        "opp_id": op.opp_id,
        "signature": op.metadata.get("execution_truth", {}).get("route_signature", ""),
        "hops": len(op.path) - 1,
        "protocols": "-".join(op.protocol_seq),
        "principal_usd": float(op.profitability.flashloan.principal_usd),
        "principal_raw": principal_raw,
        "is_clmm": any(p in {"UniswapV3", "QuickSwapV3", "Algebra"} for p in op.protocol_seq),
        "min_pool_liquidity_usd": float(op.metadata.get("min_pool_liquidity_usd", 0)),
        "route_impact_bps": float(op.metadata.get("route_impact_bps", 0)),
        "theoretical_net_usd": float(op.profitability.net_profit_usd),
    }


def process_stream_entry(entry_id: str, data: dict):
    """Processes a single entry from the Redis streams."""
    try:
        # The truth gate result is the most valuable label.
        # It's published to the 'omega:queue:executable_routes' stream.
        if "original_opportunity" in data and "executable" in data:
            # The opportunity is stored as a JSON string in the stream
            opp_data_str = data["original_opportunity"]
            opp_data = json.loads(opp_data_str)

            op = LiveOpportunity(**opp_data)
            features = extract_features(op)

            # The 'executable' value is also a string from redis
            executable_bool = str(data["executable"]).lower() in ('true', '1')

            label = {
                "executable": executable_bool,
                "realized_net_usd": float(data.get("decoded_profit_usd", 0)),
                "rejection_class": data.get("rejection_class", ""),
            }
            record = {"features": features, "label": label, "source": "truth_gate"}

            with open(DATASET_FILE, "a") as f:
                # Use default=str to handle any Decimals from extract_features
                f.write(json.dumps(record, default=str) + "\n")
    except json.JSONDecodeError as e:
        logging.warning(f"JSON decode error for entry {entry_id}: {e}. Data: {data.get('original_opportunity')}")
    except (TypeError, KeyError) as e:
        logging.error(f"Data structure error processing stream entry {entry_id}: {e}. Data: {data}")
    except Exception as e:
        logging.error(f"Unexpected error processing stream entry {entry_id}: {e}")


def run_collector_daemon():
    """Main loop for the data collection daemon."""
    logging.info("🚀 Starting Omega ML Data Collector Daemon...")
    os.makedirs(OMEGA_ML_MODEL_DIR, exist_ok=True)

    # We listen to both streams, but the truth gate stream has the richest data.
    streams = {
        STREAM_TRUTH_CANDIDATES: "0",
        STREAM_EXECUTABLE_ROUTES: "0",
    }
    logging.info(f"Listening for training data on streams: {list(streams.keys())}")

    while True:
        try:
            results = redis_cache.xread(streams, count=100, block=5000)
            if not results:
                continue

            for stream_name, entries in results:
                for entry_id, data in entries:
                    # Decode from bytes to string
                    decoded_data = {k.decode('utf-8', 'ignore'): v.decode('utf-8', 'ignore') for k, v in data.items()}
                    process_stream_entry(entry_id.decode(), decoded_data)
                    streams[stream_name] = entry_id
        except Exception as e:
            logging.error(f"Daemon loop error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run_collector_daemon()