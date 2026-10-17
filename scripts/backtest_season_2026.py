"""
backtest_season_2026.py — Real calibration/accuracy backtest for the
2026/27 season, built directly off the `predictions` table rows that
generate_season_predictions.py persisted (i.e. validates exactly what the
app actually serves, not a fresh recomputation).

For each stored prediction row, determines whether that specific
`selection` was actually correct against the real match_results outcome,
then reports a calibration table (predicted-confidence bucket vs actual
hit rate, per CLAUDE.md §1.2 — no bucket should be >~10pts off) and
overall accuracy, broken out by market.

Usage:
    PYTHONPATH=. python3 scripts/backtest_season_2026.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.database import get_supabase_admin
from scripts.export_snapshot import fetch_all

MAIN_TIER_LEAGUES = [
    "E0", "E1", "E2", "E3", "EC",
    "SC0", "SC1", "SC2", "SC3",
    "D1", "D2", "SP1", "SP2", "I1", "I2", "F1", "F2",
    "N1", "B1", "P1", "T1", "G1",
]


def _actual_correct(row: pd.Series) -> bool | None:
    """Was this persisted selection actually right, given real match_results?"""
    market, selection = row["market"], row["selection"]

    if market == "BTTS":
        if pd.isna(row["btts"]):
            return None
        actual_yes = bool(row["btts"])
        return actual_yes == (selection == "Yes")

    if market == "Cards":
        if pd.isna(row["total_cards"]):
            return None
        over = row["total_cards"] > 3.5
        return over == selection.startswith("Over")

    if market == "Over_Under_Corners":
        if pd.isna(row["total_corners"]):
            return None
        line = float(selection.split()[-1])
        is_over = selection.startswith("Over")
        actual_over = row["total_corners"] > line
        return actual_over == is_over

    if market == "Over_Under_Goals":
        if pd.isna(row["home_goals"]) or pd.isna(row["away_goals"]):
            return None
        total_goals = row["home_goals"] + row["away_goals"]
        line = float(selection.split()[-1])
        is_over = selection.startswith("Over")
        actual_over = total_goals > line
        return actual_over == is_over

    if market == "1X2":
        if pd.isna(row["ftr"]):
            return None
        ftr_map = {"H": "Home", "D": "Draw", "A": "Away"}
        return ftr_map.get(row["ftr"]) == selection

    return None


def calibration_table(df: pd.DataFrame, n_buckets: int = 10) -> pd.DataFrame:
    edges = np.linspace(0.0, 1.0, n_buckets + 1)
    idx = np.clip(np.digitize(df["model_probability"], edges) - 1, 0, n_buckets - 1)
    rows = []
    for b in range(n_buckets):
        mask = idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        rows.append({
            "bucket": f"{edges[b]:.1f}-{edges[b+1]:.1f}",
            "n": n,
            "predicted_conf": round(df.loc[mask, "model_probability"].mean(), 4),
            "actual_hit_rate": round(df.loc[mask, "correct"].mean(), 4),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["abs_error"] = (out["predicted_conf"] - out["actual_hit_rate"]).abs().round(4)
        out["within_bound"] = out["abs_error"] <= 0.10
    return out


def main() -> None:
    client = get_supabase_admin()

    print("Fetching predictions...")
    preds = fetch_all(client, "predictions", "*", {"sport": "football"})
    print(f"  {len(preds)} total prediction rows")

    print("Fetching fixtures (for season/league filter)...")
    fixtures = fetch_all(client, "fixtures", "fixture_id,season,league_key", {"sport": "football"})
    season_fixtures = fixtures[
        (fixtures["season"] == 2026) & (fixtures["league_key"].isin(MAIN_TIER_LEAGUES))
    ]

    preds = preds.merge(season_fixtures[["fixture_id"]], on="fixture_id", how="inner")
    print(f"  {len(preds)} prediction rows for 2026/27 Main-tier fixtures")

    print("Fetching match_results (actual outcomes)...")
    results = fetch_all(
        client, "match_results",
        "fixture_id,btts,total_cards,total_corners,home_goals,away_goals,ftr",
        {"sport": "football"},
    )
    preds = preds.merge(results, on="fixture_id", how="left")

    preds["correct"] = preds.apply(_actual_correct, axis=1)
    preds = preds.dropna(subset=["correct"])
    preds["correct"] = preds["correct"].astype(float)
    print(f"  {len(preds)} rows with a resolved actual outcome\n")

    for market in sorted(preds["market"].unique()):
        sub = preds[preds["market"] == market]
        print(f"=== {market} (n={len(sub)}, accuracy={sub['correct'].mean():.4f}) ===")
        table = calibration_table(sub)
        print(table.to_string(index=False) if not table.empty else "  (not enough data)")
        print()


if __name__ == "__main__":
    main()
