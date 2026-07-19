#!/usr/bin/env python3
# ==============================================================================
# ml_alpha.py -- fail-closed ML alpha integration contract.
#
# These models are designed to improve route selection and execution timing, but
# an absent or unproven model never changes execution behavior. Each model must
# publish a local model_card.json with validation metrics before it can be used.
# ==============================================================================

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.environ.get("OMEGA_ML_MODEL_DIR", str(ROOT / "models")))
TRAINING_SUMMARY_PATH = ROOT / "out" / "ml" / "receipt_training_summary.json"
ML_ALPHA_ENABLED = os.environ.get("OMEGA_ML_ALPHA_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
MIN_CONFIDENCE = float(os.environ.get("OMEGA_ML_MIN_CONFIDENCE", "0.70") or "0.70")


@dataclass(frozen=True)
class MlModelSpec:
    model_id: str
    purpose: str
    decision_point: str
    required_card: str
    required_metrics: tuple[str, ...]
    fail_closed_behavior: str


MODEL_SPECS: tuple[MlModelSpec, ...] = (
    MlModelSpec(
        model_id="route_surplus_ranker",
        purpose="Re-rank exact-call candidates by expected realized net surplus after fees, gas, slippage, and revert probability.",
        decision_point="after theoretical profitability gate, before executor truth budget allocation",
        required_card="models/route_surplus_ranker/model_card.json",
        required_metrics=("precision_at_5", "calibration_error", "out_of_sample_net_usd"),
        fail_closed_behavior="do not alter ranking; use deterministic net_profit_usd ordering",
    ),
    MlModelSpec(
        model_id="slippage_depth_sizer",
        purpose="Predict optimal flash principal from pool depth, CLMM state, recent volatility, and gas to reduce AdapterSlippageOrProfit rejects.",
        decision_point="before expanded executor-truth size ladder construction",
        required_card="models/slippage_depth_sizer/model_card.json",
        required_metrics=("size_hit_rate", "max_drawdown_usd", "quote_error_bps"),
        fail_closed_behavior="use deterministic TVL fraction and configured size ladder",
    ),
    MlModelSpec(
        model_id="gas_mev_timing_policy",
        purpose="Choose canary timing, priority fee bounds, and private/public relay eligibility from gas station, mempool, and receipt history.",
        decision_point="after exact-call pass, before live C1 broadcast",
        required_card="models/gas_mev_timing_policy/model_card.json",
        required_metrics=("inclusion_success_rate", "cost_error_usd", "revert_avoidance_rate"),
        fail_closed_behavior="use configured gas oracle, exact-call gate, and canary cap",
    ),
)


def _read_model_card(spec: MlModelSpec) -> dict[str, Any]:
    path = ROOT / spec.required_card
    if not path.exists():
        return {"present": False, "path": str(path)}
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
        return {"present": True, "path": str(path), "card": card}
    except Exception as exc:
        return {"present": True, "path": str(path), "error": f"{type(exc).__name__}: {exc}"}


def _model_ready(spec: MlModelSpec, card_row: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not ML_ALPHA_ENABLED:
        issues.append("OMEGA_ML_ALPHA_ENABLED=false")
    if not card_row.get("present"):
        issues.append("model_card_missing")
        return False, issues
    card = card_row.get("card")
    if not isinstance(card, dict):
        issues.append(str(card_row.get("error") or "invalid_model_card"))
        return False, issues
    if card.get("model_id") != spec.model_id:
        issues.append("model_id_mismatch")
    if str(card.get("chain_id")) not in {"137", "polygon", "Polygon"}:
        issues.append("chain_id_not_polygon_137")
    if card.get("execution_authority") is True:
        issues.append("ml_model_must_not_have_execution_authority")
    metrics = card.get("metrics", {})
    if not isinstance(metrics, dict):
        issues.append("metrics_missing")
    else:
        for metric in spec.required_metrics:
            if metric not in metrics:
                issues.append(f"metric_missing:{metric}")
    try:
        confidence = float(card.get("confidence", 0))
    except Exception:
        confidence = 0.0
    if confidence < MIN_CONFIDENCE:
        issues.append(f"confidence_below_min:{confidence}<{MIN_CONFIDENCE}")
    return not issues, issues


def ml_alpha_status() -> dict[str, Any]:
    models: list[dict[str, Any]] = []
    ready_count = 0
    for spec in MODEL_SPECS:
        card_row = _read_model_card(spec)
        ready, issues = _model_ready(spec, card_row)
        if ready:
            ready_count += 1
        models.append(
            {
                "model_id": spec.model_id,
                "purpose": spec.purpose,
                "decision_point": spec.decision_point,
                "required_card": spec.required_card,
                "required_metrics": list(spec.required_metrics),
                "ready": ready,
                "issues": issues,
                "fail_closed_behavior": spec.fail_closed_behavior,
                "card_present": bool(card_row.get("present")),
            }
        )
    return {
        "enabled": ML_ALPHA_ENABLED,
        "model_dir": str(MODEL_DIR),
        "min_confidence": MIN_CONFIDENCE,
        "training_summary": _training_summary(),
        "ready_count": ready_count,
        "required_count": len(MODEL_SPECS),
        "execution_authority": False,
        "can_affect_live_execution": ML_ALPHA_ENABLED and ready_count == len(MODEL_SPECS),
        "models": models,
    }


def _training_summary() -> dict[str, Any]:
    if not TRAINING_SUMMARY_PATH.exists():
        return {
            "status": "MISSING",
            "rows": 0,
            "dataset_path": str(ROOT / "out" / "ml" / "receipt_training_dataset.csv"),
        }
    try:
        data = json.loads(TRAINING_SUMMARY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"status": "INVALID", "rows": 0}
    except Exception as exc:
        return {"status": "INVALID", "rows": 0, "error": f"{type(exc).__name__}: {exc}"}


def ml_alpha_plan() -> list[dict[str, str]]:
    return [
        {
            "step": "1",
            "model": "route_surplus_ranker",
            "action": "Train on route features, exact-call outcomes, realized receipts, gas costs, and quote deltas; deploy only when precision@5 and calibration beat deterministic ranking.",
        },
        {
            "step": "2",
            "model": "slippage_depth_sizer",
            "action": "Train on pool depth, TVL fraction, CLMM liquidity, tick movement, and final eth_call results; use it to propose size ladder centers, not to bypass exact-call.",
        },
        {
            "step": "3",
            "model": "gas_mev_timing_policy",
            "action": "Train on gas station, receipt inclusion, revert, and relay outcomes; use it to choose canary timing and fee bounds after exact-call passes.",
        },
    ]
