"""
match_stats_fetcher.py — Fills in corner and card counts for finished matches
whose match_results row only has goals.

Why this exists: both near-real-time result sources (The Odds API /scores and
API-Sports /fixtures?id=) are goals-only, and football-data.co.uk (which does
carry corners/cards) publishes ~6 days late. Left alone, every Corners/Cards
prediction on a recent match stays unsettled for a week. API-Sports'
/fixtures/statistics returns both per team in one call, so this spends a
bounded slice of the daily quota on exactly the fixtures that need it.

Bounded on purpose: tracked leagues only (LEAGUE_TIERS), only fixtures that
have an unsettled Corners/Cards prediction, newest first, hard-capped per
run, and it stops at the first quota error rather than retrying.
"""
from __future__ import annotations

import logging
import os
from datetime import date

import httpx

from app.database import get_supabase_admin
from app.ml.league_tiers import LEAGUE_TIERS

logger = logging.getLogger(__name__)

STATS_URL = "https://v3.football.api-sports.io/fixtures/statistics"
STAT_MARKETS = ("Over_Under_Corners", "Cards")


def _stat(team_stats: list[dict], stat_type: str) -> int:
    for s in team_stats:
        if s.get("type") == stat_type:
            v = s.get("value")
            return int(v) if v is not None else 0
    return 0


def fill_corners_and_cards(sport: str = "football", max_fixtures: int = 40) -> int:
    """Returns the number of match_results rows updated."""
    api_key = os.getenv("API_SPORTS_KEY", "")
    if not api_key:
        logger.warning("API_SPORTS_KEY not set — skipping corner/card fill")
        return 0

    sb = get_supabase_admin()

    pending: list[dict] = []
    start = 0
    while True:
        res = (
            sb.table("predictions").select("fixture_id, market")
            .eq("sport", sport).is_("is_correct", "null").in_("market", list(STAT_MARKETS))
            .order("id").range(start, start + 999).execute()
        )
        pending.extend(res.data or [])
        if len(res.data or []) < 1000:
            break
        start += 1000
    fixture_ids = sorted({p["fixture_id"] for p in pending})
    if not fixture_ids:
        return 0

    today = date.today().isoformat()
    candidates: list[dict] = []
    for i in range(0, len(fixture_ids), 200):
        chunk = fixture_ids[i:i + 200]
        fx = (
            sb.table("fixtures").select("fixture_id, match_date, league_key")
            .eq("sport", sport).in_("fixture_id", chunk).lt("match_date", today).execute()
        )
        rows = [r for r in (fx.data or []) if r.get("league_key") in LEAGUE_TIERS]
        if not rows:
            continue
        have = (
            sb.table("match_results").select("fixture_id, home_goals, total_corners")
            .eq("sport", sport).in_("fixture_id", [r["fixture_id"] for r in rows]).execute()
        )
        needs = {h["fixture_id"] for h in (have.data or [])
                 if h.get("home_goals") is not None and h.get("total_corners") is None}
        candidates.extend(r for r in rows if r["fixture_id"] in needs)

    candidates.sort(key=lambda r: r["match_date"], reverse=True)
    candidates = candidates[:max_fixtures]
    logger.info("Corner/card fill: %d fixture(s) queued", len(candidates))

    updated = 0
    with httpx.Client(timeout=30, headers={"x-apisports-key": api_key}) as client:
        for fx in candidates:
            try:
                resp = client.get(STATS_URL, params={"fixture": fx["fixture_id"]})
                body = resp.json()
            except Exception as exc:
                logger.warning("Stats request failed for %s: %s", fx["fixture_id"], exc)
                continue

            if body.get("errors"):
                # Quota spent (or plan restriction) — every further call would
                # fail the same way, so stop instead of retrying the queue.
                logger.warning("API-Sports stats stopped: %s", body["errors"])
                break

            teams = body.get("response") or []
            if len(teams) != 2:
                continue
            home, away = (t.get("statistics") or [] for t in teams)
            hc, ac = _stat(home, "Corner Kicks"), _stat(away, "Corner Kicks")
            yellow = _stat(home, "Yellow Cards") + _stat(away, "Yellow Cards")
            red = _stat(home, "Red Cards") + _stat(away, "Red Cards")

            sb.table("match_results").update({
                "home_corners": hc, "away_corners": ac, "total_corners": hc + ac,
                "total_yellow": yellow, "total_red": red, "total_cards": yellow + red,
            }).eq("sport", sport).eq("fixture_id", fx["fixture_id"]).execute()
            updated += 1

    logger.info("Corner/card fill: updated %d match_results row(s)", updated)
    return updated


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fill_corners_and_cards()
