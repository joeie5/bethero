"""One-off: use the CURRENT (pre-Elo-fix) trained models to predict
1x2, Corners_7.5, and BTTS for every English Premier League 2025/2026
fixture, and compare against actual results where ground truth exists."""
from pathlib import Path

import pandas as pd

from app.ml.feature_engineer import FeatureEngineer
from app.ml.models import StackingEnsemble, MODEL_DIR

fe = FeatureEngineer(supabase_client=None, data_dir=Path("data_snapshot"))
fx = fe._local["fixtures"]
mr = fe._local["match_results"]

epl = fx[(fx["league_name"] == "Premier League") & (fx["season"] == 2025)]
epl = epl.merge(mr[["fixture_id", "btts", "total_corners", "home_goals", "away_goals", "ftr"]],
                 on="fixture_id", how="left")
epl = epl.dropna(subset=["home_goals"])  # only played matches
epl = epl.sort_values("match_date")
print(f"EPL 2025/2026 played fixtures: {len(epl)}")

pairs = list(zip(["football"] * len(epl), epl["fixture_id"].tolist()))
feats = fe.build_batch(pairs)
print(f"features built: {len(feats)}")

merged = feats.merge(epl[["fixture_id", "btts", "total_corners", "ftr", "home_team", "away_team", "match_date"]],
                      on="fixture_id", how="left")
exclude = {"fixture_id", "btts", "total_corners", "ftr", "home_team", "away_team", "match_date", "sport"}
f_cols = [c for c in merged.columns if c not in exclude and merged[c].dtype.kind in "biuf"]
X = merged[f_cols].fillna(0)

all_results = {}

# ── Binary markets: Corners_7.5, BTTS ──────────────────────────────
for market, actual_col, actual_fn in [
    ("Corners_7.5", "total_corners", lambda v: (v > 7.5).astype(int)),
    ("BTTS", "btts", lambda v: v.astype(int)),
]:
    model = StackingEnsemble(sport="football", market=market, model_dir=MODEL_DIR)
    model.load(MODEL_DIR / f"StackingEnsemble_football_{market}.joblib")
    model.load_base_models(MODEL_DIR)

    batch = model.predict_proba(X)
    cols = list(batch.probabilities.columns)
    pred_col = next(c for c in cols if c.startswith("Over") or c == "Yes")
    pred_prob = batch.probabilities[pred_col]

    raw_actual = merged[actual_col]
    has_ground_truth = raw_actual.notna().any()

    print(f"\n=== {market} ===")
    print(f"predicted class column: {pred_col}")
    print(f"mean predicted prob ({pred_col}): {pred_prob.mean():.4f}")
    print(f"predicted-Over/Yes rate (>=0.5 threshold): {(pred_prob >= 0.5).mean():.4f}")

    df_out = merged[["home_team", "away_team", "match_date"]].copy()
    df_out["pred_prob"] = pred_prob.values
    if has_ground_truth:
        actual = actual_fn(raw_actual)
        pred_label = (pred_prob >= 0.5).astype(int)
        accuracy = (pred_label == actual).mean()
        brier = ((pred_prob - actual) ** 2).mean()
        print(f"actual rate: {actual.mean():.4f}")
        print(f"accuracy (>=0.5 threshold): {accuracy:.4f}")
        print(f"brier score: {brier:.4f}")
        df_out["actual"] = actual.values
    else:
        print(f"NO GROUND TRUTH AVAILABLE for {actual_col} — predictions only, no accuracy/brier possible")
    all_results[market] = df_out

# ── 1x2: 3-class market ─────────────────────────────────────────────
model = StackingEnsemble(sport="football", market="1x2", model_dir=MODEL_DIR)
model.load(MODEL_DIR / "StackingEnsemble_football_1x2.joblib")
model.load_base_models(MODEL_DIR)

batch = model.predict_proba(X)
probs = batch.probabilities  # columns: Away, Draw, Home
pred_class = probs.idxmax(axis=1)

ftr_map = {"H": "Home", "D": "Draw", "A": "Away"}
actual_class = merged["ftr"].map(ftr_map)
has_ground_truth = actual_class.notna().any()

print(f"\n=== 1x2 ===")
print("mean predicted probabilities:")
print(probs.mean().to_string())
print("predicted-class distribution:")
print(pred_class.value_counts(normalize=True).to_string())

df_out = merged[["home_team", "away_team", "match_date"]].copy()
for c in probs.columns:
    df_out[f"pred_prob_{c}"] = probs[c].values
df_out["predicted"] = pred_class.values

if has_ground_truth:
    accuracy = (pred_class == actual_class).mean()
    print(f"actual-class distribution:")
    print(actual_class.value_counts(normalize=True).to_string())
    print(f"accuracy (argmax vs actual): {accuracy:.4f}")
    df_out["actual"] = actual_class.values
else:
    print("NO GROUND TRUTH AVAILABLE for ftr — predictions only")
all_results["1x2"] = df_out

for market, df in all_results.items():
    out = Path(f"epl_2025_{market.replace('.', '_')}_predictions.csv")
    df.to_csv(out, index=False)
    print(f"saved {out}")
