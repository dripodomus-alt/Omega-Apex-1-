#!/usr/bin/env python3
# ==============================================================================
# cycle_api.py — FastAPI routes for C1×C2 machine-state dashboard
# ==============================================================================
"""Register with: from omega_v5.cycle_api import register_cycle_routes; register_cycle_routes(app)"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from .cycle_logger import cycle_logger

router = APIRouter(tags=["cycles"])


@router.get("/cycles/recent")
def cycles_recent(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    """Dashboard-ready recent opportunity machine states."""
    return {
        "ok": True,
        "count": 0,
        "recent": cycle_logger.list_recent_states(limit=limit),
    }


@router.get("/cycles/{opportunity_id}")
def cycle_detail(opportunity_id: str) -> dict[str, Any]:
    state = cycle_logger.machine_state(opportunity_id)
    if state is None:
        # fall back to persisted recent list
        for row in cycle_logger.list_recent_states(limit=100):
            if row.get("opportunity_id") == opportunity_id:
                state = row
                break
    if state is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    events = cycle_logger.recent_events(limit=200, opportunity_id=opportunity_id)
    return {"ok": True, "state": state, "events": events}


@router.get("/cycles/{opportunity_id}/events")
def cycle_events(
    opportunity_id: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    return {
        "ok": True,
        "opportunity_id": opportunity_id,
        "events": cycle_logger.recent_events(limit=limit, opportunity_id=opportunity_id),
    }


def register_cycle_routes(app: Any) -> None:
    """Attach C1×C2 cycle routes to a FastAPI app."""
    app.include_router(router)
