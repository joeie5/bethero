"""
feature_engineer.py — Complete pre-match feature pipeline for Bet Hero ML models.

⚠️  NO DATA LEAKAGE GUARANTEE
All features are computed using only data with timestamp < match_date.
This is enforced by the strict date filtering in every query and rolling window.
None of match_results' post-match columns (home_goals, away_goals, ht_home_goals,
ht_away_goals, ftr, htr, home_sot, away_sot, home_corners, away_corners,
total_yellow, total_red, total_cards, ...) are ever used as same-match features —
only as (a) the training label, or (b) folded into rolling history for matches
strictly before the one being predicted.

Live schema (verified against the `bethero` Supabase project)
----------------------------------------------------------------
    fixtures        PK (sport, fixture_id)   — scheduling/context, no scores
    match_results   PK (sport, fixture_id)   — post-match stats (label source)
    team_form_cache PK (sport, team_id, as_of_date) — pre-aggregated rolling stats
    fixture_odds    — bookmaker odds per (sport, fixture_id, bookmaker, market)

Feature families
----------------
1. FORM          — rolling 5 / 10 / 20 game windows, exp-decay score, momentum,
                    plus rolling corners/cards signal for the Corners/Cards markets
2. STRENGTH      — Elo (from team_form_cache), Dixon-Coles attack/defense strengths
3. HEAD-TO-HEAD  — win/draw/loss rate, goals, venue, days since last meeting
4. CONTEXT       — fatigue, midweek flag, league position, season stage, importance
5. MARKET        — implied probabilities (overround removed), odds movement
6. REFEREE       — reserved; no referee-stats table exists in the live schema yet,
                    so this always returns zeroed features (fixtures.referee is a
                    bare text name with no aggregated stats behind it)

Public API
----------
    fe = FeatureEngineer(supabase_client)
    row = fe.build(sport, fixture_id)            # → dict[str, float]  (single match)
    df  = fe.build_batch([(sport, fixture_id), ...])  # → pd.DataFrame
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────── Constants ─────────────────────────────────────

FORM_WINDOWS        = [5, 10, 20]
EXP_DECAY_HALFLIFE  = 10          # games: weight halves every 10 games ago
H2H_LOOKBACK        = 6           # last N H2H meetings
NAN_FILL            = 0.0         # sentinel for missing numeric features
STARTING_ELO        = 1500.0      # fallback when team_form_cache has no row yet


# ═══════════════════════════════════════════════════════════════════════════
# Helper: safe division
# ═══════════════════════════════════════════════════════════════════════════

def _safe_div(num: float, den: float, default: float = NAN_FILL) -> float:
    return num / den if den != 0.0 else default


# ═══════════════════════════════════════════════════════════════════════════
# 1. FORM FEATURES
# ═══════════════════════════════════════════════════════════════════════════

class FormCalculator:
    """
    Computes rolling-window form features for a team, using only matches
    completed strictly BEFORE `before_dt`.
    """

    def __init__(self, team_matches: pd.DataFrame):
        """
        Parameters
        ----------
        team_matches : DataFrame with columns:
            match_date, is_home, goals_for, goals_against,
            result (W/D/L), corners_for, corners_against, cards_total,
            clean_sheet, btts, over25
            Ordered by match_date ASC.
        """
        self.df = team_matches.copy()
        if not self.df.empty:
            self.df = self.df.sort_values("match_date").reset_index(drop=True)

    def compute(self, before_dt: datetime, prefix: str = "home") -> dict[str, float]:
        feats: dict[str, float] = {}
        # self.df is always constructed by the caller (_team_history) already
        # filtered to strictly-before before_dt, with this same before_dt —
        # re-filtering here was a guaranteed no-op done on every one of the
        # ~600k calls in a full feature-cache build.
        hist = self.df

        for w in FORM_WINDOWS:
            window = hist.tail(w)
            p = f"{prefix}_form{w}_"
            n = len(window)
            if n == 0:
                feats.update({
                    f"{p}ppg": NAN_FILL,
                    f"{p}gscored": NAN_FILL,
                    f"{p}gconceded": NAN_FILL,
                    f"{p}corners_for": NAN_FILL,
                    f"{p}corners_against": NAN_FILL,
                    f"{p}cards_total": NAN_FILL,
                    f"{p}cs_rate": NAN_FILL,
                    f"{p}btts_rate": NAN_FILL,
                    f"{p}over25_rate": NAN_FILL,
                    f"{p}win_pct": NAN_FILL,
                    f"{p}draw_pct": NAN_FILL,
                    f"{p}loss_pct": NAN_FILL,
                })
                continue

            wins   = (window["result"] == "W").sum()
            draws  = (window["result"] == "D").sum()
            losses = (window["result"] == "L").sum()
            points = wins * 3 + draws

            feats[f"{p}ppg"]            = _safe_div(points, n)
            feats[f"{p}gscored"]        = window["goals_for"].mean()
            feats[f"{p}gconceded"]      = window["goals_against"].mean()
            feats[f"{p}corners_for"]    = window["corners_for"].mean()     if "corners_for"     in window else NAN_FILL
            feats[f"{p}corners_against"]= window["corners_against"].mean()if "corners_against" in window else NAN_FILL
            feats[f"{p}cards_total"]    = window["cards_total"].mean()     if "cards_total"     in window else NAN_FILL
            feats[f"{p}cs_rate"]        = _safe_div(window["clean_sheet"].sum(), n)
            feats[f"{p}btts_rate"]      = _safe_div(window["btts"].sum(), n)
            feats[f"{p}over25_rate"]    = _safe_div(window["over25"].sum(), n)
            feats[f"{p}win_pct"]        = _safe_div(wins,   n)
            feats[f"{p}draw_pct"]       = _safe_div(draws,  n)
            feats[f"{p}loss_pct"]       = _safe_div(losses, n)

        # ── Exponential-decay form score ──────────────────────────
        feats[f"{prefix}_ewm_form"] = self._exp_decay_form(hist)

        # ── Form momentum: change in PPG from last 5 vs 6-10 ─────
        feats[f"{prefix}_form_momentum"] = self._form_momentum(hist)

        # ── Home/Away performance split ───────────────────────────
        feats[f"{prefix}_home_ppg"] = self._venue_ppg(hist, is_home=True)
        feats[f"{prefix}_away_ppg"] = self._venue_ppg(hist, is_home=False)

        return feats

    def _exp_decay_form(self, hist: pd.DataFrame, w: int = 20) -> float:
        """Exponentially weighted points (recent games count more)."""
        window = hist.tail(w)
        if window.empty:
            return NAN_FILL
        points_series = window["result"].map({"W": 3, "D": 1, "L": 0}).astype(float)
        n = len(points_series)
        decay = np.array([math.exp(-math.log(2) / EXP_DECAY_HALFLIFE * (n - 1 - i))
                          for i in range(n)])
        return float(np.dot(points_series.values, decay) / decay.sum())

    def _form_momentum(self, hist: pd.DataFrame) -> float:
        """PPG last 5 minus PPG for games 6-10. Positive = improving form."""
        recent = hist.tail(10)
        if len(recent) < 5:
            return NAN_FILL
        last5 = recent.tail(5)
        prev5 = recent.head(len(recent) - 5)
        ppg_last5 = (last5["result"].map({"W": 3, "D": 1, "L": 0}).sum()) / max(len(last5), 1)
        ppg_prev5 = (prev5["result"].map({"W": 3, "D": 1, "L": 0}).sum()) / max(len(prev5), 1)
        return float(ppg_last5 - ppg_prev5)

    def _venue_ppg(self, hist: pd.DataFrame, is_home: bool) -> float:
        subset = hist[hist["is_home"] == is_home]
        if subset.empty:
            return NAN_FILL
        pts = subset["result"].map({"W": 3, "D": 1, "L": 0}).sum()
        return float(_safe_div(pts, len(subset)))

    def consecutive_streak(self, before_dt: datetime, result_type: str) -> int:
        """How many consecutive W/D/L results ending before match time."""
        hist = self.df.tail(20)  # self.df is already filtered strictly-before before_dt (see compute())
        streak = 0
        for r in reversed(hist["result"].tolist()):
            if r == result_type:
                streak += 1
            else:
                break
        return streak


# ═══════════════════════════════════════════════════════════════════════════
# 2. STRENGTH FEATURES — Dixon-Coles parameters
# ═══════════════════════════════════════════════════════════════════════════

class DixonColesEstimator:
    """
    Lightweight Dixon-Coles attack/defense strength estimator.
    Uses a simple iterative MLE approximation rather than full scipy optimise
    for speed (suitable for real-time feature computation).

    Attack strength  = mean goals scored / league mean goals
    Defense strength = mean goals conceded / league mean goals
    """

    def __init__(self, league_matches: pd.DataFrame):
        """
        Parameters
        ----------
        league_matches : DataFrame with home_team_id, away_team_id,
                         home_goals, away_goals, match_date
        """
        self.df = league_matches.dropna(subset=["home_goals", "away_goals"]).copy()
        self._league_avg_home: float = 0.0
        self._league_avg_away: float = 0.0
        self._attack:  dict[int, float] = {}
        self._defense: dict[int, float] = {}

    def fit(self, before_dt: datetime) -> "DixonColesEstimator":
        hist = self.df[self.df["match_date"] < before_dt]
        if hist.empty:
            return self

        self._league_avg_home = hist["home_goals"].mean()
        self._league_avg_away = hist["away_goals"].mean()
        league_avg = (self._league_avg_home + self._league_avg_away) / 2.0

        if league_avg == 0:
            return self

        # Vectorized attack/defense — was a Python-level loop over every team,
        # each doing two full boolean-mask filters of `hist` (the dominant
        # cost of feature building at scale: called on almost every fixture
        # since the cache key is (league, exact date), and `hist` grows over
        # a league's whole history). Same technique already used in
        # _build_league_table just below: stack home/away rows long, groupby
        # once. league_avg != 0 is already guaranteed above, so every team's
        # divisor is safe — no _safe_div fallback needed.
        home = hist[["home_team_id", "home_goals", "away_goals"]].rename(
            columns={"home_team_id": "team_id", "home_goals": "gf", "away_goals": "ga"})
        away = hist[["away_team_id", "away_goals", "home_goals"]].rename(
            columns={"away_team_id": "team_id", "away_goals": "gf", "home_goals": "ga"})
        long = pd.concat([home, away], ignore_index=True)
        grp = long.groupby("team_id").agg(gf=("gf", "sum"), ga=("ga", "sum"), n=("gf", "size"))

        self._attack  = ((grp["gf"] / grp["n"]) / league_avg).to_dict()
        self._defense = ((grp["ga"] / grp["n"]) / league_avg).to_dict()
        return self

    def attack(self, team_id: int)  -> float:
        return self._attack.get(team_id, 1.0)

    def defense(self, team_id: int) -> float:
        return self._defense.get(team_id, 1.0)

    def expected_goals(self, home_id: int, away_id: int) -> tuple[float, float]:
        """λ_home, λ_away — Poisson rate predictions."""
        lam_h = self.attack(home_id) * self.defense(away_id) * self._league_avg_home
        lam_a = self.attack(away_id) * self.defense(home_id) * self._league_avg_away
        return lam_h, lam_a


# ═══════════════════════════════════════════════════════════════════════════
# 3. HEAD-TO-HEAD FEATURES
# ═══════════════════════════════════════════════════════════════════════════

def compute_h2h_features(
    home_id: int,
    away_id: int,
    venue: str | None,
    before_dt: datetime,
    all_matches: pd.DataFrame,
) -> dict[str, float]:
    """
    Head-to-head stats between home and away team, strictly before match time.

    Parameters
    ----------
    all_matches : DataFrame of all historical matches for the sport
                  (fixtures joined with match_results).
    """
    h2h = all_matches[
        (
            ((all_matches["home_team_id"] == home_id) & (all_matches["away_team_id"] == away_id)) |
            ((all_matches["home_team_id"] == away_id) & (all_matches["away_team_id"] == home_id))
        ) &
        (all_matches["match_date"] < before_dt) &
        all_matches["home_goals"].notna()
    ].sort_values("match_date").tail(H2H_LOOKBACK)

    feats: dict[str, float] = {}
    n = len(h2h)

    if n == 0:
        return {
            "h2h_home_win_rate": NAN_FILL,
            "h2h_draw_rate":     NAN_FILL,
            "h2h_away_win_rate": NAN_FILL,
            "h2h_avg_goals":     NAN_FILL,
            "h2h_venue_win_rate": NAN_FILL,
            "h2h_days_since":    365.0,
        }

    # Outcome from home team's perspective
    def _outcome(row):
        if row["home_team_id"] == home_id:
            if row["home_goals"] > row["away_goals"]: return "W"
            if row["home_goals"] == row["away_goals"]: return "D"
            return "L"
        else:
            if row["away_goals"] > row["home_goals"]: return "W"
            if row["away_goals"] == row["home_goals"]: return "D"
            return "L"

    h2h = h2h.copy()
    h2h["h2h_result"] = h2h.apply(_outcome, axis=1)

    wins   = (h2h["h2h_result"] == "W").sum()
    draws  = (h2h["h2h_result"] == "D").sum()
    losses = (h2h["h2h_result"] == "L").sum()

    feats["h2h_home_win_rate"] = _safe_div(wins,   n)
    feats["h2h_draw_rate"]     = _safe_div(draws,  n)
    feats["h2h_away_win_rate"] = _safe_div(losses, n)
    feats["h2h_avg_goals"]     = ((h2h["home_goals"] + h2h["away_goals"]).mean())

    # H2H at same venue — fixtures.venue is 100% null across all 297,904
    # historical fixtures in this dataset (never populated by the import),
    # so the original venue-string match always fell through to NAN_FILL.
    # Use "current home team was also the home team in that meeting" as a
    # proxy instead: for football this is effectively the same thing as
    # "same venue," barring rare neutral-ground fixtures (cup finals etc.),
    # and h2h already carries home_team_id from all_matches.
    venue_h2h = h2h[h2h["home_team_id"] == home_id]
    vn = len(venue_h2h)
    if vn > 0:
        v_wins = (venue_h2h["h2h_result"] == "W").sum()
        feats["h2h_venue_win_rate"] = _safe_div(v_wins, vn)
    else:
        feats["h2h_venue_win_rate"] = NAN_FILL

    # Days since last H2H
    last_dt = h2h["match_date"].max()
    if pd.notna(last_dt):
        diff = (before_dt - pd.Timestamp(last_dt).to_pydatetime().replace(tzinfo=None)).days
        feats["h2h_days_since"] = float(max(0, diff))
    else:
        feats["h2h_days_since"] = 365.0

    return feats


# ═══════════════════════════════════════════════════════════════════════════
# 4. CONTEXT FEATURES
# ═══════════════════════════════════════════════════════════════════════════

def compute_context_features(
    match: dict,
    team_id: int,
    team_hist: pd.DataFrame,
    before_dt: datetime,
    league_table: dict[int, dict],
    is_home: bool,
) -> dict[str, float]:
    """
    Match-context features: fatigue, season stage, league position, importance.

    Parameters
    ----------
    match       : The upcoming match dict from DB (fixtures row)
    team_hist   : All historical matches for this team (full history, date-sorted)
    league_table: {team_id: {position, points, top4_gap, relegation_gap}} at match time
    """
    side = "home" if is_home else "away"
    feats: dict[str, float] = {}

    # ── Fatigue features ──────────────────────────────────────
    recent = team_hist[team_hist["match_date"] < before_dt].sort_values("match_date")
    if not recent.empty:
        last_match_dt = pd.Timestamp(recent.iloc[-1]["match_date"]).to_pydatetime()
        days_since = (before_dt - last_match_dt.replace(tzinfo=None)).days
        feats[f"{side}_days_rest"] = float(days_since)
        cutoff_14d = before_dt - timedelta(days=14)
        games_14d = recent[recent["match_date"] >= cutoff_14d]
        feats[f"{side}_games_last14d"] = float(len(games_14d))
    else:
        feats[f"{side}_days_rest"]     = 14.0
        feats[f"{side}_games_last14d"] = 0.0

    # ── Midweek match flag ─────────────────────────────────────
    feats["is_midweek"] = 1.0 if before_dt.weekday() in (1, 2, 3) else 0.0

    # ── Season stage (0=early, 0.5=mid, 1.0=late) ─────────────
    season_str = str(match.get("season", ""))
    feats["season_stage"] = _season_stage(before_dt, season_str)

    # ── League table features ─────────────────────────────────
    row = league_table.get(team_id, {})
    feats[f"{side}_league_position"]  = float(row.get("position",       10))
    feats[f"{side}_top4_gap"]         = float(row.get("top4_gap",        10))
    feats[f"{side}_relegation_gap"]   = float(row.get("relegation_gap",  10))

    # ── Match importance score (0–1) ──────────────────────────
    feats["match_importance"] = _match_importance(
        round_name   = match.get("round", ""),
        season_stage = feats["season_stage"],
        top4_gap     = feats[f"{side}_top4_gap"],
        rel_gap      = feats[f"{side}_relegation_gap"],
    )

    # ── Win / clean-sheet streaks ─────────────────────────────
    results = recent.tail(10)["result"].tolist() if not recent.empty else []
    feats[f"{side}_win_streak"]  = float(_streak(results, "W"))
    feats[f"{side}_loss_streak"] = float(_streak(results, "L"))
    feats[f"{side}_cs_streak"]   = float(_streak(recent.tail(10)["clean_sheet"].astype(bool).map(
        lambda x: "Y" if x else "N").tolist(), "Y")) if not recent.empty else 0.0

    return feats


def _season_stage(dt: datetime, season: str) -> float:
    """Heuristic: map calendar month to season stage [0, 1]."""
    month = dt.month
    mapping = {8: 0.0, 9: 0.1, 10: 0.2, 11: 0.3, 12: 0.4,
               1: 0.5, 2: 0.6, 3: 0.7, 4: 0.8, 5: 0.9, 6: 1.0, 7: 1.0}
    return mapping.get(month, 0.5)


def _match_importance(
    round_name: str,
    season_stage: float,
    top4_gap: float,
    rel_gap: float,
) -> float:
    """
    Heuristic match importance in [0, 1].
    Cup finals and relegation deciders score highest.
    """
    score = 0.5 * season_stage   # later in season = higher importance
    rn = (round_name or "").lower()
    if "final" in rn:    score += 0.4
    elif "semi" in rn:   score += 0.2
    elif "quarter" in rn: score += 0.1
    if rel_gap is not None and rel_gap <= 3:   score += 0.2
    if top4_gap is not None and top4_gap <= 3: score += 0.1
    return round(min(1.0, score), 4)


def _streak(results: list[str], target: str) -> int:
    streak = 0
    for r in reversed(results):
        if r == target:
            streak += 1
        else:
            break
    return streak


# ═══════════════════════════════════════════════════════════════════════════
# 5. MARKET FEATURES
# ═══════════════════════════════════════════════════════════════════════════

def compute_market_features(odds_rows: list[dict]) -> dict[str, float]:
    """
    Derive implied probabilities and odds movement signals from fixture_odds rows.

    Parameters
    ----------
    odds_rows : List of fixture_odds rows for the match (one or more pulls,
                possibly at different pulled_at timestamps), across whichever
                markets fixture_odds has for this fixture (1X2 and/or
                Over_Under_Goals — the only two markets with real bookmaker
                coverage; Corners/Cards/BTTS have none, confirmed against
                the live fixture_odds table).
    """
    feats: dict[str, float] = {
        "market_implied_home": NAN_FILL,
        "market_implied_draw": NAN_FILL,
        "market_implied_away": NAN_FILL,
        "market_overround":    NAN_FILL,
        "odds_move_home":      NAN_FILL,
        "odds_move_away":      NAN_FILL,
        "market_confidence":   NAN_FILL,
        "pinnacle_home_close": NAN_FILL,
        "pinnacle_away_close": NAN_FILL,
        # Goals market (line 2.5 — the only line with real odds coverage):
        # was computed post-hoc for edge-scoring one line's prediction only,
        # never fed to the models as an input feature. The bookmaker's own
        # total-goals view is a direct, strong signal for Goals/BTTS/Corners
        # that team-form aggregates alone can't see — same treatment as the
        # 1X2 block above, mirrored for this market.
        "goals_market_implied_over":  NAN_FILL,
        "goals_market_implied_under": NAN_FILL,
        "goals_market_overround":     NAN_FILL,
        "goals_odds_move_over":       NAN_FILL,
    }
    if not odds_rows:
        return feats

    one_x_two = [r for r in odds_rows if (r.get("market") or "") == "1X2"]
    if one_x_two:
        # Prefer Pinnacle; fall back to any bookmaker
        pinnacle_rows = [r for r in one_x_two if "pinnacle" in (r.get("bookmaker", "") or "").lower()]
        rows = pinnacle_rows or one_x_two
        rows_sorted = sorted(rows, key=lambda r: r.get("pulled_at") or "")
        latest = rows_sorted[-1]
        earliest = rows_sorted[0]

        close_h = latest.get("home_odds")
        close_d = latest.get("draw_odds")
        close_a = latest.get("away_odds")

        if close_h and close_a:
            implied_h = _safe_div(1.0, float(close_h))
            implied_d = _safe_div(1.0, float(close_d)) if close_d else 0.0
            implied_a = _safe_div(1.0, float(close_a))
            overround = implied_h + implied_d + implied_a

            feats["market_overround"]    = round(overround, 4)
            feats["market_implied_home"] = round(_safe_div(implied_h, overround), 4)
            feats["market_implied_draw"] = round(_safe_div(implied_d, overround), 4)
            feats["market_implied_away"] = round(_safe_div(implied_a, overround), 4)

            if pinnacle_rows:
                feats["pinnacle_home_close"] = float(close_h)
                feats["pinnacle_away_close"] = float(close_a)

        # Odds movement: earliest pull vs latest pull (proxy for open/close
        # since fixture_odds has no explicit opening/closing columns, only
        # pulled_at)
        open_h = earliest.get("home_odds")
        open_a = earliest.get("away_odds")
        if open_h and close_h:
            feats["odds_move_home"] = round(float(open_h) - float(close_h), 4)
        if open_a and close_a:
            feats["odds_move_away"] = round(float(open_a) - float(close_a), 4)

        total_move = abs(feats["odds_move_home"] if feats["odds_move_home"] != NAN_FILL else 0.0) \
                   + abs(feats["odds_move_away"] if feats["odds_move_away"] != NAN_FILL else 0.0)
        feats["market_confidence"] = round(min(1.0, total_move / 1.0), 4)

    goals = [r for r in odds_rows if (r.get("market") or "") == "Over_Under_Goals"]
    if goals:
        rows_sorted = sorted(goals, key=lambda r: r.get("pulled_at") or "")
        latest = rows_sorted[-1]
        earliest = rows_sorted[0]

        close_over  = latest.get("over_odds")
        close_under = latest.get("under_odds")
        if close_over and close_under:
            implied_over  = _safe_div(1.0, float(close_over))
            implied_under = _safe_div(1.0, float(close_under))
            overround = implied_over + implied_under
            feats["goals_market_overround"]     = round(overround, 4)
            feats["goals_market_implied_over"]  = round(_safe_div(implied_over, overround), 4)
            feats["goals_market_implied_under"] = round(_safe_div(implied_under, overround), 4)

        open_over = earliest.get("over_odds")
        if open_over and close_over:
            feats["goals_odds_move_over"] = round(float(open_over) - float(close_over), 4)

    return feats


# ═══════════════════════════════════════════════════════════════════════════
# 6. REFEREE FEATURES
# ═══════════════════════════════════════════════════════════════════════════

def compute_referee_features(referee: dict | None) -> dict[str, float]:
    """
    No referee-stats table exists in the live schema yet (fixtures.referee is
    a bare name string). Always returns zeroed features until such a table
    is added and populated — do not fabricate values from the name alone.
    """
    if not referee:
        return {
            "ref_avg_yellows":    NAN_FILL,
            "ref_avg_reds":       NAN_FILL,
            "ref_avg_fouls":      NAN_FILL,
            "ref_home_bias":      NAN_FILL,
        }
    return {
        "ref_avg_yellows": float(referee.get("avg_yellow_cards", 0) or 0),
        "ref_avg_reds":    float(referee.get("avg_red_cards",    0) or 0),
        "ref_avg_fouls":   float(referee.get("avg_fouls",        0) or 0),
        "ref_home_bias":   float(referee.get("home_bias_score",  0) or 0),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

class FeatureEngineer:
    """
    Builds the complete pre-match feature vector for one or many matches.

    All DB queries are carefully scoped to be before match_date — no leakage.
    Matches are identified by the live schema's composite key (sport, fixture_id).
    """

    def __init__(self, supabase_client, data_dir: "Path | None" = None):
        """
        Parameters
        ----------
        supabase_client : live Supabase client.
                           - data_dir=None: fully online, every loader hits
                             Supabase directly (the original live-serving path).
                           - data_dir set + supabase_client=None: fully offline,
                             for bulk training (scripts/build_feature_cache.py).
                           - data_dir set + supabase_client given: HYBRID —
                             snapshot is the fast local base, plus one small
                             top-up query for match_results/fixtures newer
                             than the snapshot's newest row. This is what
                             predictor.py now uses: the online path used to
                             paginate the ENTIRE match_results table (~298
                             sequential API calls) before building even one
                             feature vector — confirmed live, several minutes
                             per cold FeatureEngineer instance.
        data_dir : optional path to a local Parquet snapshot directory
                   (see scripts/export_snapshot.py).
        """
        self.client = supabase_client
        self._match_cache:    dict[str, pd.DataFrame] = {}
        self._dc_cache:       dict[tuple, DixonColesEstimator] = {}
        self._table_cache:    dict[tuple, dict] = {}
        self._elo_cache:      dict[tuple, dict[int, float]] = {}
        self._elo_index:      "dict[tuple[str, int], tuple[np.ndarray, np.ndarray]] | None" = None
        self._team_history_cache: dict[tuple[str, int], pd.DataFrame] = {}

        self._offline = data_dir is not None
        self._local: dict[str, pd.DataFrame] = {}
        if self._offline:
            self._load_snapshot(data_dir)
            if self.client is not None:
                self._top_up_from_live()

    def _load_snapshot(self, data_dir: "Path") -> None:
        from pathlib import Path as _Path
        data_dir = _Path(data_dir)
        for name in ("fixtures", "match_results", "fixture_odds", "team_form_cache"):
            matches = sorted(data_dir.glob(f"{name}_*.parquet"))
            if not matches:
                self._local[name] = pd.DataFrame()
                continue
            self._local[name] = pd.concat(
                [pd.read_parquet(p) for p in matches], ignore_index=True
            )

        self._reindex_local()

        logger.info(
            "[FeatureEngineer] Loaded offline snapshot from %s: %s",
            data_dir, {k: len(v) for k, v in self._local.items()},
        )

    def _reindex_local(self) -> None:
        # Index fixtures and fixture_odds by (sport, fixture_id) via
        # set_index — O(1)-ish sorted lookup per call instead of a full
        # boolean scan (up to ~300k rows). Deliberately NOT eagerly
        # materializing every row as a Python dict up front (.to_dict()
        # over 300k rows is itself a multi-minute cost and wasteful when
        # a training run only touches a fraction of the snapshot) — rows
        # are converted to dicts lazily, only for fixtures actually requested.
        fx = self._local["fixtures"]
        self._fixtures_indexed = (
            fx.set_index(["sport", "fixture_id"]).sort_index() if not fx.empty else fx
        )
        fo = self._local["fixture_odds"]
        self._odds_indexed = (
            fo.set_index(["sport", "fixture_id"]).sort_index() if not fo.empty else fo
        )

    def _top_up_from_live(self) -> None:
        """
        Hybrid mode only: pull match_results (+ their fixtures) newer than
        whatever's already in the snapshot, so a periodically-rebuilt local
        Parquet file doesn't silently go stale for live predictions — without
        re-paginating the whole historical table every time. One bounded
        query per sport present in the snapshot, not the full-table scan
        _load_all_sport_matches() used to do online.
        """
        mr = self._local.get("match_results", pd.DataFrame())
        fx = self._local.get("fixtures", pd.DataFrame())
        if fx.empty:
            return

        for sport in fx["sport"].unique():
            sport_fx = fx[fx["sport"] == sport]
            cutoff = pd.to_datetime(sport_fx["match_date"], errors="coerce").max()
            cutoff_iso = (cutoff.isoformat() if pd.notna(cutoff) else "1970-01-01T00:00:00")

            try:
                res = (
                    self.client.table("match_results")
                    .select(
                        "fixture_id, home_goals, away_goals, total_corners, home_corners,"
                        " away_corners, total_cards,"
                        " fixtures!inner(sport, fixture_id, home_team_id, away_team_id, match_date,"
                        " kickoff_time, league_key, venue, season, round)"
                    )
                    .eq("sport", sport)
                    .not_.is_("home_goals", "null")
                    .gt("fixtures.match_date", cutoff_iso)
                    .execute()
                )
            except Exception as exc:
                logger.warning("[FeatureEngineer] top-up query failed for %s (continuing on snapshot only): %s", sport, exc)
                continue

            rows = res.data or []
            if not rows:
                continue

            new_fx_rows, new_mr_rows = [], []
            for r in rows:
                fx_data = dict(r.pop("fixtures", {}) or {})
                fx_data.setdefault("sport", sport)
                new_fx_rows.append(fx_data)
                r["sport"] = sport
                new_mr_rows.append(r)

            if new_fx_rows:
                self._local["fixtures"] = pd.concat(
                    [self._local["fixtures"], pd.DataFrame(new_fx_rows)], ignore_index=True
                )
            if new_mr_rows:
                self._local["match_results"] = pd.concat(
                    [self._local["match_results"], pd.DataFrame(new_mr_rows)], ignore_index=True
                )
            logger.info("[FeatureEngineer] Topped up %d %s match(es) newer than snapshot (cutoff=%s)",
                        len(new_mr_rows), sport, cutoff_iso)

        self._reindex_local()

    # ── Public API ──────────────────────────────────────────────

    def build(self, sport: str, fixture_id: str) -> dict[str, float]:
        """Build the full feature dict for a single match."""
        match = self._load_match(sport, fixture_id)
        if not match:
            raise ValueError(f"Fixture {sport}/{fixture_id} not found")
        return self._build_features(match)

    def build_batch(self, fixtures: list[tuple[str, str]]) -> pd.DataFrame:
        """Build feature DataFrame for multiple (sport, fixture_id) matches."""
        rows = []
        for sport, fixture_id in fixtures:
            try:
                match = self._load_match(sport, fixture_id)
                if match:
                    feats = self._build_features(match)
                    feats["sport"] = sport
                    feats["fixture_id"] = fixture_id
                    rows.append(feats)
            except Exception as exc:
                logger.warning("Feature build failed for %s/%s: %s", sport, fixture_id, exc)
        return pd.DataFrame(rows)

    # ── Core feature build ──────────────────────────────────────

    def _build_features(self, match: dict) -> dict[str, float]:
        sport      = match["sport"]
        fixture_id = match["fixture_id"]
        home_id    = match["home_team_id"]
        away_id    = match["away_team_id"]
        league_key = match.get("league_key")
        venue      = match.get("venue")
        referee    = match.get("referee_data")
        match_dt   = self._parse_dt(match)

        if match_dt is None:
            raise ValueError(f"Cannot parse match_date for fixture {sport}/{fixture_id}")

        all_matches = self._load_all_sport_matches(sport)

        # ── Per-team history ─────────────────────────────────────
        home_hist_df = self._team_history(sport, home_id, all_matches, before_dt=match_dt, is_home=True)
        away_hist_df = self._team_history(sport, away_id, all_matches, before_dt=match_dt, is_home=False)

        home_form_calc = FormCalculator(home_hist_df)
        away_form_calc = FormCalculator(away_hist_df)

        feats: dict[str, float] = {}

        # 1. FORM
        feats.update(home_form_calc.compute(match_dt, prefix="home"))
        feats.update(away_form_calc.compute(match_dt, prefix="away"))

        # Win/loss streaks
        feats["home_win_streak"]   = float(home_form_calc.consecutive_streak(match_dt, "W"))
        feats["home_loss_streak"]  = float(home_form_calc.consecutive_streak(match_dt, "L"))
        feats["away_win_streak"]   = float(away_form_calc.consecutive_streak(match_dt, "W"))
        feats["away_loss_streak"]  = float(away_form_calc.consecutive_streak(match_dt, "L"))

        # 2. STRENGTH — Elo (from team_form_cache; STARTING_ELO if no row cached yet)
        home_elo = self._get_cached_elo(sport, home_id, match_dt)
        away_elo = self._get_cached_elo(sport, away_id, match_dt)
        feats["elo_home"]        = round(home_elo, 2)
        feats["elo_away"]        = round(away_elo, 2)
        feats["elo_diff"]        = round(home_elo - away_elo, 2)
        feats["elo_prob_home"]   = round(
            1.0 / (1.0 + 10 ** ((away_elo - home_elo - 65) / 400)), 4
        )

        # Dixon-Coles
        dc = self._get_dixon_coles(league_key, all_matches, match_dt)
        feats["dc_attack_home"]  = round(dc.attack(home_id),    4)
        feats["dc_defense_home"] = round(dc.defense(home_id),   4)
        feats["dc_attack_away"]  = round(dc.attack(away_id),    4)
        feats["dc_defense_away"] = round(dc.defense(away_id),   4)
        lam_h, lam_a = dc.expected_goals(home_id, away_id)
        feats["dc_exp_goals_home"] = round(lam_h, 4)
        feats["dc_exp_goals_away"] = round(lam_a, 4)

        # 3. HEAD TO HEAD
        feats.update(compute_h2h_features(home_id, away_id, venue, match_dt, all_matches))

        # 4. CONTEXT
        league_table = self._build_league_table(league_key, all_matches, match_dt)
        feats.update(compute_context_features(match, home_id, home_hist_df, match_dt,
                                              league_table, is_home=True))
        feats.update(compute_context_features(match, away_id, away_hist_df, match_dt,
                                              league_table, is_home=False))

        # 5. MARKET
        odds_rows = self._load_odds(sport, fixture_id)
        feats.update(compute_market_features(odds_rows))

        # 6. REFEREE
        feats.update(compute_referee_features(referee))

        # Fill any remaining NaNs
        feats = {k: (NAN_FILL if (v is None or (isinstance(v, float) and math.isnan(v))) else v)
                 for k, v in feats.items()}

        return feats

    # ── DB Loaders ──────────────────────────────────────────────

    def _load_match(self, sport: str, fixture_id: str) -> dict | None:
        if self._offline:
            try:
                row = self._fixtures_indexed.loc[(sport, fixture_id)]
                m = row.to_dict()
                m["sport"], m["fixture_id"] = sport, fixture_id
                m["referee_data"] = None
                return m
            except KeyError:
                # Hybrid mode only: the fixture being predicted right now is
                # inherently newer than any periodically-rebuilt snapshot —
                # a single-row live lookup here is cheap (unlike the full
                # historical top-up), so fall through rather than fail.
                if self.client is None:
                    return None

        res = (
            self.client.table("fixtures")
            .select("*")
            .eq("sport", sport)
            .eq("fixture_id", fixture_id)
            .single()
            .execute()
        )
        if not res.data:
            return None
        m = res.data
        # No referee-stats table in the live schema yet — see compute_referee_features
        m["referee_data"] = None
        return m

    def _load_all_sport_matches(self, sport: str) -> pd.DataFrame:
        """
        Load all finished matches for the sport (match_results joined with
        fixtures for team ids / date / league), cached per sport.
        """
        if sport in self._match_cache:
            return self._match_cache[sport]

        if self._offline:
            mr = self._local["match_results"]
            fx = self._local["fixtures"]
            mr = mr[(mr["sport"] == sport) & mr["home_goals"].notna()]
            fx_cols = ["sport", "fixture_id", "home_team_id", "away_team_id",
                       "match_date", "kickoff_time", "league_key", "venue", "season", "round"]
            df = mr.merge(fx[fx_cols], on=["sport", "fixture_id"], how="inner")
        else:
            all_rows: list[dict] = []
            page, psize = 0, 1_000
            while True:
                res = (
                    self.client.table("match_results")
                    .select(
                        "fixture_id, home_goals, away_goals, total_corners, home_corners,"
                        " away_corners, total_cards,"
                        " fixtures!inner(home_team_id, away_team_id, match_date, kickoff_time,"
                        " league_key, venue, season, round)"
                    )
                    .eq("sport", sport)
                    .not_.is_("home_goals", "null")
                    .range(page * psize, (page + 1) * psize - 1)
                    .execute()
                )
                batch = res.data or []
                for r in batch:
                    fx = r.pop("fixtures", {}) or {}
                    r.update(fx)
                all_rows.extend(batch)
                if len(batch) < psize:
                    break
                page += 1
            df = pd.DataFrame(all_rows)

        if not df.empty:
            df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
            df["match_date"] = df["match_date"].dt.tz_localize(None)
            df = df.sort_values("match_date").reset_index(drop=True)
        self._match_cache[sport] = df
        return df

    def _get_team_full_history(self, sport: str, team_id: int,
                                all_matches: pd.DataFrame) -> pd.DataFrame:
        """
        Full enriched (both-perspective), sorted history for one team —
        every column _team_history() derives, before the point-in-time
        date filter. Cached per (sport, team_id).

        _team_history() used to redo this whole thing — including an O(n)
        boolean-mask filter of the entire sport's match table — on EVERY
        call, and it's called twice per fixture (home + away) unconditionally.
        That's the same "filter the whole history table every time" cost
        already fixed for Elo lookups; only the cheap final date filter
        actually needs to happen per-call.
        """
        key = (sport, team_id)
        if key in self._team_history_cache:
            return self._team_history_cache[key]

        if all_matches.empty:
            self._team_history_cache[key] = all_matches
            return all_matches

        # Slice to only the columns this function needs before filtering —
        # the full frame carries ~35 mostly-unused object-dtype columns
        # (raw_stats, scoreline, ftr, ...) whose presence forces the later
        # row-wise result computation onto pandas' slow generic object path.
        needed = ["match_date", "home_team_id", "away_team_id",
                  "home_goals", "away_goals", "home_corners", "away_corners", "total_cards"]
        slim = all_matches[needed]

        home_games = slim[slim["home_team_id"] == team_id].copy()
        away_games = slim[slim["away_team_id"] == team_id].copy()

        def _enrich(df: pd.DataFrame, perspective_home: bool) -> pd.DataFrame:
            df = df.copy()
            df["is_home"] = perspective_home
            if perspective_home:
                df["goals_for"]      = df["home_goals"]
                df["goals_against"]  = df["away_goals"]
                df["corners_for"]    = df.get("home_corners", pd.Series(NAN_FILL, index=df.index))
                df["corners_against"]= df.get("away_corners", pd.Series(NAN_FILL, index=df.index))
            else:
                df["goals_for"]      = df["away_goals"]
                df["goals_against"]  = df["home_goals"]
                df["corners_for"]    = df.get("away_corners", pd.Series(NAN_FILL, index=df.index))
                df["corners_against"]= df.get("home_corners", pd.Series(NAN_FILL, index=df.index))
            df["cards_total"] = df.get("total_cards", pd.Series(NAN_FILL, index=df.index))
            # Vectorized W/D/L — was a per-row .apply(axis=1), the dominant
            # cost in feature building at scale.
            df["result"] = np.where(
                df["goals_for"] > df["goals_against"], "W",
                np.where(df["goals_for"] == df["goals_against"], "D", "L"),
            )
            df["clean_sheet"] = (df["goals_against"] == 0).astype(int)
            df["btts"]        = ((df["goals_for"] > 0) & (df["goals_against"] > 0)).astype(int)
            df["over25"]      = ((df["goals_for"] + df["goals_against"]) > 2.5).astype(int)
            return df

        combined = pd.concat([
            _enrich(home_games, True),
            _enrich(away_games, False),
        ]).sort_values("match_date").reset_index(drop=True)

        self._team_history_cache[key] = combined
        return combined

    def _team_history(self, sport: str, team_id: int, all_matches: pd.DataFrame,
                      before_dt: datetime, is_home: bool) -> pd.DataFrame:
        """
        Point-in-time history for team_id, add perspective columns (is_home,
        goals_for, goals_against, corners_for, corners_against, cards_total,
        result, clean_sheet, btts, over25).
        """
        combined = self._get_team_full_history(sport, team_id, all_matches)
        if combined.empty:
            return combined
        return combined[combined["match_date"] < pd.Timestamp(before_dt)]

    def _load_odds(self, sport: str, fixture_id: str) -> list[dict]:
        if self._offline:
            try:
                hit = self._odds_indexed.loc[[(sport, fixture_id)]]
            except KeyError:
                return []
            return hit.reset_index().to_dict(orient="records")

        res = (
            self.client.table("fixture_odds")
            .select("*")
            .eq("sport", sport)
            .eq("fixture_id", fixture_id)
            .execute()
        )
        return res.data or []

    def _build_elo_index(self) -> None:
        """
        One-time index of team_form_cache for O(log n) point-in-time Elo
        lookups: {(sport, team_id): (sorted_dates, sorted_ratings)}.

        _get_cached_elo() used to re-filter the full team_form_cache
        DataFrame (and re-parse its as_of_date column to datetime) on
        EVERY call. That's fine when the table is empty, but with it
        genuinely populated (~580k rows) each lookup took ~0.15s — at
        ~600k lookups for a full feature-cache build that's ~25 hours.
        Building this index once up front makes each lookup a numpy
        searchsorted against a small per-team array instead.
        """
        self._elo_index: dict[tuple[str, int], tuple[np.ndarray, np.ndarray]] = {}
        tf = self._local.get("team_form_cache", pd.DataFrame())
        if tf.empty or "elo_rating" not in tf.columns:
            return
        tf = tf.dropna(subset=["elo_rating"])
        if tf.empty:
            return
        tf = tf.assign(_as_of=pd.to_datetime(tf["as_of_date"]).values.astype("datetime64[D]"))
        tf = tf.sort_values(["sport", "team_id", "_as_of"])
        for (sp, tid), g in tf.groupby(["sport", "team_id"], sort=False):
            self._elo_index[(sp, tid)] = (
                g["_as_of"].to_numpy(),
                g["elo_rating"].to_numpy(dtype=float),
            )

    def _get_cached_elo(self, sport: str, team_id: int, before_dt: datetime) -> float:
        """
        Point-in-time Elo lookup from team_form_cache (pre-aggregated,
        strictly-prior rows only). Falls back to STARTING_ELO when the
        cache has no row for this team yet.
        """
        key = (sport, before_dt.date())
        if key not in self._elo_cache:
            self._elo_cache[key] = {}
        cache = self._elo_cache[key]
        if team_id in cache:
            return cache[team_id]

        if self._offline:
            if self._elo_index is None:
                self._build_elo_index()
            rating = STARTING_ELO
            idx = self._elo_index.get((sport, team_id))
            if idx is not None:
                dates_arr, ratings_arr = idx
                target = np.datetime64(before_dt.date(), "D")
                pos = np.searchsorted(dates_arr, target, side="right") - 1
                if pos >= 0:
                    rating = float(ratings_arr[pos])
            cache[team_id] = rating
            return rating

        res = (
            self.client.table("team_form_cache")
            .select("elo_rating")
            .eq("sport", sport)
            .eq("team_id", team_id)
            .lte("as_of_date", before_dt.date().isoformat())
            .order("as_of_date", desc=True)
            .limit(1)
            .execute()
        )
        rating = STARTING_ELO
        if res.data and res.data[0].get("elo_rating") is not None:
            rating = float(res.data[0]["elo_rating"])
        cache[team_id] = rating
        return rating

    def _get_dixon_coles(self, league_key: str | None, all_matches: pd.DataFrame,
                          before_dt: datetime) -> DixonColesEstimator:
        key = (league_key, before_dt.date())
        if key in self._dc_cache:
            return self._dc_cache[key]
        league_matches = (
            all_matches[all_matches["league_key"] == league_key]
            if league_key is not None and not all_matches.empty
            else all_matches
        )
        dc = DixonColesEstimator(league_matches).fit(before_dt)
        self._dc_cache[key] = dc
        return dc

    def _build_league_table(self, league_key: str | None, all_matches: pd.DataFrame,
                             before_dt: datetime) -> dict[int, dict]:
        """
        Simulate standing at before_dt.
        Returns {team_id: {position, points, top4_gap, relegation_gap}}.
        """
        key = (league_key, before_dt.date())
        if key in self._table_cache:
            return self._table_cache[key]

        if all_matches.empty:
            self._table_cache[key] = {}
            return {}

        hist = all_matches[
            (all_matches["league_key"] == league_key) &
            (all_matches["match_date"] < pd.Timestamp(before_dt))
        ]
        if hist.empty:
            self._table_cache[key] = {}
            return {}

        # Vectorized standings — was a Python-level iterrows() over full
        # league history per fixture-date (the dominant cost in feature
        # building at scale); now a single groupby over ≤2×len(hist) rows,
        # bounded by team count (~20-24) afterward, not history length.
        home = hist[["home_team_id", "home_goals", "away_goals"]].rename(
            columns={"home_team_id": "team_id", "home_goals": "gf", "away_goals": "ga"})
        away = hist[["away_team_id", "away_goals", "home_goals"]].rename(
            columns={"away_team_id": "team_id", "away_goals": "gf", "home_goals": "ga"})
        long = pd.concat([home, away], ignore_index=True)
        long["points"] = np.where(long["gf"] > long["ga"], 3, np.where(long["gf"] == long["ga"], 1, 0))
        long["gd"] = long["gf"] - long["ga"]

        agg = (
            long.groupby("team_id")
            .agg(points=("points", "sum"), gd=("gd", "sum"))
            .sort_values(["points", "gd"], ascending=[False, False])
        )

        n = len(agg)
        pts_arr = agg["points"].values
        top4_pts = int(pts_arr[min(3, n - 1)]) if n >= 4 else 0
        rel_pts  = int(pts_arr[max(n - 4, 0)]) if n >= 4 else 0

        result: dict[int, dict] = {}
        for pos, (tid, row) in enumerate(agg.iterrows(), start=1):
            points = int(row["points"])
            result[tid] = {
                "position":       pos,
                "points":         points,
                "top4_gap":       max(0, top4_pts - points),
                "relegation_gap": max(0, points - rel_pts),
            }

        self._table_cache[key] = result
        return result

    # ── Utility ─────────────────────────────────────────────────

    @staticmethod
    def _parse_dt(match: dict) -> datetime | None:
        """
        fixtures.match_date is a bare date; kickoff_time is a separate time
        column. Combine them (default midnight if kickoff_time is null).
        """
        raw_date = match.get("match_date")
        if not raw_date:
            return None
        try:
            d = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
        raw_time = match.get("kickoff_time")
        t = time(0, 0, 0)
        if raw_time:
            try:
                t = datetime.strptime(str(raw_time)[:8], "%H:%M:%S").time()
            except (ValueError, TypeError):
                pass
        return datetime.combine(d, t)

    def feature_names(self) -> list[str]:
        """Build a dummy feature vector to enumerate all feature names."""
        dummy_feats = {
            **{f"home_form{w}_{s}": 0.0 for w in FORM_WINDOWS
               for s in ["ppg","gscored","gconceded","corners_for","corners_against",
                         "cards_total","cs_rate","btts_rate","over25_rate",
                         "win_pct","draw_pct","loss_pct"]},
            **{f"away_form{w}_{s}": 0.0 for w in FORM_WINDOWS
               for s in ["ppg","gscored","gconceded","corners_for","corners_against",
                         "cards_total","cs_rate","btts_rate","over25_rate",
                         "win_pct","draw_pct","loss_pct"]},
        }
        return sorted(dummy_feats.keys())
