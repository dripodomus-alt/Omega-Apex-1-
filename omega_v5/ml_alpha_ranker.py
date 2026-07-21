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
        float(op.metadata.get("sizing", {}).get("selected_principal_usd", 0.0)),
        float(op.metadata.get("sizing", {}).get("min_pool_tvl_usd", 0.0)),
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
    """Predicts the best size bin using a heuristic based on liquidity and profit."""
    if not DYNAMIC_SIZE_OPT_BINS_USD:
        return MIN_FLASH_PRINCIPAL_USD

    # This heuristic is a step up from a static default, moving towards a real model.
    # It uses liquidity and theoretical profit to select a more appropriate size bin.
    liquidity = float(op.metadata.get("sizing", {}).get("min_pool_tvl_usd", 0.0))
    if liquidity == 0.0:
        # Fallback if TVL is not available in the preliminary opportunity
        liquidity = float(op.metadata.get("min_pool_liquidity_usd", 0.0))
        
    net_profit = float(op.profitability.net_profit_usd)

    # Bias index by liquidity and profit. These divisors are heuristic.
    # A larger liquidity or higher theoretical profit suggests a larger optimal size.
    # This logic is borrowed from a similar heuristic in the VQC ranker module.
    idx = min(int((liquidity / 80000) + (net_profit / 50)), len(DYNAMIC_SIZE_OPT_BINS_USD) - 1)
    idx = max(0, idx)

    selected_bin = DYNAMIC_SIZE_OPT_BINS_USD[idx]
    
    print(f"   ML Alpha: Size bin heuristic selected bin ${selected_bin:,.0f} (index {idx}) based on liquidity ${liquidity:,.0f} and profit ${net_profit:,.2f}.")
    
    return selected_bin

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
