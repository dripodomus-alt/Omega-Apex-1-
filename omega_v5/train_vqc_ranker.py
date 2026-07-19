#!/usr/bin/env python3
# ==============================================================================
# train_vqc_ranker.py -- Train the VQC route surplus ranker model.
# ==============================================================================

import json
import os
import pickle
import numpy as np

# Add project root to path to allow direct script execution
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from omega_v5.config import OMEGA_ML_MODEL_DIR
from sklearn.preprocessing import MinMaxScaler
from scipy.optimize import minimize
from omega_v5.quantum_logic_gate import create_vqc_circuit, simulate_and_measure

DATASET_FILE = os.path.join(OMEGA_ML_MODEL_DIR, "vqc_ranker_dataset.jsonl")
SCALER_FILE = os.path.join(OMEGA_ML_MODEL_DIR, "vqc_ranker_scaler.pkl")
MODEL_WEIGHTS_FILE = os.path.join(OMEGA_ML_MODEL_DIR, "vqc_ranker_weights.npy")


def load_dataset():
    """Loads the collected training data."""
    if not os.path.exists(DATASET_FILE):
        raise FileNotFoundError(f"Dataset not found at {DATASET_FILE}. Run the data collector first.")

    records = []
    with open(DATASET_FILE, "r") as f:
        for line in f:
            records.append(json.loads(line))
    return records


def featurize(records: list[dict], scaler: MinMaxScaler | None = None) -> tuple[np.ndarray, np.ndarray, MinMaxScaler]:
    """
    Converts a list of data records into numpy feature vectors and labels.
    Also handles feature scaling.
    """
    feature_vectors = []
    labels = []

    for record in records:
        features = record["features"]
        # This is a simplified featurization. A real implementation would involve
        # more sophisticated feature engineering, like one-hot encoding for 'protocols'.
        vec = np.array([
            features.get("hops", 0),
            features.get("principal_usd", 0),
            features.get("min_pool_liquidity_usd", 0),
            features.get("route_impact_bps", 0),
            features.get("theoretical_net_usd", 0),
            1 if features.get("is_clmm") else 0,
        ])
        feature_vectors.append(vec)
        labels.append(1 if record["label"]["executable"] else 0)

    X = np.array(feature_vectors)
    y = np.array(labels)

    if scaler is None:
        # Fit a new scaler and transform the data
        scaler = MinMaxScaler(feature_range=(0, np.pi))  # Scale features to [0, pi] for encoding
        X_scaled = scaler.fit_transform(X)
    else:
        # Use the existing scaler to transform new data
        X_scaled = scaler.transform(X)

    return X_scaled, y, scaler


def _vqc_predict_proba(features: np.ndarray, weights: np.ndarray) -> float:
    """Executes the VQC circuit and returns the probability of the '1' state."""
    n_features = len(features)
    reps = 2  # Must match the structure used for weight generation
    vqc_circuit = create_vqc_circuit(n_features, features, weights, reps=reps)
    counts = simulate_and_measure(vqc_circuit, shots=100) # Lower shots for faster training
    return counts.get("1", 0) / 100

def _objective_function(weights: np.ndarray, X: np.ndarray, y: np.ndarray) -> float:
    """Calculates binary cross-entropy loss for the VQC model."""
    loss = 0.0
    for features, label in zip(X, y):
        prediction = _vqc_predict_proba(features, weights)
        # Clip predictions to avoid log(0)
        prediction = np.clip(prediction, 1e-10, 1 - 1e-10)
        if label == 1:
            loss -= np.log(prediction)
        else:
            loss -= np.log(1 - prediction)
    return loss / len(y)


def train_model(records):
    """
    Trains the VQC model.
    
    This implementation uses a classical optimizer (SciPy's COBYLA) to find
    the optimal weights for the quantum circuit that minimize the cross-entropy loss.
    """
    print("Starting VQC model training...")
    X, y, scaler = featurize(records)
    n_features = X.shape[1]
    reps = 2
    n_weights = n_features * reps * 2
    
    # Save the scaler for inference later
    with open(SCALER_FILE, 'wb') as f:
        pickle.dump(scaler, f)
    print(f"Feature scaler saved to {SCALER_FILE}")

    # Initialize random weights
    initial_weights = np.random.uniform(0, 2 * np.pi, n_weights)

    print(f"Training on {len(X)} samples with {n_features} features...")
    # Use scipy's minimizer to find the optimal weights
    result = minimize(
        _objective_function,
        initial_weights,
        args=(X, y),
        method='COBYLA',
        options={'maxiter': 75} # Keep iterations reasonable for a demo
    )

    optimal_weights = result.x
    np.save(MODEL_WEIGHTS_FILE, optimal_weights)
    print(f"Training complete. Final loss: {result.fun:.4f}")
    print(f"Model weights saved to {MODEL_WEIGHTS_FILE}")

    # --- Verification Step ---
    print("\nVerifying model loading and execution with one data point...")
    sample_features = X[0]
    sample_label = y[0]
    p_success = _vqc_predict_proba(sample_features, optimal_weights)

    print(f"Sample Opp ID: {records[0]['features']['opp_id']}")
    print(f"  - Actual Outcome: {'Executable' if sample_label == 1 else 'Rejected'}")
    print(f"  - Model Prediction (P(executable)): {p_success:.4f}")


if __name__ == "__main__":
    dataset = load_dataset()
    print(f"Loaded {len(dataset)} records from the dataset.")
    if not dataset:
        print("Dataset is empty. Cannot train model.")
    else:
        train_model(dataset)