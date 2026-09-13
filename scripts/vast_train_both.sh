#!/bin/bash
# vast_train_both.sh — Train every market twice on the Vast.ai box:
#   1. "full"   — RandomForest's true, unconstrained search (n_estimators<=1000,
#                 max_depth<=30, n_jobs=-1) — same settings as the original
#                 successful training run.
#   2. "shrunk" — capped (n_estimators<=300, max_depth<=16) to see whether a
#                 dramatically smaller Random Forest costs meaningful accuracy.
#                 Motivated by the VPS's 1.6GB RAM: the 1x2 (2.19GB) and
#                 Corners_9.5 (1.48GB) Random Forests from the full run
#                 can't fit there at all regardless of storage location.
#
# Two fully separate output directories (models_full/, models_shrunk/) so
# neither run clobbers the other — compare file sizes and calibration
# tables side by side afterward.
#
# Run from the repo root on the Vast.ai instance:
#   bash scripts/vast_train_both.sh
#
# Sequential, not parallel — both configs would otherwise fight over the
# same CPU cores (each defaults to n_jobs=-1), which would slow both down
# more than running them one after another.

set -e
cd "$(dirname "$0")/.."

echo "=== [1/2] FULL (uncapped) — all markets, full dataset ==="
mkdir -p models_full
MODEL_DIR=models_full \
  PYTHONPATH=. python3 scripts/vast_train.py --markets all --n-trials 20 --n-meta-trials 20 \
  2>&1 | tee train_full.log

echo ""
echo "=== [2/2] SHRUNK (capped Random Forest) — all markets, full dataset ==="
mkdir -p models_shrunk
MODEL_DIR=models_shrunk \
BETHERO_RF_N_JOBS=-1 \
BETHERO_RF_MAX_ESTIMATORS=300 \
BETHERO_RF_MAX_DEPTH=16 \
  PYTHONPATH=. python3 scripts/vast_train.py --markets all --n-trials 20 --n-meta-trials 20 \
  2>&1 | tee train_shrunk.log

echo ""
echo "=== BOTH RUNS COMPLETE ==="
echo "--- Random Forest file size comparison ---"
for f in models_full/RandomForestBetModel_football_*.joblib; do
  market=$(basename "$f" .joblib | sed 's/RandomForestBetModel_football_//')
  full_size=$(du -h "$f" | cut -f1)
  shrunk_size=$(du -h "models_shrunk/RandomForestBetModel_football_${market}.joblib" 2>/dev/null | cut -f1 || echo "MISSING")
  echo "  ${market}: full=${full_size}  shrunk=${shrunk_size}"
done
