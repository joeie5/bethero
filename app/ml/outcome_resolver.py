"""
outcome_resolver.py — Given a market/selection and the real match_results
row, determines what actually happened. Shared by any endpoint that needs
to show a stored prediction/pick against its real outcome (longshots,
results history) rather than storing it redundantly on every row.
"""
from __future__ import annotations


def resolve_actual_outcome(market: str, selection: str, result: dict) -> str | None:
    if market == "BTTS":
        if result.get("btts") is None:
            return None
        return "Yes" if result["btts"] else "No"
    if market == "Cards":
        if result.get("total_cards") is None:
            return None
        return "Over 3.5" if result["total_cards"] > 3.5 else "Under 3.5"
    if market == "Over_Under_Corners":
        if result.get("total_corners") is None:
            return None
        line = float(selection.split()[-1])
        total_corners = result["total_corners"]
        if total_corners > line:
            return f"Over {line}"
        # A miss on "Over 7.5" isn't reported as "Under 7.5" — that's not
        # one of this system's two real corners markets (Over 7.5,
        # Under 9.5, per CLAUDE.md §2). corners <= 7.5 always implies
        # corners < 9.5 too, so report it against the line that's actually
        # tracked instead of an ad-hoc mirror of whatever was predicted.
        if line == 7.5:
            return "Under 9.5"
        return f"Under {line}"
    if market == "Over_Under_Goals":
        if result.get("home_goals") is None or result.get("away_goals") is None:
            return None
        line = float(selection.split()[-1])
        total = result["home_goals"] + result["away_goals"]
        if total > line:
            return f"Over {line}"
        # Same reasoning as corners above — "Under 1.5" isn't one of the
        # three real goals lines (Over 1.5, Over 2.5, Under 3.5). goals<=1.5
        # always implies goals<3.5, so report against the real tracked line.
        if line == 1.5:
            return "Under 3.5"
        return f"Under {line}"
    if market == "1X2":
        return {"H": "Home", "D": "Draw", "A": "Away"}.get(result.get("ftr"))
    return None
