"""Sport-specific parsers -> a common tidy match-level dataframe.

Common schema for team-sports (football/nba/nfl/mlb):
  date, league, home, away, home_score, away_score, result (H/D/A or H/A),
  odds_home, odds_draw, odds_away (NaN if not available)

Tennis common schema:
  date, tourney, surface, winner, loser, winner_rank, loser_rank, best_of
"""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# NOTE: ligue_2 and belgium_pro_league were previously ~250-row files with
# future-dated (2026) synthetic-looking rows. Both were re-pulled with full
# real historical data from football-data.co.uk this session (11,316 and
# 8,706 rows respectively) -- no longer excluded. Kept as an empty set (not
# deleted) since run_all_backtests.py imports it for exclusion reporting.
BAD_FOOTBALL_LEAGUES = set()

# football/ is organized as football/{country}/{league}.csv in Storage and
# locally (e.g. football/england/premier_league.csv) -- search recursively.


def load_football(exclude_bad=True) -> pd.DataFrame:
    frames = []
    folder = DATA_DIR / "football"
    if not folder.exists():
        return pd.DataFrame()
    for f in folder.rglob("*.csv"):
        try:
            df = pd.read_csv(f, encoding="latin1", low_memory=False)
        except Exception:
            continue

        is_extra_schema = "Home" in df.columns and "HomeTeam" not in df.columns

        if is_extra_schema:
            # "Extra leagues" combined-file schema from football-data.co.uk/new/*.csv
            if not {"Home", "Away", "HG", "AG"}.issubset(df.columns):
                continue
            df = df.rename(columns={
                "Home": "home", "Away": "away",
                "HG": "home_score", "AG": "away_score", "Res": "result",
            })
            df["league"] = f.stem
            df["date"] = pd.to_datetime(df.get("Date"), dayfirst=True, errors="coerce")
            # Prefer Pinnacle closing odds (PSCH/PSCD/PSCA); fall back to Bet365 closing (B365CH/CD/CA)
            for psc, b365, new in [
                ("PSCH", "B365CH", "odds_home"),
                ("PSCD", "B365CD", "odds_draw"),
                ("PSCA", "B365CA", "odds_away"),
            ]:
                psc_v = pd.to_numeric(df[psc], errors="coerce") if psc in df.columns else pd.Series(np.nan, index=df.index)
                b365_v = pd.to_numeric(df[b365], errors="coerce") if b365 in df.columns else pd.Series(np.nan, index=df.index)
                df[new] = psc_v.fillna(b365_v)
            df["odds_over25"] = np.nan
            df["odds_under25"] = np.nan
            df["home_corners"] = np.nan
            df["away_corners"] = np.nan
        else:
            if not {"HomeTeam", "AwayTeam", "FTHG", "FTAG"}.issubset(df.columns):
                continue
            df = df.rename(columns={
                "HomeTeam": "home", "AwayTeam": "away",
                "FTHG": "home_score", "FTAG": "away_score", "FTR": "result",
                "HC": "home_corners", "AC": "away_corners",
            })
            df["league"] = f.stem
            df["date"] = pd.to_datetime(df.get("Date"), dayfirst=True, errors="coerce")
            for col, new in [("B365H", "odds_home"), ("B365D", "odds_draw"), ("B365A", "odds_away")]:
                df[new] = pd.to_numeric(df[col], errors="coerce") if col in df.columns else np.nan
            # Over/Under 2.5 goals odds: prefer B365, fall back to Gamebookers (GB)
            for src_over, src_under in [("B365>2.5", "B365<2.5"), ("GB>2.5", "GB<2.5")]:
                if src_over in df.columns and "odds_over25" not in df.columns:
                    df["odds_over25"] = pd.to_numeric(df[src_over], errors="coerce")
                    df["odds_under25"] = pd.to_numeric(df[src_under], errors="coerce")
            if "odds_over25" not in df.columns:
                df["odds_over25"] = np.nan
                df["odds_under25"] = np.nan
            if "home_corners" not in df.columns:
                df["home_corners"] = np.nan
            if "away_corners" not in df.columns:
                df["away_corners"] = np.nan
        keep = ["date", "league", "home", "away", "home_score", "away_score", "result",
                "odds_home", "odds_draw", "odds_away", "odds_over25", "odds_under25",
                "home_corners", "away_corners"]
        df = df[keep].dropna(subset=["date", "home", "away", "home_score", "away_score"])
        df["home_score"] = pd.to_numeric(df["home_score"], errors="coerce")
        df["away_score"] = pd.to_numeric(df["away_score"], errors="coerce")
        df["home_corners"] = pd.to_numeric(df["home_corners"], errors="coerce")
        df["away_corners"] = pd.to_numeric(df["away_corners"], errors="coerce")
        df = df.dropna(subset=["home_score", "away_score"])
        computed = pd.Series(
            np.where(df["home_score"] > df["away_score"], "H",
            np.where(df["home_score"] < df["away_score"], "A", "D")),
            index=df.index)
        df["result"] = df["result"].fillna(computed)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).sort_values("date")
    return out


def load_team_sport_generic(sport: str) -> pd.DataFrame:
    """For nba/nfl/mlb all_games.csv — column names verified empirically at
    ingestion time (see sync report); this normalizes whatever is found to
    the common schema on a best-effort basis."""
    f = DATA_DIR / sport / "all_games.csv"
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_csv(f, low_memory=False)
    return df  # raw — normalized downstream per-sport once columns are confirmed


def load_tennis(tour: str) -> pd.DataFrame:
    folder = DATA_DIR / f"tennis_{tour}"
    if not folder.exists():
        return pd.DataFrame()
    frames = []
    for f in folder.glob("*matches_[12][0-9][0-9][0-9].csv"):
        try:
            df = pd.read_csv(f, low_memory=False)
        except Exception:
            continue
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
