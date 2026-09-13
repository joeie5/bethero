"""
local_train_resumable.py — CPU-only local training driver, resumable across
sleep AND shutdown/reboot.

Why this exists instead of scripts/vast_train.py:
  - vast_train.py only skips a whole MARKET if its ensemble file already
    exists — a shutdown mid-market (e.g. after 3 of 5 base models finish)
    would silently re-train those 3 already-done models from scratch.
  - This driver checks each of the 48 (market, model) files individually,
    comparing its mtime against the feature cache's rebuild time, so a
    shutdown only ever costs whatever single model was actively training.
  - It also disables MLflow's local artifact copy (mlflow.log_artifact
    duplicates the saved model file into ./mlruns/ — harmless normally, but
    with a 2.2GB Random Forest model and ~3.7GB free disk, that copy alone
    could fill the disk. Params/metrics logging is unaffected.)

Usage:
    PYTHONPATH=. python3 scripts/local_train_resumable.py
    PYTHONPATH=. python3 scripts/local_train_resumable.py --markets BTTS,1x2

Safe to interrupt (sleep, shutdown, Ctrl+C) and re-run — it picks up exactly
where it left off.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

# Must be set BEFORE importing app.ml.models — RandomForestBetModel reads
# these as default-argument expressions at class-definition (import) time.
# This machine has 8 cores / 15.8GB RAM with as little as ~2-3GB free; the
# unconstrained search (n_jobs=-1, up to 1000 trees, depth 30) is what
# produced the 2.19GB (1x2) and 1.48GB (Corners_9.5) models on the 32-core/
# 24GB+ Vast.ai box and silently OOM-killed this machine mid-fit with no
# traceback. These caps trade some model complexity for actually completing.
os.environ.setdefault("BETHERO_RF_N_JOBS", "2")
os.environ.setdefault("BETHERO_RF_MAX_ESTIMATORS", "300")
os.environ.setdefault("BETHERO_RF_MAX_DEPTH", "16")

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = REPO_ROOT / "models"
DATA_DIR = REPO_ROOT / "data_snapshot"
FEATURE_CACHE = DATA_DIR / "feature_cache_football.parquet"

ALL_MARKETS = [
    "BTTS", "Cards_3.5",
    "Goals_1.5", "Goals_2.5", "Goals_3.5",
    "Corners_7.5", "Corners_9.5",
    "1x2",
]

# registry key -> (class name used in saved filenames, file extension)
MODEL_KEY_TO_CLASS = {
    "random_forest":  ("RandomForestBetModel", "joblib"),
    "xgboost":        ("XGBoostBetModel", "joblib"),
    "lightgbm":       ("LightGBMBetModel", "joblib"),
    "neural_network": ("NeuralNetworkBetModel", "pt"),
    "lstm":           ("LSTMBetModel", "pt"),
}


def is_fresh(class_name: str, market: str, cutoff: float) -> bool:
    ext = "pt" if class_name in ("NeuralNetworkBetModel", "LSTMBetModel") else "joblib"
    f = MODEL_DIR / f"{class_name}_football_{market}.{ext}"
    return f.exists() and f.stat().st_mtime > cutoff


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--markets", default="all")
    parser.add_argument("--n-trials", type=int, default=20)
    parser.add_argument("--n-meta-trials", type=int, default=20)
    args = parser.parse_args()

    markets = ALL_MARKETS if args.markets == "all" else [m.strip() for m in args.markets.split(",")]

    if not FEATURE_CACHE.exists():
        raise SystemExit(f"Feature cache not found: {FEATURE_CACHE}")
    cutoff = FEATURE_CACHE.stat().st_mtime
    print(f"Freshness cutoff (feature cache rebuild time): {time.ctime(cutoff)}")

    # Disable MLflow's local artifact copy — see module docstring.
    import mlflow
    mlflow.log_artifact = lambda *a, **kw: None

    from app.ml.training_pipeline_logic import (
        ModelTrainer, MLflowLogger, PipelineConfig, TrainingDataLoader, MODEL_REGISTRY,
    )
    from app.database import get_supabase_admin

    client = get_supabase_admin()
    mlflow_logger = MLflowLogger()
    grand_t0 = time.monotonic()

    for market in markets:
        print(f"\n{'='*60}\n{market}\n{'='*60}", flush=True)

        needed = [
            key for key, (cls_name, _ext) in MODEL_KEY_TO_CLASS.items()
            if not is_fresh(cls_name, market, cutoff)
        ]
        ensemble_fresh = is_fresh("StackingEnsemble", market, cutoff)

        if not needed and ensemble_fresh:
            print(f"  {market}: all 6 models already fresh, skipping", flush=True)
            continue

        # Load the training frame once, reused across every model for this market.
        df = TrainingDataLoader(client, data_dir=DATA_DIR).load("football", market)
        if df is None:
            print(f"  {market}: no data, skipping", flush=True)
            continue

        for key in needed:
            cls_name, _ext = MODEL_KEY_TO_CLASS[key]
            print(f"  [{market}/{cls_name}] training...", flush=True)
            t0 = time.monotonic()
            cfg = PipelineConfig(sport="football", market=market, model_name=key,
                                  n_trials=args.n_trials, n_meta_trials=args.n_meta_trials)
            res = ModelTrainer(cfg, mlflow_logger, df=df).run()
            elapsed = time.monotonic() - t0
            print(f"  [{market}/{cls_name}] {res.status} in {elapsed:.1f}s {res.error or ''}", flush=True)
            if res.status == "failed":
                print(f"  [{market}] aborting ensemble stage due to base model failure", flush=True)
                break
        else:
            # All base models present and fresh (either just trained or already were) — do the ensemble.
            if not ensemble_fresh:
                print(f"  [{market}/StackingEnsemble] training...", flush=True)
                t0 = time.monotonic()
                cfg = PipelineConfig(sport="football", market=market, model_name="StackingEnsemble",
                                      n_trials=args.n_trials, n_meta_trials=args.n_meta_trials)
                res = ModelTrainer(cfg, mlflow_logger, df=df).run()
                elapsed = time.monotonic() - t0
                print(f"  [{market}/StackingEnsemble] {res.status} in {elapsed:.1f}s {res.error or ''}", flush=True)
                if res.calibration_table is not None:
                    print(res.calibration_table.to_string(index=False), flush=True)
            else:
                print(f"  [{market}/StackingEnsemble] already fresh, skipping", flush=True)

        del df  # free memory before moving to the next market

    total = time.monotonic() - grand_t0
    print(f"\n=== ALL MARKETS DONE ({total/3600:.2f} hours total) ===", flush=True)


if __name__ == "__main__":
    main()
