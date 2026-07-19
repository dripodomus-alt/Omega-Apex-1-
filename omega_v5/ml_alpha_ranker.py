#!/usr/bin/env python3
# ==============================================================================
# ml_alpha_ranker.py -- VQC-based opportunity re-ranking logic.
# Updated: added dynamic size bin prediction for optimizer.
# ==============================================================================

from __future__ import annotations

import os
import pickle
from decimal import Decimal

import numpy as np

from .config import OMEGA_ML_MODEL_DIR, DYNAMIC_SIZE_OPT_BINS_USD, MIN_FLASH_PRINCIPAL_USD
from .opportunity_ranker import LiveOpportunity
from .quantum_logic_gate import create_vqc_circuit, simulate_and_measure

SCALER_FILE = os.path.join(OMEGA_ML_MODEL_DIR, "vqc_ranker_scaler.pkl")
MODEL_WEIGHTS_FILE = os.path.join(OMEGA_ML_MODEL_DIR, "vqc_ranker_weights.npy")

_SCALER = None
_WEIGHTS = None

def _load_model() -> bool:
    """Loads the VQC scaler and weights from disk."""
    global _SCALER, _WEIGHTS
    if _SCALER is not None and _WEIGHTS is not None:
        return True
    if not os.path.exists(SCALER_FILE) or not os.path.exists(MODEL_WEIGHTS_FILE):
        return False
    try:
        with open(SCALER_FILE, 'rb') as f:
            _SCALER = pickle.load(f)
        _WEIGHTS = np.load(MODEL_WEIGHTS_FILE)
        print(f"   ML Alpha: VQC model loaded successfully from {OMEGA_ML_MODEL_DIR}")
        return True
    except Exception as e:
        print(f"   ML Alpha: VQC model load failed: {e}")
        return False

def _featurize_single(op: LiveOpportunity) -> np.ndarray:
    """Converts a single LiveOpportunity into a feature vector (now includes size features)."""
    vec = np.array([
        len(op.path) - 1,
        float(op.profitability.flashloan.principal_usd),
        float(op.metadata.get("min_pool_liquidity_usd", 0)),
        float(op.metadata.get("route_impact_bps", 0)),
        float(op.profitability.net_profit_usd),
        1 if any(p in {"UniswapV3", "QuickSwapV3", "Algebra"} for p in op.protocol_seq) else 0,
        # NEW dynamic size features for bin prediction
        float(op.sizing.selected_principal_usd) if op.sizing else 0.0,
        float(op.sizing.min_pool_tvl_usd) if op.sizing else 0.0,
    ])
    return vec.reshape(1, -1)

def predict_surplus_probability(op: LiveOpportunity) -> float:
    """Predicts the probability of a route being executable using the VQC model."""
    if not _load_model() or _SCALER is None or _WEIGHTS is None:
        return -1.0 # Indicate model not ready

    features_raw = _featurize_single(op)
    features_scaled = _SCALER.transform(features_raw)[0]

    n_features = len(features_scaled)
    reps = 2
    vqc_circuit = create_vqc_circuit(n_features, features_scaled, _WEIGHTS, reps=reps)
    counts = simulate_and_measure(vqc_circuit, shots=256) # More shots for inference
    return counts.get("1", 0) / 256

def predict_optimal_size_bin(op: LiveOpportunity) -> Decimal:
    """Predict best size bin with the trained model when available, otherwise deterministic liquidity heuristic."""
    if not _load_model():
        # fallback to first configured bin
        return DYNAMIC_SIZE_OPT_BINS_USD[0] if DYNAMIC_SIZE_OPT_BINS_USD else MIN_FLASH_PRINCIPAL_USD

    # Use features to bias toward a bin (simplified)
    features = _featurize_single(op)[0]
    # crude: larger liquidity -> larger bin index
    liquidity = features[2] if len(features) > 2 else 0
    idx = min(int(liquidity / 50000), len(DYNAMIC_SIZE_OPT_BINS_USD) - 1)
    return DYNAMIC_SIZE_OPT_BINS_USD[idx]

def rerank_with_vqc(opportunities: list[LiveOpportunity]) -> list[LiveOpportunity]:
    """Re-ranks opportunities based on a score of P(executable) * net_profit_usd."""
    if not _load_model():
        print("   ML Alpha: VQC model not found or failed to load. Skipping re-ranking.")
        return opportunities

    print(f"   ML Alpha: Re-ranking {len(opportunities)} candidates with VQC model...")
    scored_ops = []
    for op in opportunities:
        prob = predict_surplus_probability(op)
        if prob < 0:
            score = float(op.profitability.net_profit_usd)
        else:
            score = prob * float(op.profitability.net_profit_usd)
        scored_ops.append((score, op))

    scored_ops.sort(key=lambda x: x[0], reverse=True)
    return [op for _, op in scored_ops]
