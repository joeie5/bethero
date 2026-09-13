"""One-off integrity check: actually load every model file (not just check
size) to find silent truncation from the earlier disk-full cp failure."""
import joblib
import torch
from pathlib import Path

MARKETS = ['BTTS', 'Cards_3.5', 'Goals_1.5', 'Goals_2.5', 'Goals_3.5', 'Corners_7.5', 'Corners_9.5', '1x2']
JOBLIB_MODELS = ['RandomForestBetModel', 'XGBoostBetModel', 'LightGBMBetModel', 'StackingEnsemble']
PT_MODELS = ['NeuralNetworkBetModel', 'LSTMBetModel']

broken = []
for market in MARKETS:
    for model in JOBLIB_MODELS:
        f = Path('models') / f'{model}_football_{market}.joblib'
        try:
            joblib.load(f)
        except Exception as e:
            broken.append((str(f), type(e).__name__))
    for model in PT_MODELS:
        f = Path('models') / f'{model}_football_{market}.pt'
        try:
            torch.load(f, weights_only=False, map_location=torch.device('cpu'))
        except Exception as e:
            broken.append((str(f), type(e).__name__))

print(f"BROKEN: {len(broken)} / 96")
for f, err in broken:
    print(f"  {f}: {err}")
