"""
test_no_leakage.py — §1.1 hard-constraint guard.

Asserts that none of the post-match statistic columns (mapped to the live
`match_results` schema) ever appear as a key in the feature dict FeatureEngineer
produces. These columns may only be used as (a) the label itself, or (b) input
to a rolling average computed strictly from matches before the one being
predicted — never as a same-match feature.

Live-schema mapping of the brief's original column list:
    FTHG, FTAG          -> home_goals, away_goals
    HTHG, HTAG          -> ht_home_goals, ht_away_goals
    HTR                 -> htr
    HS, AS              -> (no live equivalent — shots-on-target only)
    HST, AST            -> home_sot, away_sot
    HC, AC              -> home_corners, away_corners
    HY, AY, HR, AR       -> (no per-team split in live schema — total_yellow/total_red only)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.feature_engineer import FeatureEngineer, FormCalculator  # noqa: E402

# Raw post-match columns (live match_results schema) that must never appear
# verbatim as a feature-dict key. Rolling/aggregate derivatives (e.g.
# "home_form5_gscored") are fine — those are historical averages, not
# same-match leakage — so this checks for exact key matches only.
BANNED_RAW_COLUMNS = {
    "home_goals", "away_goals",
    "ht_home_goals", "ht_away_goals",
    "ftr", "htr",
    "home_sot", "away_sot",
    "home_corners", "away_corners",
    "total_corners",
    "total_yellow", "total_red", "total_cards",
    "btts", "over25", "over15",
    "home_clean_sheet", "away_clean_sheet",
    "total_goals", "goal_diff",
}


def test_feature_names_exclude_banned_columns():
    fe = FeatureEngineer(supabase_client=None)
    names = set(fe.feature_names())
    leaked = names & BANNED_RAW_COLUMNS
    assert not leaked, f"Leaky columns present in feature_names(): {leaked}"


def test_form_calculator_output_excludes_banned_columns():
    """
    FormCalculator.compute() is the main per-match feature producer — run it
    on a small synthetic history and check the *output* dict directly, not
    just the static feature_names() enumeration.
    """
    import pandas as pd
    from datetime import datetime

    history = pd.DataFrame([
        {
            "match_date": datetime(2024, 1, d),
            "is_home": True,
            "goals_for": 2, "goals_against": 1,
            "corners_for": 6, "corners_against": 4,
            "cards_total": 3,
            "result": "W", "clean_sheet": 0, "btts": 1, "over25": 0,
        }
        for d in range(1, 6)
    ])
    fc = FormCalculator(history)
    feats = fc.compute(before_dt=datetime(2024, 2, 1), prefix="home")

    leaked = set(feats.keys()) & BANNED_RAW_COLUMNS
    assert not leaked, f"Leaky columns present in FormCalculator output: {leaked}"

    # Sanity: rolling aggregates (the *allowed* historical form of these
    # same signals) should be present.
    assert "home_form5_gscored" in feats
    assert "home_form5_corners_for" in feats
    assert "home_form5_cards_total" in feats


if __name__ == "__main__":
    test_feature_names_exclude_banned_columns()
    test_form_calculator_output_excludes_banned_columns()
    print("PASSED — no leaky post-match columns in FeatureEngineer output")
