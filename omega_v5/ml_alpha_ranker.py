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
    """
    Predicts the best size bin. This version uses a more robust heuristic
    based on a target fraction of the route's minimum TVL.
    """
    if not DYNAMIC_SIZE_OPT_BINS_USD:
        return MIN_FLASH_PRINCIPAL_USD

    # Use the minimum TVL from the sizing metadata if available, as it's the
    # most direct measure of the route's capacity.
    liquidity = float(op.metadata.get("sizing", {}).get("min_pool_tvl_usd", 0.0))
    if liquidity == 0.0:
        # Fallback for preliminary opportunities before full sizing.
        liquidity = float(op.metadata.get("min_pool_liquidity_usd", 0.0))

    if liquidity <= 0:
        return MIN_FLASH_PRINCIPAL_USD

    # Heuristic: The optimal trade size is often a small fraction of the
    # bottleneck liquidity. We target a fraction (e.g., 5%) and find the
    # closest available size bin from our configured ladder. This is more
    # robust than a simple linear formula with magic numbers.
    target_principal = Decimal(liquidity) * Decimal("0.05")

    # Find the bin that is closest to our target principal.
    closest_bin = min(DYNAMIC_SIZE_OPT_BINS_USD, key=lambda b: abs(b - target_principal))

    print(
        f"   ML Alpha: Size bin heuristic selected bin ${closest_bin:,.0f} "
        f"(target: ${target_principal:,.0f}) based on liquidity ${liquidity:,.0f}."
    )

    return closest_bin

def rerank_with_vqc(opportunities: list[LiveOpportunity]) -> list[LiveOpportunity]:
    """
    Re-ranks opportunities based on their expected value, calculated as:
    Expected Value = P(success) * net_profit_usd

    This prioritizes trades that have the best combination of profitability and
    likelihood of successful on-chain execution, as predicted by the VQC model.
    """
    if not _load_model():
        print("   ML Alpha: VQC model not found or failed to load. Skipping re-ranking.")
        return opportunities

    print(f"   ML Alpha: Re-ranking {len(opportunities)} candidates with VQC model...")
    scored_ops = []
    for op in opportunities:
        # Get the model's prediction for the probability of successful execution.
        prob = predict_surplus_probability(op)
        if prob < 0:
            # If the model is not ready or fails, fall back to ranking by raw profit.
            score = float(op.profitability.net_profit_usd)
        else:
            # The score is the expected value: probability of success times the net profit.
            score = prob * float(op.profitability.net_profit_usd)
        scored_ops.append((score, op))

    # Sort opportunities by the calculated score in descending order.
    scored_ops.sort(key=lambda x: x[0], reverse=True)
    return [op for _, op in scored_ops]
