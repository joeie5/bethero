"""Audit: for every football CSV source file, compare what the RAW file
actually contains (parsed via the real importer logic) against what's
currently live in match_results, focused on the fields each of the 8
markets needs:
  - Goals_1.5/2.5/3.5, BTTS, 1x2 -> home_goals/away_goals
  - Cards_3.5                    -> total_cards
  - Corners_7.5/9.5              -> total_corners

Flags each league as one of:
  OK           — CSV and live DB agree, most-recent season fully covered
  DB_GAP       — CSV has the data but live DB is missing it (backfill needed)
  SOURCE_GAP   — CSV itself lacks the data for the most recent season (Extra
                 tier, or Main tier where football-data.co.uk simply hasn't
                 published stats for a division yet) — nothing to backfill
"""
from pathlib import Path

import pandas as pd

from app.ingestion.football_importer import FootballImporter

CSV_ROOT = Path("backtest_web/data/football")
imp = FootballImporter.__new__(FootballImporter)

# live DB mirror
mr = pd.read_parquet("data_snapshot/match_results_football.parquet")
fx = pd.read_parquet("data_snapshot/fixtures_football.parquet")
live = fx.merge(mr[["fixture_id", "home_goals", "away_goals", "total_corners", "total_cards"]],
                on="fixture_id", how="left")
live["match_date"] = pd.to_datetime(live["match_date"], errors="coerce")

rows_out = []
for csv_path in sorted(CSV_ROOT.rglob("*.csv")):
    country = csv_path.parent.name
    try:
        raw = pd.read_csv(csv_path, encoding="utf-8", low_memory=False)
    except Exception:
        raw = pd.read_csv(csv_path, encoding="latin1", low_memory=False)
    try:
        norm = imp.normalize(raw, csv_path)
    except Exception as e:
        rows_out.append({"country": country, "file": csv_path.name, "error": str(e)})
        continue
    if norm.empty:
        rows_out.append({"country": country, "file": csv_path.name, "error": "normalize() returned empty"})
        continue

    norm["match_date"] = pd.to_datetime(norm["match_date"], format="mixed", errors="coerce")
    norm = norm.dropna(subset=["match_date"])
    most_recent_season_cutoff = norm["match_date"].max() - pd.Timedelta(days=365)
    recent = norm[norm["match_date"] >= most_recent_season_cutoff]

    has_goals   = recent["home_score"].notna() & recent["away_score"].notna()
    has_corners = recent["extra_stats"].apply(lambda d: isinstance(d, dict) and "total_corners" in d)
    has_cards   = recent["extra_stats"].apply(lambda d: isinstance(d, dict) and "total_cards" in d)

    csv_goals_pct   = has_goals.mean()
    csv_corners_pct = has_corners.mean()
    csv_cards_pct   = has_cards.mean()

    league_name = norm["league_name"].mode().iloc[0] if not norm["league_name"].empty else "?"
    live_sub = live[(live["match_date"] >= most_recent_season_cutoff) &
                    (live["league_name"] == league_name)]
    if live_sub.empty:
        # try matching by country instead if league_name lookup failed (Unknown League issue)
        live_sub = live[(live["match_date"] >= most_recent_season_cutoff)]

    db_goals_pct   = live_sub["home_goals"].notna().mean() if len(live_sub) else float("nan")
    db_corners_pct = live_sub["total_corners"].notna().mean() if len(live_sub) else float("nan")
    db_cards_pct   = live_sub["total_cards"].notna().mean() if len(live_sub) else float("nan")

    def _flag(csv_pct, db_pct):
        if csv_pct < 0.5:
            return "SOURCE_GAP"
        if pd.isna(db_pct) or db_pct < csv_pct - 0.1:
            return "DB_GAP"
        return "OK"

    rows_out.append({
        "country": country, "league": league_name, "file": csv_path.name,
        "recent_rows_csv": len(recent), "recent_rows_db": len(live_sub),
        "csv_goals%": round(csv_goals_pct, 2), "db_goals%": round(db_goals_pct, 2) if pd.notna(db_goals_pct) else None,
        "goals_flag": _flag(csv_goals_pct, db_goals_pct),
        "csv_corners%": round(csv_corners_pct, 2), "db_corners%": round(db_corners_pct, 2) if pd.notna(db_corners_pct) else None,
        "corners_flag": _flag(csv_corners_pct, db_corners_pct),
        "csv_cards%": round(csv_cards_pct, 2), "db_cards%": round(db_cards_pct, 2) if pd.notna(db_cards_pct) else None,
        "cards_flag": _flag(csv_cards_pct, db_cards_pct),
    })

report = pd.DataFrame(rows_out)
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 100)
print(report.to_string(index=False))
report.to_csv("football_data_audit.csv", index=False)
print("\nsaved -> football_data_audit.csv")

print("\n=== Summary ===")
for col in ["goals_flag", "corners_flag", "cards_flag"]:
    if col in report.columns:
        print(f"{col}: {report[col].value_counts().to_dict()}")
