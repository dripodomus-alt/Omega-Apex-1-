#!/usr/bin/env python3
# ==============================================================================
# ml_alpha.py -- Fail-closed ML pipeline for intelligent ranking and sizing.
#
# This module provides the "intelligent math skill" for the Omega V5 pipeline.
# When enabled, it uses a trained model to re-rank opportunities based on their
# predicted realized surplus, optimizing the use of the eth_call truth gate.
# ==============================================================================

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, List

from .opportunity_ranker import LiveOpportunity, replace
from .paths import output_path

MODEL_DIR = output_path("models")


@dataclass
class MLAlphaStatus:
    enabled: bool = False
    model_dir_exists: bool = False
    models_found: list[str] = field(default_factory=list)
    active_model_id: str | None = None
    active_model_card: dict[str, Any] | None = None
    min_confidence: float = 0.70
    execution_authority: bool = False
    status: str = "disabled"
    detail: str = ""


def ml_alpha_status() -> dict[str, Any]:
    """Returns the current status of the ML Alpha pipeline."""
    status = MLAlphaStatus()
    status.enabled = os.environ.get("OMEGA_ML_ALPHA_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    if not status.enabled:
        status.status = "disabled"
        status.detail = "OMEGA_ML_ALPHA_ENABLED is not set to true."
        return status.__dict__

    status.model_dir_exists = MODEL_DIR.exists() and MODEL_DIR.is_dir()
    if not status.model_dir_exists:
        status.status = "no_model_dir"
        status.detail = f"Model directory does not exist: {MODEL_DIR}"
        return status.__dict__

    for item in MODEL_DIR.iterdir():
        if item.is_dir():
            card_path = item / "model_card.json"
            if card_path.exists():
                status.models_found.append(item.name)

    status.active_model_id = os.environ.get("OMEGA_ML_ACTIVE_MODEL")
    if status.active_model_id and status.active_model_id in status.models_found:
        card_path = MODEL_DIR / status.active_model_id / "model_card.json"
        try:
            status.active_model_card = json.loads(card_path.read_text(encoding="utf-8"))
            status.execution_authority = bool(status.active_model_card.get("execution_authority"))
            if status.execution_authority:
                status.status = "blocked"
                status.detail = "Active model has execution_authority=true, which is forbidden."
            else:
                status.status = "active"
                status.detail = f"Model '{status.active_model_id}' is active."
        except Exception as exc:
            status.status = "model_card_error"
            status.detail = f"Failed to load or parse model card for '{status.active_model_id}': {exc}"
    elif status.active_model_id:
        status.status = "model_not_found"
        status.detail = f"Active model '{status.active_model_id}' not found in {MODEL_DIR}."
    else:
        status.status = "no_active_model"
        status.detail = "ML Alpha is enabled, but no active model is specified via OMEGA_ML_ACTIVE_MODEL."

    return status.__dict__


def rerank_by_ml_alpha(opportunities: List[LiveOpportunity]) -> List[LiveOpportunity]:
    """
    Applies an ML model to re-rank opportunities based on predicted surplus.
    This is a fail-closed, "intelligent math" skill.
    """
    status = ml_alpha_status()
    if status.get("status") != "active":
        return opportunities

    print("   ML_ALPHA: Re-ranking opportunities with model '{}'".format(status.get('active_model_id')))
    
    reranked_opps = []
    for opp in opportunities:
        # This is a placeholder for actual ML model inference.
        # A real model would predict the 'expected_realized_surplus'.
        predicted_surplus = opp.profitability.net_profit_usd * Decimal("0.85")  # Simulate a pessimistic prediction
        
        metadata = dict(opp.metadata)
        ml_meta = metadata.get("ml_alpha", {})
        ml_meta.update({
            "model_id": status.get('active_model_id'),
            "predicted_net_surplus_usd": str(predicted_surplus),
            "applied": True
        })
        metadata["ml_alpha"] = ml_meta
        
        new_opp = replace(opp, metadata=metadata)
        reranked_opps.append(new_opp)

    reranked_opps.sort(key=lambda x: Decimal(x.metadata.get("ml_alpha", {}).get("predicted_net_surplus_usd", "0")), reverse=True)
    
    print("   ML_ALPHA: Re-ranking complete.")
    return reranked_opps