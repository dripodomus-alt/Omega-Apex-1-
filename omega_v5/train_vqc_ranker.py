#!/usr/bin/env python3
# ==============================================================================
# train_vqc_ranker.py -- Production-ready ML model training script for the
#                        route_surplus_ranker model.
#
# This script loads a dataset of past arbitrage opportunities, trains a
# gradient boosting model (XGBoost) to predict the realized net surplus, evaluates
# its performance, and saves the model artifacts, including a model card.
# ==============================================================================

import json
import os
import sys
from pathlib import Path
from typing import Any, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from omega_v5.ml_alpha import MODEL_DIR, MODEL_SPECS

MODEL_ID = "route_surplus_ranker"
DATASET_PATH = MODEL_DIR.parent / "out" / "ml" / "receipt_training_dataset.csv"


def load_and_prepare_data(path: Path) -> pd.DataFrame:
    """Loads and prepares the training data from CSV."""
    if not path.exists():
        raise FileNotFoundError(
            f"Training dataset not found at {path}. "
            "You must generate this file by running the system to collect execution data. "
            "See the ML Alpha Roadmap documentation for more details."
        )
    print(f"Loading data from {path}...")
    df = pd.read_csv(path)
    # Basic feature engineering can be added here
    # For now, we just use the raw features
    return df


def train_model(df: pd.DataFrame) -> Tuple[xgb.XGBRegressor, pd.DataFrame, pd.DataFrame]:
    """Trains the XGBoost regressor and saves it."""
    print("Training XGBoost model for route surplus ranking...")

    features = [
        'principal_usd',
        'predicted_gross_rate',
        'hops',
        'tvl_bottleneck_usd',
        'gas_price_gwei'
    ]
    target = 'realized_net_profit_usd'

    X = df[features]
    y = df[target]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = xgb.XGBRegressor(
        objective='reg:squarederror',
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1
    )

    model.fit(X_train, y_train)

    # Save the trained model
    model_path = MODEL_DIR / MODEL_ID
    model_path.mkdir(parents=True, exist_ok=True)
    model_file = model_path / f"{MODEL_ID}.joblib"
    joblib.dump(model, model_file)
    print(f"Model saved to {model_file}")

    test_df = pd.concat([X_test, y_test], axis=1)
    return model, test_df, features


def evaluate_model(model: xgb.XGBRegressor, test_df: pd.DataFrame, features: list) -> dict:
    """
    Evaluates the model and returns performance metrics.
    NOTE: Add `pandas`, `scikit-learn`, and `xgboost` to your requirements.
    """
    print("Evaluating model performance...")
    X_test = test_df[features]
    y_test = test_df['realized_net_profit_usd']

    y_pred = model.predict(X_test)

    test_df['predicted_net_profit_usd'] = y_pred

    # --- Calculate metrics ---
    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)

    # Precision@5: Of the top 5 predicted opportunities, how many were actually profitable?
    k = 5
    top_k_predictions = test_df.sort_values('predicted_net_profit_usd', ascending=False).head(k)
    actually_profitable_in_top_k = (top_k_predictions['realized_net_profit_usd'] > 0).sum()
    precision_at_k = actually_profitable_in_top_k / k

    # Out-of-sample net USD: What is the sum of profits from the top K predicted opportunities?
    out_of_sample_net_usd = top_k_predictions['realized_net_profit_usd'].sum()
    
    # Placeholder for calibration error, a key metric for probabilistic models.
    calibration_error = "not_implemented"

    metrics = {
        "r_squared": float(r2),
        "mean_absolute_error": float(mae),
        "precision_at_5": float(precision_at_k),
        "out_of_sample_net_usd": float(out_of_sample_net_usd),
        "calibration_error": calibration_error,
        "test_set_size": len(test_df),
    }
    print(f"Evaluation metrics: {json.dumps(metrics, indent=2)}")
    return metrics



def main() -> int:
    """Main training and evaluation pipeline."""
    spec = next((s for s in MODEL_SPECS if s.model_id == MODEL_ID), None)
    if not spec:
        print(f"[ERROR] No model spec found for '{MODEL_ID}' in ml_alpha.py")
        return 1

    try:
        # Step 1: Load and prepare data
        df = load_and_prepare_data(DATASET_PATH)

        # Step 2: Train the model
        model, test_df, features = train_model(df)

        # Step 3: Evaluate the model
        metrics = evaluate_model(model, test_df, features)

        # Step 4: Create and save the model card with real metrics
        model_card = {
            "model_id": MODEL_ID,
            "chain_id": 137,
            "purpose": "Re-rank exact-call candidates by expected realized net surplus.",
            "execution_authority": False,  # CRITICAL: ML models must never have execution authority
            "confidence": metrics.get('precision_at_5', 0.0),
            "metrics": metrics,
            "training_data": {
                "source": str(DATASET_PATH.relative_to(MODEL_DIR.parent)),
                "features": features,
                "target": "realized_net_profit_usd",
            },
            "model_artifact": f"{MODEL_ID}/{MODEL_ID}.joblib",
        }

        model_path = MODEL_DIR / MODEL_ID
        card_path = model_path / "model_card.json"
        card_path.write_text(json.dumps(model_card, indent=2), encoding="utf-8")

        print(f"\n[SUCCESS] Model card for '{MODEL_ID}' created at: {card_path}")
        print("The ML Alpha pipeline is now configured with a trained model and live metrics.")

    except Exception as e:
        print(f"\n[ERROR] An error occurred during the training pipeline: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())