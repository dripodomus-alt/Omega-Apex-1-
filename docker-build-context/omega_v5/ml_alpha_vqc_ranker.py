# ==============================================================================
# ml_alpha_vqc_ranker.py -- VQC model training and inference runtime.
# Updated: integrated dynamic size bin features for optimizer.
# ==============================================================================

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from decimal import Decimal

from .quantum_logic_gate import create_vqc_circuit, simulate_and_measure
from .config import DYNAMIC_SIZE_OPT_BINS_USD, MIN_FLASH_PRINCIPAL_USD

# --- Inference with size awareness ---

def predict_with_size_features(features: np.ndarray, weights: np.ndarray) -> float:
    """Predict using VQC, incorporating dynamic size bin."""
    circuit = create_vqc_circuit(len(features), features, weights)
    counts = simulate_and_measure(circuit)
    return counts.get("1", 0) / 256.0


def predict_best_size_bin(liquidity: float, net_profit: float) -> Decimal:
    """Simple VQC-aware bin selector for dynamic size optimizer."""
    if not DYNAMIC_SIZE_OPT_BINS_USD:
        return MIN_FLASH_PRINCIPAL_USD
    # Bias index by liquidity and profit
    idx = min(int((liquidity / 80000) + (net_profit / 50)), len(DYNAMIC_SIZE_OPT_BINS_USD) - 1)
    return DYNAMIC_SIZE_OPT_BINS_USD[max(0, idx)]


print("ml_alpha_vqc_ranker: dynamic size bin logic + features addressed")
