"""
Offline batch trainer — the ONLY place football models get trained.

Trains every (league x model x market) combination and writes results to
results_cache/football/{league}/{model}/{market}/:
  predictions.parquet   (or .csv fallback)  -- raw out-of-fold predictions
  calibration.json                          -- calibration_table() as records
  tickets.json                              -- 3x/5x/10x tiers + streaks
  verdict.json                              -- go/no-go

app.py reads ONLY from this cache at request time — no live .fit() calls.

Usage:
  python run_all_backtests.py                # all 15 valid leagues
  python run_all_backtests.py premier_league  # just one league (fast dev loop)
"""
import sys
import json
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from lib.loaders import load_football, BAD_FOOTBALL_LEAGUES
from lib.backtest import (
    run_football_model_suite, run_football_market_suite, run_corners_suite,
    calibration_table, build_legs, sweep_odds_band, compute_streaks, go_no_go,
    DEFAULT_PROB_COLS, DEFAULT_ODDS_COLS, OUTCOME_ODDS_COL,
    BTTS_PROB_COLS, BTTS_ODDS_MAP, OU_PROB_COLS, OU_ODDS_MAP, CORNERS_PROB_COLS,
)

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / "results_cache" / "football"
N_FOLDS = 3  # walk-forward folds; kept modest given VPS CPU budget

MARKET_CONFIG = {
    "1x2": {"prob_cols": DEFAULT_PROB_COLS, "odds_cols": DEFAULT_ODDS_COLS,
            "odds_map": OUTCOME_ODDS_COL, "n_classes": 3},
    "btts": {"prob_cols": BTTS_PROB_COLS, "odds_cols": list(BTTS_ODDS_MAP.values()),
             "odds_map": BTTS_ODDS_MAP, "n_classes": 2},
    "over_under_2.5": {"prob_cols": OU_PROB_COLS, "odds_cols": list(OU_ODDS_MAP.values()),
                        "odds_map": OU_ODDS_MAP, "n_classes": 2},
    "corners_9.5": {"prob_cols": CORNERS_PROB_COLS, "odds_cols": ["odds_under_corners", "odds_over_corners"],
                     "odds_map": {0: "odds_under_corners", 1: "odds_over_corners"}, "n_classes": 2},
}


def write_market_result(league, model, market, preds, min_conf=0.60):
    cfg = MARKET_CONFIG[market]
    out_dir = CACHE_DIR / league / model / market
    out_dir.mkdir(parents=True, exist_ok=True)

    preds.to_csv(out_dir / "predictions.csv", index=False)

    cal = calibration_table(preds, prob_cols=cfg["prob_cols"])
    cal.to_json(out_dir / "calibration.json", orient="records")

    legs = build_legs(preds, min_conf=min_conf, prob_cols=cfg["prob_cols"], outcome_odds_map=cfg["odds_map"])
    tier_out = {}
    tier3_tickets = []
    for target in (3, 5, 10):
        best = sweep_odds_band(legs, target)
        if best is None:
            tier_out[str(target)] = {"n_tickets": 0, "win_rate": None, "band": None, "streaks": None}
            continue
        streak = compute_streaks(best["tickets"])
        tier_out[str(target)] = {
            "n_tickets": best["n_tickets"], "win_rate": round(best["win_rate"], 4),
            "band": [best["lo"], best["hi"]], "streaks": streak,
            "tickets": [{"date": str(t["date"]), "n_legs": t["n_legs"],
                         "combined_odds": t["combined_odds"], "won": bool(t["won"])} for t in best["tickets"]],
        }
        if target == 3:
            tier3_tickets = best["tickets"]
    (out_dir / "tickets.json").write_text(json.dumps(tier_out, indent=2))

    verdict = go_no_go(cal, tier3_tickets)
    verdict["n_matches"] = len(preds)
    verdict["n_legs_min_conf"] = len(legs)
    (out_dir / "verdict.json").write_text(json.dumps(verdict, indent=2))
    return verdict


def run_league(league, df_league):
    print(f"\n=== {league} ({len(df_league):,} matches) ===")
    t0 = time.time()
    summary = {}

    try:
        results_1x2 = run_football_model_suite(df_league, n_folds=N_FOLDS)
    except Exception as e:
        print(f"  1x2 suite FAILED: {e}")
        traceback.print_exc()
        results_1x2 = {}
    for model, preds in results_1x2.items():
        if preds.empty:
            continue
        v = write_market_result(league, model, "1x2", preds)
        summary[f"{model}/1x2"] = v
        print(f"  1x2/{model}: n={v['n_matches']} verdict={v['verdict']}")

    try:
        market_results = run_football_market_suite(df_league, n_folds=N_FOLDS)
    except Exception as e:
        print(f"  btts/ou suite FAILED: {e}")
        traceback.print_exc()
        market_results = {}
    for market, model_dict in market_results.items():
        for model, preds in model_dict.items():
            if preds.empty:
                continue
            v = write_market_result(league, model, market, preds)
            summary[f"{model}/{market}"] = v
            print(f"  {market}/{model}: n={v['n_matches']} verdict={v['verdict']}")

    try:
        corner_results = run_corners_suite(df_league, n_folds=N_FOLDS)
    except Exception as e:
        print(f"  corners suite FAILED: {e}")
        corner_results = {}
    for market, model_dict in corner_results.items():
        for model, preds in model_dict.items():
            if preds.empty:
                continue
            v = write_market_result(league, model, market, preds)
            summary[f"{model}/{market}"] = v
            print(f"  {market}/{model}: n={v['n_matches']} verdict={v['verdict']}")

    print(f"  done in {time.time()-t0:.1f}s")
    return summary


def main():
    only_leagues = sys.argv[1:] or None
    df_all = load_football()
    if df_all.empty:
        print("No football data found — run sync_data first.")
        return
    leagues = sorted(df_all["league"].unique())
    if only_leagues:
        leagues = [l for l in leagues if l in only_leagues]
    print(f"Leagues to train: {leagues}")
    print(f"Excluded (bad data): {sorted(BAD_FOOTBALL_LEAGUES)}")

    all_summary = {}
    for league in leagues:
        df_league = df_all[df_all["league"] == league].reset_index(drop=True)
        all_summary[league] = run_league(league, df_league)

    manifest = {
        "leagues_trained": leagues,
        "leagues_excluded": sorted(BAD_FOOTBALL_LEAGUES),
        "markets": list(MARKET_CONFIG.keys()),
        "n_folds": N_FOLDS,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
    }
    (CACHE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("\n=== DONE ===")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
