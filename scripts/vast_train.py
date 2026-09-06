"""
vast_train.py — CLI training driver for a Vast.ai GPU rental.

Same resumable, skip-if-already-trained loop as notebooks/train_on_colab.ipynb,
but as a plain script for a real SSH session instead of Colab cells — meant
to be run inside tmux/screen so it survives SSH disconnects (see
scripts/vast_setup.sh).

Usage:
    python3 scripts/vast_train.py --markets all --n-trials 20
    python3 scripts/vast_train.py --markets BTTS,1x2 --n-trials 20 --limit 50000
    python3 scripts/vast_train.py --markets Cards_3.5 --n-trials 10 --dry-run

Progress is printed with flush=True after every model and every market, so
`tail -f` on a redirected log file shows real-time progress (see the
`nohup ... > train.log 2>&1 &` pattern in the deploy guide as an alternative
to tmux).
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

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data_snapshot"


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
    from app.ml.models import MODEL_DIR
    from app.ml.training_pipeline_logic import train_market

    print(f"MODEL_DIR: {MODEL_DIR}")
    print(f"DATA_DIR:  {args.data_dir}")
    print(f"Markets:   {markets}")
    print(f"n_trials={args.n_trials}  n_meta_trials={args.n_meta_trials}  limit={args.limit}  dry_run={args.dry_run}")

    grand_t0 = time.monotonic()
    for model_key in markets:
        ensemble_path = MODEL_DIR / f"StackingEnsemble_football_{model_key}.joblib"
        if ensemble_path.exists() and not args.dry_run:
            print(f"=== {model_key}: already trained, skipping ({ensemble_path}) ===", flush=True)
            continue

        print(f"\n=== {model_key} — starting (limit={args.limit}) ===", flush=True)
        t0 = time.monotonic()
        results = train_market(
            "football", model_key,
            n_trials=args.n_trials, n_meta_trials=args.n_meta_trials,
            limit=args.limit, data_dir=args.data_dir, dry_run=args.dry_run,
        )
        elapsed = time.monotonic() - t0
        for r in results:
            print(f"  {r.model_name}: {r.status} {r.error or ''} ({r.duration_s}s)", flush=True)
            if r.calibration_table is not None:
                print(r.calibration_table.to_string(index=False), flush=True)
        print(f"{model_key} done in {elapsed/60:.1f} min", flush=True)

    total_elapsed = time.monotonic() - grand_t0
    print(f"\n=== ALL REQUESTED MARKETS DONE ({total_elapsed/3600:.2f} hours total) ===", flush=True)


if __name__ == "__main__":
    main()
