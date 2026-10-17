"""
generate_season_predictions.py — Populate the `predictions` table with real
model output for this season's Main-tier fixtures, so the app's real
endpoints (/predictions/match/{id}, accumulators, etc.) have genuine data
to show instead of the Flutter app's hardcoded mock/demo content.

Processes one market at a time across ALL fixtures (not all markets per
fixture) — each market's StackingEnsemble base models (RandomForest alone
can be 700MB-2.2GB per market) get cached in-process once loaded, and
holding every market's ensemble in memory simultaneously exceeds available
RAM (confirmed: "could not allocate N bytes" failures loading RandomForest
when multiple markets' ensembles were resident at once). Clearing the
model cache between markets keeps peak memory to roughly one market's
model set at a time.

Usage:
    PYTHONPATH=. python3 scripts/generate_season_predictions.py
    PYTHONPATH=. python3 scripts/generate_season_predictions.py --limit 500
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_TIER_LEAGUES = [
    "E0", "E1", "E2", "E3", "EC",
    "SC0", "SC1", "SC2", "SC3",
    "D1", "D2", "SP1", "SP2", "I1", "I2", "F1", "F2",
    "N1", "B1", "P1", "T1", "G1",
]
MARKETS = ["BTTS", "Cards", "Corners", "Goals", "1x2"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                         help="Cap number of fixtures processed (default: all)")
    parser.add_argument("--season", type=int, default=2025)
    args = parser.parse_args()

    from app.database import get_supabase_admin
    from app.ml.predictor import Predictor, _ModelCache

    df = pd.read_parquet(REPO_ROOT / "data_snapshot" / "fixtures_football.parquet")
    season = df[
        (df["season"] == args.season)
        & (df["league_key"].isin(MAIN_TIER_LEAGUES))
        & (df["status"] == "FT")
    ].sort_values("match_date")

    if args.limit:
        season = season.head(args.limit)

    fixture_ids = season["fixture_id"].tolist()
    print(f"Fixtures to predict: {len(fixture_ids)}", flush=True)

    client = get_supabase_admin()
    predictor = Predictor(client, data_dir=str(REPO_ROOT / "data_snapshot"))

    grand_t0 = time.monotonic()
    for market in MARKETS:
        t0 = time.monotonic()
        ok = 0
        failed = 0
        for i, fid in enumerate(fixture_ids):
            try:
                predictor.predict_match("football", fid, markets=[market], persist=True)
                ok += 1
            except Exception as exc:
                failed += 1
                if failed <= 5:
                    print(f"  [{market}] {fid} failed: {exc}", flush=True)
            if (i + 1) % 500 == 0:
                print(f"  [{market}] {i+1}/{len(fixture_ids)} "
                      f"({time.monotonic()-t0:.0f}s elapsed)", flush=True)

        print(f"{market}: {ok} ok, {failed} failed ({time.monotonic()-t0:.1f}s)", flush=True)

        # Free this market's (possibly multi-GB) base models before the next
        # market loads its own — see module docstring.
        _ModelCache._store.clear()

    print(f"\n=== ALL MARKETS DONE ({(time.monotonic()-grand_t0)/60:.1f} min total) ===", flush=True)


if __name__ == "__main__":
    main()
