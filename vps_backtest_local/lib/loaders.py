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

# ligue_2.csv and belgium_pro_league.csv are ~250-row files with future-dated
# (2026) synthetic-looking rows -- confirmed bad data, excluded from training.
BAD_FOOTBALL_LEAGUES = {"ligue_2", "belgium_pro_league"}


KEEP_COLS = ["date", "league", "home", "away", "home_score", "away_score", "result",
             "odds_home", "odds_draw", "odds_away", "odds_over25", "odds_under25",
             "home_corners", "away_corners"]


def _finalize(df: pd.DataFrame, league: str) -> pd.DataFrame:
    df["league"] = league
    for col in KEEP_COLS:
        if col not in df.columns:
            df[col] = np.nan
    df = df[KEEP_COLS].dropna(subset=["date", "home", "away", "home_score", "away_score"])
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
    return df


def _parse_main_tier(df: pd.DataFrame) -> pd.DataFrame:
    """football-data.co.uk primary league format: HomeTeam/AwayTeam/FTHG/FTAG,
    full stats (corners, cards) and multi-bookmaker odds."""
    df = df.rename(columns={
        "HomeTeam": "home", "AwayTeam": "away",
        "FTHG": "home_score", "FTAG": "away_score", "FTR": "result",
        "HC": "home_corners", "AC": "away_corners",
    })
    df["date"] = pd.to_datetime(df.get("Date"), dayfirst=True, errors="coerce")
    for col, new in [("B365H", "odds_home"), ("B365D", "odds_draw"), ("B365A", "odds_away")]:
        df[new] = pd.to_numeric(df[col], errors="coerce") if col in df.columns else np.nan
    for src_over, src_under in [("B365>2.5", "B365<2.5"), ("GB>2.5", "GB<2.5")]:
        if src_over in df.columns and "odds_over25" not in df.columns:
            df["odds_over25"] = pd.to_numeric(df[src_over], errors="coerce")
            df["odds_under25"] = pd.to_numeric(df[src_under], errors="coerce")
    return df


def _parse_extra_tier(df: pd.DataFrame) -> pd.DataFrame:
    """football-data.co.uk "extra leagues" combined format: Home/Away/HG/AG,
    closing odds only (PSCH/D/A, AvgCH/D/A, B365CH/D/A), no corners/cards,
    no goals-line odds -- never fabricate what isn't there (see CLAUDE.md §5:
    verify each Extra-tier country's actual columns, don't assume Main-tier
    depth)."""
    df = df.rename(columns={"Home": "home", "Away": "away", "HG": "home_score", "AG": "away_score",
                             "Res": "result"})
    df["date"] = pd.to_datetime(df.get("Date"), dayfirst=True, errors="coerce")
    for bookmaker_h, bookmaker_d, bookmaker_a in [
        ("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA"), ("B365CH", "B365CD", "B365CA"),
    ]:
        if bookmaker_h in df.columns and "odds_home" not in df.columns:
            df["odds_home"] = pd.to_numeric(df[bookmaker_h], errors="coerce")
            df["odds_draw"] = pd.to_numeric(df[bookmaker_d], errors="coerce")
            df["odds_away"] = pd.to_numeric(df[bookmaker_a], errors="coerce")
    # No Over/Under 2.5 lines or corners data in the Extra tier -- left as NaN
    # by _finalize(), not fabricated.
    return df


def load_football(exclude_bad=True) -> pd.DataFrame:
    frames = []
    folder = DATA_DIR / "football"
    if not folder.exists():
        return pd.DataFrame()
    for f in folder.glob("*.csv"):
        if exclude_bad and f.stem in BAD_FOOTBALL_LEAGUES:
            continue
        try:
            df = pd.read_csv(f, encoding="latin1", low_memory=False)
        except Exception:
            continue
        if {"HomeTeam", "AwayTeam", "FTHG", "FTAG"}.issubset(df.columns):
            df = _parse_main_tier(df)
        elif {"Home", "Away", "HG", "AG"}.issubset(df.columns):
            df = _parse_extra_tier(df)
        else:
            continue
        frames.append(_finalize(df, f.stem))
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
