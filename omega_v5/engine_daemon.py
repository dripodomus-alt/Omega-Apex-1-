#!/usr/bin/env python3
# ==============================================================================
# engine_daemon.py -- long-running PM2 wrapper around omega_v5.main.
#
# Updated for full pipeline:
# - Lifespan (n+4) alignment across all stages.
# - Dry-run cycles on startup / ticks.
# - Full logging of stage/execute/expire + PNL tracking.
# - PATH consistency enforced.
# ==============================================================================

from __future__ import annotations

import asyncio
import logging
import os
import time
from decimal import Decimal

from .main import run
from .runtime_control import runtime_settings, get_runtime_state
from .pnl_tracker import current_snapshot, record_stage_event, pnl_summary

logger = logging.getLogger("omega.daemon")
logger.setLevel(logging.INFO)

def _bool_env(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


async def _run_forever() -> None:
    rpc_url = os.environ.get("OMEGA_ENGINE_RPC_URL", os.environ.get("POLYGON_RPC_URL", ""))

    while True:
        settings = runtime_settings()
        ticks = int(settings.get("ticks", os.environ.get("OMEGA_ENGINE_TICKS", "1")))
        principal = Decimal(
            str(settings.get("principal_usd", os.environ.get("OMEGA_ENGINE_PRINCIPAL_USD", "50000")))
        )
        execute_top = int(settings.get("execute_top", 5))
        print_top = int(settings.get("print_top_routes", 50))
        canary = bool(settings.get("canary_mode", False))

        try:
            await run(
                rpc_url=rpc_url,
                principal_usd=principal,
                ticks=ticks,
                execute_top=execute_top,
                print_top_routes=print_top,
                canary_mode=canary,
            )
        except Exception as exc:
            logger.exception("engine tick failed: %s", exc)

        # Log current pipeline metrics
        snap = current_snapshot()
        metrics = snap.get("pipeline_metrics", {})
        logger.info(
            f"PIPELINE METRICS: staged={metrics.get('staged_count')} "
            f"executed={metrics.get('executed_count')} "
            f"expired={metrics.get('expired_lifespan_count')} "
            f"submissions={metrics.get('successful_submissions')} "
            f"n+4={metrics.get('n_plus_4_lifespan')}"
        )

        await asyncio.sleep(1)


def main() -> None:
    asyncio.run(_run_forever())


if __name__ == "__main__":
    main()
