"""One-off: regenerate Goals market predictions for the full season with the
fixed best_edge_across_lines selection logic (see predictor.py fix)."""
import time
import pandas as pd

from app.database import get_supabase_admin
from app.ml.predictor import Predictor

MAIN_TIER_LEAGUES = [
    "E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3",
    "D1", "D2", "SP1", "SP2", "I1", "I2", "F1", "F2",
    "N1", "B1", "P1", "T1", "G1",
]

df = pd.read_parquet("data_snapshot/fixtures_football.parquet")
season = df[(df["season"] == 2026) & (df["league_key"].isin(MAIN_TIER_LEAGUES)) & (df["status"] == "FT")].sort_values("match_date")
fixture_ids = season["fixture_id"].tolist()
print(f"Fixtures to predict: {len(fixture_ids)}", flush=True)

client = get_supabase_admin()
predictor = Predictor(client, data_dir="data_snapshot")

t0 = time.monotonic()
ok = 0
failed = 0
for i, fid in enumerate(fixture_ids):
    try:
        predictor.predict_match("football", fid, markets=["Goals"], persist=True)
        ok += 1
    except Exception as exc:
        failed += 1
        if failed <= 5:
            print(f"  {fid} failed: {exc}", flush=True)
    if (i + 1) % 200 == 0:
        print(f"  {i+1}/{len(fixture_ids)} ({time.monotonic()-t0:.0f}s elapsed)", flush=True)
print(f"Goals: {ok} ok, {failed} failed ({time.monotonic()-t0:.1f}s)", flush=True)
