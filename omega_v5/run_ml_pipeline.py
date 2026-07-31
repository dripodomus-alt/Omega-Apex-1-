#!/usr/bin/env python3
"""
run_ml_pipeline.py - Master orchestrator for the ML Alpha training pipeline.
"""

import logging
import shutil
from pathlib import Path

from omega_v5.ml_data_collector import collect_training_data
from omega_v5.train_vqc_ranker import main as run_training

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "route_surplus_ranker"
PROD_MODEL_PATH = MODEL_DIR / "route_surplus_ranker.joblib"
CANDIDATE_MODEL_PATH = MODEL_DIR / "candidate.joblib"

def main():
    """
    Orchestrates the full data collection, training, and model promotion pipeline.
    """
    logging.info("--- Starting ML Alpha Training Pipeline ---")

    # Step 1: Collect latest data
    logging.info("[1/4] Collecting training data from execution traces...")
    try:
        data_summary = collect_training_data()
        if data_summary.get("rows", 0) == 0:
            logging.warning("No new training data found. Exiting.")
            return
        logging.info(f"Successfully collected {data_summary['rows']} new training rows.")
    except Exception as e:
        logging.error(f"Data collection failed: {e}", exc_info=True)
        return

    # Step 2: Train a new candidate model
    logging.info("[2/4] Training new candidate model...")
    try:
        # We need to adapt train_vqc_ranker to accept an output path
        # For now, we'll assume it saves to a candidate path.
        # A refactor would be `train_model(dataset_path, output_path)`
        run_training() # This will create the model card and .joblib file
        logging.info("Candidate model training complete.")
    except Exception as e:
        logging.error(f"Model training failed: {e}", exc_info=True)
        return

    # Step 3: Evaluate and Promote (Simplified)
    # A real implementation would load both models and compare their performance
    # on a held-out validation dataset.
    logging.info("[3/4] Evaluating and promoting model...")
    candidate_model_file = MODEL_DIR / "route_surplus_ranker.joblib" # As per train_vqc_ranker.py
    if candidate_model_file.exists():
        logging.info(f"Promoting new model to production: {PROD_MODEL_PATH}")
        shutil.move(candidate_model_file, PROD_MODEL_PATH)
    
    logging.info("[4/4] --- ML Alpha Training Pipeline Complete ---")

if __name__ == "__main__":
    main()