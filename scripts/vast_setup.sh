#!/usr/bin/env bash
# One-time environment setup on a fresh Vast.ai instance.
# Run this once after SSH'ing in and cloning the repo.
#
# Mirrors the lessons learned getting this working on Colab:
# - requirements.txt's exact pins don't have prebuilt wheels for every
#   Python version and fall back to slow from-source builds — install
#   only what training actually needs, mostly unpinned.
# - supabase IS pinned: a newer supabase-py restructured ClientOptions
#   (app/database.py builds one with storage_client_timeout), confirmed
#   breaking live on an unpinned install. supabase-py is pure Python so
#   pinning it doesn't reintroduce the slow-build problem.
# - sqlalchemy is required by app/database.py but was never even listed
#   in requirements.txt at all — a pre-existing gap, added explicitly.
# - torch is intentionally NOT installed here if the instance image
#   already ships a CUDA-enabled build (e.g. a PyTorch-based Vast.ai
#   template) — installing requirements.txt's torch==2.2.2+cpu over that
#   would silently disable the GPU. Uncomment the torch line below only
#   if this instance's base image has no PyTorch at all.

set -euo pipefail

echo "=== Checking GPU ==="
nvidia-smi

echo "=== Installing training dependencies ==="
pip install -q pandas numpy scikit-learn xgboost lightgbm joblib optuna mlflow \
    "supabase==2.10.0" python-dotenv sqlalchemy pydantic pydantic-settings

# Uncomment if this instance has no PyTorch preinstalled at all:
# pip install -q torch --index-url https://download.pytorch.org/whl/cu121

echo "=== Verifying CUDA is visible to PyTorch ==="
python3 -c "
import torch
print('CUDA available:', torch.cuda.is_available())
print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only — check the instance image/GPU attachment')
"

echo "=== Verifying data_snapshot/ is present ==="
if [ ! -d "data_snapshot" ]; then
    echo "ERROR: data_snapshot/ not found. scp it up from your local machine first:"
    echo "  scp -r data_snapshot/ <user>@<host>:<repo-path>/data_snapshot/"
    exit 1
fi
echo "data_snapshot/ found — $(ls data_snapshot/*.parquet | wc -l) parquet files"

echo "=== Verifying .env is present ==="
if [ ! -f ".env" ]; then
    echo "ERROR: .env not found. scp it up from your local machine first:"
    echo "  scp .env <user>@<host>:<repo-path>/.env"
    exit 1
fi
echo ".env found"

echo ""
echo "=== Setup complete — ready to train ==="
echo "Run inside tmux (survives SSH disconnects):"
echo "  tmux new -s training"
echo "  python3 scripts/vast_train.py --markets all --n-trials 20"
echo "  (Ctrl+B then D to detach — training keeps running after you disconnect)"
