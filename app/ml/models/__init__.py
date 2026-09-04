"""
app.ml.models — Bet Hero model layer.

Public API
----------
    from app.ml.models import StackingEnsemble, MODEL_DIR

    ensemble = StackingEnsemble(sport="football", market="BTTS", model_dir=MODEL_DIR)
"""

from __future__ import annotations

import os
from pathlib import Path

from app.ml.models.base_model import (
    BetHeroBaseModel,
    BacktestResult,
    CalibrationMethod,
    PredictionBatch,
    TrainingResult,
)
from app.ml.models.ensemble import StackingEnsemble
from app.ml.models.lightgbm_model import LightGBMBetModel
from app.ml.models.lstm_model import LSTMBetModel
from app.ml.models.neural_network_model import NeuralNetworkBetModel
from app.ml.models.random_forest_model import RandomForestBetModel
from app.ml.models.xgboost_model import XGBoostBetModel

MODEL_DIR = Path(os.getenv("MODEL_DIR", "models"))

__all__ = [
    "MODEL_DIR",
    "BetHeroBaseModel",
    "BacktestResult",
    "CalibrationMethod",
    "PredictionBatch",
    "TrainingResult",
    "StackingEnsemble",
    "LightGBMBetModel",
    "LSTMBetModel",
    "NeuralNetworkBetModel",
    "RandomForestBetModel",
    "XGBoostBetModel",
]
