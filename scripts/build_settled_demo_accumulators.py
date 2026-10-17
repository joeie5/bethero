"""
build_settled_demo_accumulators.py — Build 3-odds/5-odds/10-odds
accumulators for season weeks 1-6, one ticket set per "day-group" within
each week:

  - Weekday group (Mon-Thu): legs may span those 2-4 days combined.
  - Friday, Saturday, Sunday: each is its own single-day ticket set —
    a Saturday ticket must never include a Friday or Sunday leg.

This mirrors how a real user picks tickets: weekday midweek fixtures are
sparser so a short combined window makes sense, but weekend slates are
dense enough (and distinct enough as match days) to stand alone.

Legs are ranked by real model_probability (Goals prioritized — our
best-calibrated market), not the `confidence` composite score, which can
be high on a genuinely low-probability, high-value pick — fine for value
betting, wrong for building a ticket that needs to actually land. Cross-
tier exclusivity (a fixture/market pair used in one tier can't reappear in
another) is scoped per (week, day-group) — the natural boundary of "one
set of tickets".

Note on §1.5 (5-odds/10-odds are gated for real users): this is local demo
data built from historical, already-resolved matches — not a ticket being
offered to a real user to place a bet on.

Usage:
    PYTHONPATH=. python3 scripts/build_settled_demo_accumulators.py
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from app.database import get_supabase_admin
from app.ml.accumulator_builder import Selection, MAX_SINGLE_ODDS
from app.ml.outcome_resolver import resolve_actual_outcome
from scripts.export_snapshot import fetch_all

SEASON = 2026
WEEKS_TO_BUILD = 6  # season week 1..6

TIER_CONFIG = {
    "3odds":  {"min_legs": 3, "max_legs": 3,  "min_probability": 0.55, "target_odds": 3.0},
    "5odds":  {"min_legs": 5, "max_legs": 5,  "min_probability": 0.50, "target_odds": 5.0},
    "10odds": {"min_legs": 10, "max_legs": 10, "min_probability": 0.45, "target_odds": 10.0},
}

# Goals is our best-calibrated market (77.3% real accuracy vs. 55-63% for
# the others) — let it fill more of a ticket than the rest, rather than
# capping every market equally and forcing in weaker picks just to hit a
# leg count. Still capped, not unlimited — concentrating 100% in one
# market is the exact failure mode CLAUDE.md's diversity rule exists to
# prevent (one market took 53.6% of all picks before that cap existed).
MARKET_CAP = {"Over_Under_Goals": 4}
DEFAULT_MARKET_CAP = 2
MAX_SAME_LEAGUE = 2
MAX_SAME_DATE = 4

MAIN_TIER_LEAGUES = [
    "E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3",
    "D1", "D2", "SP1", "SP2", "I1", "I2", "F1", "F2",
    "N1", "B1", "P1", "T1", "G1",
]

DAY_GROUPS = ["weekday", "friday", "saturday", "sunday"]


def _sort_key(s: Selection) -> tuple:
    return (0 if s.market == "Over_Under_Goals" else 1, -s.model_probability)


def _day_group(weekday: int) -> str:
    # Monday=0 ... Sunday=6
    return {4: "friday", 5: "saturday", 6: "sunday"}.get(weekday, "weekday")


def _season_week_numbers(fixtures_df: pd.DataFrame) -> dict[tuple[int, int], int]:
    """Maps (iso_year, iso_week) -> sequential season week number (1, 2, ...),
    in chronological order of first appearance in the season's fixtures."""
    dates = pd.to_datetime(fixtures_df["match_date"])
    iso = dates.dt.isocalendar()
    pairs = sorted(set(zip(iso["year"], iso["week"])))
    return {pair: i + 1 for i, pair in enumerate(pairs)}


