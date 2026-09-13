"""Run the StackingEnsemble on the full calibration split for every market
and report predicted-confidence range + calibration table, to see how
discriminative (or flat) each market's model actually is."""
import gc
from pathlib import Path

from app.ml.training_pipeline_logic import TrainingDataLoader, TemporalSplitter, LABEL_COLS
from app.ml.models import StackingEnsemble, MODEL_DIR

MARKETS = ['BTTS', 'Cards_3.5', 'Goals_1.5', 'Goals_2.5', 'Goals_3.5', 'Corners_7.5', 'Corners_9.5', '1x2']

for market in MARKETS:
    print(f"\n{'='*60}\n{market}\n{'='*60}")
    try:
        df = TrainingDataLoader(None, data_dir=Path('data_snapshot')).load('football', market)
        split = TemporalSplitter()
        tr, va, ca = split.split(df)
        exclude = {'fixture_id', 'sport', 'match_date', 'target'} | LABEL_COLS
        f_cols = [c for c in df.columns if c not in exclude and df[c].dtype.kind in 'biuf']
        xc = ca[f_cols].fillna(0)
        yc = ca['target']

        model = StackingEnsemble(sport='football', market=market, model_dir=MODEL_DIR)
        model.load(MODEL_DIR / f'StackingEnsemble_football_{market}.joblib')
        model.load_base_models(MODEL_DIR)

        batch = model.predict_proba(xc)
        cols = list(batch.probabilities.columns)
        # pick the "positive"/last class column for binary-style summary
        preds = batch.probabilities.iloc[:, -1]
        print(f"classes: {cols}")
        print(f"n: {len(preds)}  mean: {preds.mean():.4f}  min: {preds.min():.4f}  max: {preds.max():.4f}  spread: {preds.max()-preds.min():.4f}")

        cal_table = model.calibration_table(xc, yc)
        print(cal_table.to_string(index=False))

        del model, batch, df, tr, va, ca, xc, yc
        gc.collect()
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
