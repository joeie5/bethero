"""
vast_train.py — CLI training driver for a Vast.ai GPU rental.

Per-model resumable (not just per-market): checks each of the 48
(market, model) files individually against the feature cache's rebuild
time, so an instance interruption, SSH disconnect, or crash mid-market
only costs whatever single model was actively training — re-running this
script picks up exactly where it left off. Meant to be run inside
tmux/screen so it survives SSH disconnects (see scripts/vast_setup.sh).

Also disables MLflow's local artifact copy (mlflow.log_artifact
duplicates every saved model into ./mlruns/ — harmless with Vast.ai's
larger disk, but wasteful and unnecessary since the real model files are
already saved to MODEL_DIR by model.save()).

Usage:
    python3 scripts/vast_train.py --markets all --n-trials 20
    python3 scripts/vast_train.py --markets BTTS,1x2 --n-trials 20 --limit 50000
    python3 scripts/vast_train.py --markets Cards_3.5 --n-trials 10 --dry-run

Progress is printed with flush=True after every model and every market, so
`tail -f` on a redirected log file shows real-time progress.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

ALL_MARKETS = [
    "BTTS", "Cards_3.5",
    "Goals_1.5", "Goals_2.5", "Goals_3.5",
    "Corners_7.5", "Corners_9.5",
    "1x2",
]

# registry key -> class name used in saved filenames
MODEL_KEY_TO_CLASS = {
    "random_forest":  "RandomForestBetModel",
    "xgboost":        "XGBoostBetModel",
    "lightgbm":       "LightGBMBetModel",
    "neural_network": "NeuralNetworkBetModel",
    "lstm":           "LSTMBetModel",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data_snapshot"


def _is_fresh(model_dir: Path, class_name: str, market: str, cutoff: float) -> bool:
    ext = "pt" if class_name in ("NeuralNetworkBetModel", "LSTMBetModel") else "joblib"
    f = model_dir / f"{class_name}_football_{market}.{ext}"
    return f.exists() and f.stat().st_mtime > cutoff


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--markets", default="all",
                         help="Comma-separated model_keys, or 'all' for every market (default: all)")
    parser.add_argument("--n-trials", type=int, default=20, help="Optuna trials per base model (default: 20)")
    parser.add_argument("--n-meta-trials", type=int, default=20, help="Optuna trials for the ensemble meta-learner (default: 20)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Cap training rows to the most recent N (default: no cap — full dataset)")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                         help=f"Path to the feature-cache snapshot (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--dry-run", action="store_true", help="Validate the pipeline without actually training")
    args = parser.parse_args()

    markets = ALL_MARKETS if args.markets == "all" else [m.strip() for m in args.markets.split(",")]
    unknown = set(markets) - set(ALL_MARKETS)
    if unknown:
        raise SystemExit(f"Unknown market_key(s): {unknown} — valid: {ALL_MARKETS}")

    # Imported here, not at module level, so --help works even before
    # app.ml.* (and its Supabase client construction) is importable.
    import mlflow
    mlflow.log_artifact = lambda *a, **kw: None  # see module docstring

    from app.ml.models import MODEL_DIR
    from app.ml.training_pipeline_logic import (
        ModelTrainer, MLflowLogger, PipelineConfig, TrainingDataLoader,
    )
    from app.database import get_supabase_admin

    feature_cache = args.data_dir / "feature_cache_football.parquet"
    cutoff = feature_cache.stat().st_mtime if feature_cache.exists() else 0.0

    print(f"MODEL_DIR: {MODEL_DIR}")
    print(f"DATA_DIR:  {args.data_dir}")
    print(f"Markets:   {markets}")
    print(f"n_trials={args.n_trials}  n_meta_trials={args.n_meta_trials}  limit={args.limit}  dry_run={args.dry_run}")
    print(f"Freshness cutoff: {time.ctime(cutoff) if cutoff else '(no existing feature cache — nothing skipped)'}")

    client = get_supabase_admin()
    mlflow_logger = MLflowLogger()
    grand_t0 = time.monotonic()

    for model_key in markets:
        print(f"\n=== {model_key} ===", flush=True)

        needed = [
            key for key, cls_name in MODEL_KEY_TO_CLASS.items()
            if not (_is_fresh(MODEL_DIR, cls_name, model_key, cutoff) and not args.dry_run)
        ]
        ensemble_fresh = _is_fresh(MODEL_DIR, "StackingEnsemble", model_key, cutoff) and not args.dry_run

        if not needed and ensemble_fresh:
            print(f"  {model_key}: all 6 models already fresh, skipping", flush=True)
            continue

        t0 = time.monotonic()
        df = TrainingDataLoader(client, data_dir=args.data_dir).load(
            "football", model_key, limit=args.limit,
        )
        if df is None:
            print(f"  {model_key}: no data, skipping", flush=True)
            continue

        for key in needed:
            cls_name = MODEL_KEY_TO_CLASS[key]
            m0 = time.monotonic()
            cfg = PipelineConfig(sport="football", market=model_key, model_name=key,
                                  n_trials=args.n_trials, n_meta_trials=args.n_meta_trials,
                                  dry_run=args.dry_run)
            res = ModelTrainer(cfg, mlflow_logger, df=df).run()
            print(f"  {cls_name}: {res.status} {res.error or ''} ({time.monotonic()-m0:.1f}s)", flush=True)
            if res.status == "failed":
                print(f"  {model_key}: aborting ensemble stage due to base model failure", flush=True)
                break
        else:
            if not ensemble_fresh:
                m0 = time.monotonic()
                cfg = PipelineConfig(sport="football", market=model_key, model_name="StackingEnsemble",
                                      n_trials=args.n_trials, n_meta_trials=args.n_meta_trials,
                                      dry_run=args.dry_run)
                res = ModelTrainer(cfg, mlflow_logger, df=df).run()
                print(f"  StackingEnsemble: {res.status} {res.error or ''} ({time.monotonic()-m0:.1f}s)", flush=True)
                if res.calibration_table is not None:
                    print(res.calibration_table.to_string(index=False), flush=True)
            else:
                print(f"  StackingEnsemble: already fresh, skipping", flush=True)

        del df
        print(f"{model_key} done in {(time.monotonic()-t0)/60:.1f} min", flush=True)

    total_elapsed = time.monotonic() - grand_t0
    print(f"\n=== ALL REQUESTED MARKETS DONE ({total_elapsed/3600:.2f} hours total) ===", flush=True)


if __name__ == "__main__":
    main()
