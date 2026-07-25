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
from typing import Any, Callable, List

import joblib
import numpy as np
import pennylane as qml

from .opportunity_ranker import LiveOpportunity, replace
from .paths import output_path

MODEL_DIR = output_path("models")
_model_cache = {}


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


# This part is duplicated from train_vqc_ranker.py.
# For production, this should be refactored into a shared model-definition module.
def _get_vqc_circuit(num_qubits: int) -> Callable:
    """Creates and returns a Pennylane VQC circuit."""
    dev = qml.device("default.qubit", wires=num_qubits)

    @qml.qnode(dev)
    def circuit(weights, x):
        qml.AngleEmbedding(x, wires=range(num_qubits))
        qml.StronglyEntanglingLayers(weights, wires=range(num_qubits))
        return qml.expval(qml.PauliZ(0))

    return circuit


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


def _load_model_artifacts(status: dict) -> bool:
    """Loads the VQC model, weights, and scaler into a cache."""
    model_id = status.get("active_model_id")
    if not model_id or model_id in _model_cache:
        return model_id in _model_cache

    model_path = MODEL_DIR / model_id
    card = status.get("active_model_card", {})
    files = card.get("files", {})
    scaler_path = model_path / files.get("scaler")
    weights_path = model_path / files.get("weights")

    if not scaler_path.exists() or not weights_path.exists():
        print(f"   ML_ALPHA: ERROR - Model files for '{model_id}' not found.")
        return False

    try:
        scaler = joblib.load(scaler_path)
        weights = np.load(weights_path)
        num_features = len(card.get("features", []))
        circuit = _get_vqc_circuit(num_features)

        _model_cache[model_id] = {
            "scaler": scaler,
            "weights": weights,
            "circuit": circuit,
            "features": card.get("features", []),
        }
        print(f"   ML_ALPHA: Successfully loaded model '{model_id}'.")
        return True
    except Exception as e:
        print(f"   ML_ALPHA: ERROR - Failed to load model artifacts for '{model_id}': {e}")
        _model_cache.pop(model_id, None)
        return False


def rerank_by_ml_alpha(opportunities: List[LiveOpportunity]) -> List[LiveOpportunity]:
    """
    Applies an ML model to re-rank opportunities based on predicted surplus.
    This is a fail-closed, "intelligent math" skill.
    """
    status = ml_alpha_status()
    if status.get("status") != "active" or not _load_model_artifacts(status):
        return opportunities

    model_id = status.get("active_model_id")
    model = _model_cache.get(model_id)
    if not model:
        return opportunities

    print(f"   ML_ALPHA: Re-ranking opportunities with model '{model_id}'")

    reranked_opps = []
    for opp in opportunities:
        try:
            # This logic assumes the LiveOpportunity object and engine can provide these features.
            # This part is highly dependent on the data available in the `LiveOpportunity` object.
            principal = float(opp.profitability.flashloan.principal_usd)
            # If TVL is not present, default to 0. This is a pessimistic but truthful signal.
            route_tvl = float(opp.metadata.get("route_tvl_usd", 0))
            slippage_bps = float(opp.metadata.get("slippage_bps", 0))
            gas_cost_usd = float(opp.profitability.gas_cost_usd)
            principal_to_tvl = min(1.0, (principal / route_tvl) if route_tvl > 0 else 1.0)

            feature_vector = [float(opp.gross_rate), principal, slippage_bps, len(opp.path), principal_to_tvl, gas_cost_usd]
            feature_vector_scaled = model["scaler"].transform([feature_vector])

            # The VQC model returns a score from -1 (bad) to 1 (good)
            vqc_score = model["circuit"](model["weights"], feature_vector_scaled[0])
            confidence_factor = (Decimal(vqc_score) + 1) / 2  # Map [-1, 1] to [0, 1]
            predicted_surplus = opp.profitability.net_profit_usd * confidence_factor
        except Exception as e:
            # Fail closed: if feature extraction or prediction fails, use a pessimistic default
            # Log the error for debugging purposes.
            print(f"   ML_ALPHA: ERROR - Feature extraction failed for opp {opp.metadata.get('opp_id', 'N/A')}: {e}")
            vqc_score = -1.0
            predicted_surplus = opp.profitability.net_profit_usd * Decimal("0.1") # Penalize heavily

        metadata = dict(opp.metadata)
        ml_meta = metadata.get("ml_alpha", {})
        ml_meta.update({"model_id": model_id, "vqc_score": float(vqc_score), "predicted_net_surplus_usd": str(predicted_surplus), "applied": True})
        metadata["ml_alpha"] = ml_meta

        new_opp = replace(opp, metadata=metadata)
        reranked_opps.append(new_opp)

    reranked_opps.sort(key=lambda x: Decimal(x.metadata.get("ml_alpha", {}).get("predicted_net_surplus_usd", "0")), reverse=True)

    print("   ML_ALPHA: Re-ranking complete.")
    return reranked_opps