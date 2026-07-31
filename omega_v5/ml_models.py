"""
ml_models.py - Centralized loader for production ML models.
"""
import logging
import os
from typing import Any, Optional

import joblib  # Using joblib as it's common for sklearn/xgboost models

logger = logging.getLogger(__name__)

_ranker_model: Optional[Any] = None
MODEL_PATH = os.environ.get("OMEGA_RANKER_MODEL_PATH", "out/models/route_surplus_ranker.joblib")


def get_ranker_model() -> Optional[Any]:
    """
    Loads the route_surplus_ranker model from disk.

    Returns a loaded model object (e.g., an XGBoost classifier) or None if not found.
    """
    global _ranker_model
    if _ranker_model:
        return _ranker_model

    if not os.path.exists(MODEL_PATH):
        logger.warning(f"Ranker model not found at {MODEL_PATH}. ML ranking will be disabled.")
        return None

    try:
        logger.info(f"Loading route surplus ranker model from: {MODEL_PATH}")
        _ranker_model = joblib.load(MODEL_PATH)
        return _ranker_model
    except Exception as e:
        logger.error(f"Failed to load ranker model from {MODEL_PATH}: {e}", exc_info=True)
        return None