def main() -> None:
    client = get_supabase_admin()

    print("Loading predictions + fixtures + results...")
    preds_df = fetch_all(client, "predictions", "*", {"sport": "football"}, ["id"])
    preds_df = preds_df.where(preds_df.notna(), None)
    preds = preds_df.to_dict("records")

    fixtures_df = pd.read_parquet("data_snapshot/fixtures_football.parquet")
    season_fixtures = fixtures_df[
        (fixtures_df["season"] == SEASON)
        & (fixtures_df["league_key"].isin(MAIN_TIER_LEAGUES))
        & (fixtures_df["status"] == "FT")
    ]
    week_number_by_iso = _season_week_numbers(season_fixtures)

    fixtures_df = fixtures_df.where(fixtures_df.notna(), None)
    fixtures_by_id = {r["fixture_id"]: r for r in fixtures_df.to_dict("records")}

    results_df = pd.read_parquet("data_snapshot/match_results_football.parquet")
    results_df = results_df.where(results_df.notna(), None)
    results_by_id = {r["fixture_id"]: r for r in results_df.to_dict("records")}

    # Build the full candidate pool, tagging each with its season week
    # number and day-group.
    pool: list[tuple[Selection, str, bool, int, str]] = []
    for p in preds:
        fx = fixtures_by_id.get(p["fixture_id"])
        if not fx or fx.get("status") != "FT" or fx.get("season") != SEASON:
            continue
        if fx.get("league_key") not in MAIN_TIER_LEAGUES:
            continue
        match_date = fx.get("match_date")
        if not match_date:
            continue
        d = date.fromisoformat(str(match_date)[:10])
        iso = d.isocalendar()
        week_num = week_number_by_iso.get((iso[0], iso[1]))
        if week_num is None or week_num > WEEKS_TO_BUILD:
            continue
        day_group = _day_group(d.weekday())

        result = results_by_id.get(p["fixture_id"])
        if not result:
            continue
        actual = resolve_actual_outcome(p["market"], p["selection"], result)
        if actual is None:
            continue

        raw_odds = p.get("odds")
        odds = raw_odds if raw_odds is not None and not pd.isna(raw_odds) else round(1.0 / p["model_probability"], 2)
        if odds > MAX_SINGLE_ODDS:
            continue
        raw_edge = p.get("edge")
        edge = raw_edge if raw_edge is not None and not pd.isna(raw_edge) else 0.0

        sel = Selection(
            prediction_id=p["id"], sport="football", fixture_id=p["fixture_id"],
            market=p["market"], selection=p["selection"],
            model_probability=p["model_probability"], odds=odds,
            confidence=p["confidence"], edge=edge,
            league_key=fx.get("league_key"), match_date=str(match_date),
            home_team=fx.get("home_team") or "", away_team=fx.get("away_team") or "",
            league_name=fx.get("league_name") or "",
        )
        pool.append((sel, actual, p["selection"] == actual, week_num, day_group))

    print(f"Candidate pool: {len(pool)} selections across weeks 1-{WEEKS_TO_BUILD}\n")

    # Resumability: if this crashes partway (transient network errors have
    # happened before) a rerun should skip combos already built rather than
    # duplicate them — target_date+acc_type is unique to our own generation
    # scheme (anchor_date is deterministic per week/day-group).
    existing_res = client.table("accumulators").select("target_date,acc_type").execute()
    already_built = {(r["target_date"], r["acc_type"]) for r in (existing_res.data or [])}

    total_built = 0
    for week_num in range(1, WEEKS_TO_BUILD + 1):
        for day_group in DAY_GROUPS:
            group_pool = [t for t in pool if t[3] == week_num and t[4] == day_group]
            if not group_pool:
                continue

            used_fixture_market: set[tuple[str, str]] = set()
            group_built = []

            for acc_type, cfg in TIER_CONFIG.items():
                eligible = [
                    (s, a, c) for s, a, c, _, _ in group_pool
                    if s.model_probability >= cfg["min_probability"]
                    and (s.fixture_id, s.market) not in used_fixture_market
                ]
                eligible.sort(key=lambda t: _sort_key(t[0]))
                by_pred_id = {s.prediction_id: (a, c) for s, a, c in eligible}

                # Greedily add the best-ranked legs (Goals first, then
                # highest real probability) until the tier's target odds is
                # reached — not always maxed to max_legs. A "3-odds" ticket
                # that reaches ~3x combined odds in 2 legs is a BETTER
                # ticket than the same target padded to 4 legs with a
                # weaker 3rd/4th pick, since every extra leg compounds
                # failure risk for no benefit once the target's already hit.
                legs: list[Selection] = []
                seen_fixtures: set[str] = set()
                market_count: dict[str, int] = {}
                league_count: dict[str, int] = {}
                date_count: dict[str, int] = {}
                combined_odds = 1.0

                for s, _, _ in eligible:
                    if len(legs) >= cfg["max_legs"]:
                        break
                    if s.fixture_id in seen_fixtures:
                        continue
                    cap = MARKET_CAP.get(s.market, DEFAULT_MARKET_CAP)
                    if market_count.get(s.market, 0) >= cap:
                        continue
                    lkey = s.league_key or "-1"
                    if league_count.get(lkey, 0) >= MAX_SAME_LEAGUE:
                        continue
                    dt = s.match_date[:10]
                    if date_count.get(dt, 0) >= MAX_SAME_DATE:
                        continue

                    legs.append(s)
                    seen_fixtures.add(s.fixture_id)
                    market_count[s.market] = market_count.get(s.market, 0) + 1
                    league_count[lkey] = league_count.get(lkey, 0) + 1
                    date_count[dt] = date_count.get(dt, 0) + 1
                    combined_odds *= s.odds

                    if len(legs) >= cfg["min_legs"] and combined_odds >= cfg["target_odds"]:
                        break

                if len(legs) < cfg["min_legs"]:
                    continue

                for s in legs:
                    used_fixture_market.add((s.fixture_id, s.market))

                combined_odds = round(combined_odds, 3)
                all_correct = all(by_pred_id[s.prediction_id][1] for s in legs)
                avg_prob = (sum(s.model_probability for s in legs) / len(legs)) ** len(legs)

                # target_date anchors this ticket to its day-group for
                # read-time week/day grouping — earliest leg date for the
                # weekday group (which can span Mon-Thu), the single date
                # itself for weekend groups.
                group_dates = sorted(s.match_date[:10] for s in legs)
                anchor_date = group_dates[0]

                if (anchor_date, acc_type) in already_built:
                    print(f"Week {week_num} / {day_group} / {acc_type}: already built, skipping")
                    continue

                acca_row = {
                    "acc_type": acc_type,
                    "target_date": anchor_date,
                    "target_odds": combined_odds,
                    "actual_odds": combined_odds,
                    "model_win_probability": round(avg_prob, 4),
                    "legs": len(legs),
                    "status": "settled",
                    "outcome": "won" if all_correct else "lost",
                    "return_amount": combined_odds if all_correct else 0.0,
                    "settled": True,
                }
                acca_ins = client.table("accumulators").insert(acca_row).execute()
                acca_id = acca_ins.data[0]["id"]

                pick_rows = [{
                    "accumulator_id": acca_id,
                    "sport": s.sport, "fixture_id": s.fixture_id,
                    "prediction_id": s.prediction_id,
                    "home_team": s.home_team, "away_team": s.away_team,
                    "match_date": s.match_date[:10] if s.match_date else None,
                    "league_key": s.league_key, "league_name": s.league_name,
                    "market": s.market, "selection": s.selection,
                    "confidence": s.confidence, "odds": s.odds,
                    "leg_order": i + 1,
                } for i, s in enumerate(legs)]
                client.table("accumulator_picks").insert(pick_rows).execute()

                total_built += 1
                group_built.append(acc_type)
                print(f"Week {week_num} / {day_group} / {acc_type}: {len(legs)} legs, "
                      f"odds {combined_odds}, {'WON' if all_correct else 'LOST'} "
                      f"(id={acca_id}, dates {group_dates[0]}..{group_dates[-1]})")

            if not group_built:
                print(f"Week {week_num} / {day_group}: not enough eligible legs for any tier, skipped")

    print(f"\n=== DONE — {total_built} accumulators built across weeks 1-{WEEKS_TO_BUILD} ===")


if __name__ == "__main__":
    main()
