"""
football_importer.py — Imports historical football data from
work/backtest_web/data/football/<country>/<league>.csv (football-data.co.uk
Main-tier and Extra-tier exports — see CLAUDE.md §5).

Tier detection (per file, not per country — some countries only have one)
---------------------------------------------------------------------------
Main tier  : has HC/AC/HY/AY/HR/AR/HS/AS/HST/AST — full post-match stats,
             supports all four §2 markets (BTTS, Goals, Corners, Cards).
Extra tier : only HG/AG/Res — supports BTTS/Goals only (both derivable from
             goals alone); Corners/Cards stay null, never fabricated.

Column reference
-----------------
Main tier : Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,Referee,
            HS,AS,HST,AST,HC,AC,HY,AY,HR,AR, + many bookmaker odds columns
            (B365H/D/A, PSH/D/A, PSCH/D/A, AvgH/D/A, MaxH/D/A,
             B365>2.5/B365<2.5, Avg>2.5/Avg<2.5, ...)
Extra tier: Country,League,Season,Date,Time,Home,Away,HG,AG,Res, +
            closing-odds-only columns (PSCH/D/A, MaxCH/D/A, AvgCH/D/A,
             BFECH/D/A, B365CH/D/A) — no opening odds, no O/U lines.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from app.ingestion.base_importer import BaseImporter

logger = logging.getLogger(__name__)


# ── League name map: Football-Data.co.uk division codes → readable names ──
DIVISION_MAP: dict[str, tuple[str, str]] = {
    "E0":  ("Premier League",        "England"),
    "E1":  ("Championship",          "England"),
    "E2":  ("League One",            "England"),
    "E3":  ("League Two",            "England"),
    "EC":  ("National League",       "England"),
    "SC0": ("Scottish Premiership",  "Scotland"),
    "SC1": ("Scottish Championship", "Scotland"),
    "SC2": ("Scottish League One",   "Scotland"),
    "SC3": ("Scottish League Two",   "Scotland"),
    "D1":  ("Bundesliga",            "Germany"),
    "D2":  ("2. Bundesliga",         "Germany"),
    "SP1": ("La Liga",               "Spain"),
    "SP2": ("La Liga 2",             "Spain"),
    "I1":  ("Serie A",               "Italy"),
    "I2":  ("Serie B",               "Italy"),
    "F1":  ("Ligue 1",               "France"),
    "F2":  ("Ligue 2",               "France"),
    "N1":  ("Eredivisie",            "Netherlands"),
    "B1":  ("First Division A",      "Belgium"),
    "P1":  ("Primeira Liga",         "Portugal"),
    "T1":  ("Süper Lig",             "Turkey"),
    "G1":  ("Super League",          "Greece"),
}

FOOTBALL_ALIASES: dict[str, str] = {
    "man utd": "manchester united", "man united": "manchester united",
    "man city": "manchester city", "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur", "wolves": "wolverhampton wanderers",
    "brighton": "brighton & hove albion", "sheffield utd": "sheffield united",
    "nottm forest": "nottingham forest", "qpr": "queens park rangers",
    "west brom": "west bromwich albion", "newcastle": "newcastle united",
    "leicester": "leicester city", "norwich": "norwich city",
    "west ham": "west ham united", "atletico": "atletico madrid",
    "real": "real madrid", "barca": "barcelona", "inter": "inter milan",
    "ac milan": "milan", "psv": "psv eindhoven", "ajax": "ajax amsterdam",
    "dortmund": "borussia dortmund", "bvb": "borussia dortmund",
    "leverkusen": "bayer leverkusen",
}

MAIN_TIER_MARKERS = {"hc", "ac", "hy", "ay", "hr", "ar", "hs", "as", "hst", "ast"}

# (bookmaker_label, home_col, draw_col, away_col) cascades, most preferred first
MAIN_1X2_CASCADE = [
    ("Pinnacle", "psh", "psd", "psa"),
    ("Bet365",   "b365h", "b365d", "b365a"),
    ("Average",  "avgh", "avgd", "avga"),
]
MAIN_OU25_CASCADE = [
    ("Bet365",  "b365>2.5", "b365<2.5"),
    ("Average", "avg>2.5",  "avg<2.5"),
]
EXTRA_1X2_CASCADE = [
    ("Pinnacle", "psch", "pscd", "psca"),
    ("Average",  "avgch", "avgcd", "avgca"),
    ("Bet365",   "b365ch", "b365cd", "b365ca"),
]


class FootballImporter(BaseImporter):

    sport_slug = "football"

    def load_aliases(self) -> dict[str, str]:
        return FOOTBALL_ALIASES

    def normalize(self, df: pd.DataFrame, source_file: Path) -> pd.DataFrame:
        df = self._clean_df(df)
        df.columns = [c.lower().strip() for c in df.columns]
        cols = set(df.columns)

        if "hometeam" in cols and "awayteam" in cols:
            return self._normalize_main_tier(df)
        elif "home" in cols and "away" in cols:
            return self._normalize_extra_tier(df)
        else:
            logger.warning("Unrecognised football file format: %s (%s)", source_file, sorted(cols)[:15])
            return pd.DataFrame()

    # ── Main tier (football-data.co.uk primary league pages) ─────

    def _normalize_main_tier(self, df: pd.DataFrame) -> pd.DataFrame:
        is_main = bool(MAIN_TIER_MARKERS & set(df.columns))
        rows = []
        for _, r in df.iterrows():
            date_val = r.get("date")
            if not date_val or pd.isna(date_val):
                continue
            parsed = self._parse_date(str(date_val))
            div_raw = r.get("div")
            div = "" if div_raw is None or pd.isna(div_raw) else str(div_raw).strip()
            league_name, country = DIVISION_MAP.get(div, ("Unknown League", ""))

            fthg, ftag = self._safe_int(r.get("fthg")), self._safe_int(r.get("ftag"))
            extra_stats: dict = {}
            odds: list[dict] = []

            if is_main and fthg is not None and ftag is not None:
                hc, ac = self._safe_int(r.get("hc")), self._safe_int(r.get("ac"))
                hy, ay = self._safe_int(r.get("hy")), self._safe_int(r.get("ay"))
                hr, ar = self._safe_int(r.get("hr")), self._safe_int(r.get("ar"))
                hst, ast = self._safe_int(r.get("hst")), self._safe_int(r.get("ast"))
                hthg, htag = self._safe_int(r.get("hthg")), self._safe_int(r.get("htag"))

                if hc is not None and ac is not None:
                    extra_stats["home_corners"] = hc
                    extra_stats["away_corners"] = ac
                    extra_stats["total_corners"] = hc + ac
                if hy is not None and ay is not None and hr is not None and ar is not None:
                    extra_stats["total_yellow"] = hy + ay
                    extra_stats["total_red"] = hr + ar
                    extra_stats["total_cards"] = hy + ay + hr + ar
                if hst is not None and ast is not None:
                    extra_stats["home_sot"] = hst
                    extra_stats["away_sot"] = ast
                    extra_stats["total_sot"] = hst + ast
                if hthg is not None and htag is not None:
                    extra_stats["ht_home_goals"] = hthg
                    extra_stats["ht_away_goals"] = htag
                    extra_stats["htr"] = "H" if hthg > htag else ("A" if htag > hthg else "D")

                odds = self._extract_main_odds(r)

            rows.append({
                "home_team_name": str(r.get("hometeam", "")),
                "away_team_name": str(r.get("awayteam", "")),
                "match_date":     str(date_val),
                "league_key":     div or "unknown",
                "league_name":    league_name,
                "country":        country,
                "season":         self._season_from_date(parsed),
                "home_score":     fthg,
                "away_score":     ftag,
                "status":         "FT",
                "extra_stats":    extra_stats,
                "odds":           odds,
            })
        return pd.DataFrame(rows)

    def _extract_main_odds(self, r: pd.Series) -> list[dict]:
        odds = []
        for bookmaker, hcol, dcol, acol in MAIN_1X2_CASCADE:
            h, d, a = self._safe_float(r.get(hcol)), self._safe_float(r.get(dcol)), self._safe_float(r.get(acol))
            if h and d and a:
                odds.append({
                    "bookmaker": bookmaker, "market": "1X2",
                    "home_odds": h, "draw_odds": d, "away_odds": a,
                })
                break
        for bookmaker, ocol, ucol in MAIN_OU25_CASCADE:
            o, u = self._safe_float(r.get(ocol)), self._safe_float(r.get(ucol))
            if o and u:
                odds.append({
                    "bookmaker": bookmaker, "market": "Over_Under_Goals", "line": 2.5,
                    "over_odds": o, "under_odds": u,
                })
                break
        return odds

    # ── Extra tier (football-data.co.uk combined "extra leagues" files) ──

    def _normalize_extra_tier(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for _, r in df.iterrows():
            date_val = r.get("date")
            if not date_val or pd.isna(date_val):
                continue
            parsed = self._parse_date(str(date_val))
            hg, ag = self._safe_int(r.get("hg")), self._safe_int(r.get("ag"))

            odds: list[dict] = []
            for bookmaker, hcol, dcol, acol in EXTRA_1X2_CASCADE:
                h, d, a = self._safe_float(r.get(hcol)), self._safe_float(r.get(dcol)), self._safe_float(r.get(acol))
                if h and d and a:
                    odds.append({
                        "bookmaker": bookmaker, "market": "1X2",
                        "home_odds": h, "draw_odds": d, "away_odds": a,
                    })
                    break

            season_raw = str(r.get("season", "") or "")
            season_match = re.match(r"(\d{4})", season_raw)
            season = int(season_match.group(1)) if season_match else self._season_from_date(parsed)

            rows.append({
                "home_team_name": str(r.get("home", "")),
                "away_team_name": str(r.get("away", "")),
                "match_date":     str(date_val),
                "league_key":     str(r.get("league", "unknown")).strip() or "unknown",
                "league_name":    str(r.get("league", "Unknown")).strip() or "Unknown",
                "country":        str(r.get("country", "")).strip(),
                "season":         season,
                "home_score":     hg,
                "away_score":     ag,
                "status":         "FT",
                "extra_stats":    {},   # no corners/cards in Extra tier — never fabricated
                "odds":           odds,
            })
        return pd.DataFrame(rows)

    # ── Utility ────────────────────────────────────────────────

    @staticmethod
    def _season_from_date(dt) -> int | None:
        """Football season label = year the season started (Aug-Jul cycle)."""
        if dt is None:
            return None
        return dt.year if dt.month >= 7 else dt.year - 1
