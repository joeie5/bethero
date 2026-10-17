"""
odds_api_results.py — Pulls completed match scores from The Odds API
(api.the-odds-api.com), one call per tracked league rather than one call
per fixture, and pre-populates `match_results` with them. This is the
primary result source: app.ingestion.result_fetcher.ResultFetcher already
prefers whatever's already in match_results over calling API-Football, so
running this first means API-Football's scarce 100/day quota is only ever
spent on leagues The Odds API doesn't cover.

Only home_goals/away_goals/ftr/btts/over15/over25 are populated — The Odds
API's /scores endpoint has no corner or card counts, so those columns are
left NULL (matching API-Football's own goals-only result shape). See
OutcomeResolver.resolve()'s None return for why that's safe: a Corners/
Cards prediction against a goals-only result is left unresolved, not
marked incorrect.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

import httpx

from app.database import get_supabase_admin
from app.ml.league_key_map import ODDS_API_LEAGUE_MAP

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
BASE_URL = "https://api.the-odds-api.com/v4"


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _leagues_with_pending_predictions(supabase, sport: str) -> set[str]:
    """Restricts the sweep to leagues that actually have something to
    settle. The free tier is 500 requests total PER MONTH (confirmed live:
    the remaining-requests header drops per call, not per day) — a blind
    sweep of all ~31 mapped leagues every run would burn ~930/month, nearly
    double budget. Most days only a handful of leagues have unsettled
    predictions at all, so this cuts real usage far below that ceiling."""
    pending = (
        supabase.table("predictions").select("fixture_id")
        .eq("sport", sport).is_("is_correct", "null")
        .execute()
    )
    fixture_ids = list({p["fixture_id"] for p in (pending.data or [])})
    if not fixture_ids:
        return set()

    leagues: set[str] = set()
    for i in range(0, len(fixture_ids), 500):
        chunk = fixture_ids[i:i + 500]
        fx = (
            supabase.table("fixtures").select("league_key")
            .eq("sport", sport).in_("fixture_id", chunk)
            .execute()
        )
        leagues.update(r["league_key"] for r in (fx.data or []) if r.get("league_key"))
    return leagues


def fetch_and_store_results(sport: str = "football", days_from: int = 3) -> int:
    """For each tracked league that both has unsettled predictions AND is
    covered by The Odds API, pulls recent completed scores and upserts them
    into match_results by matching team names against our `fixtures`
    table. Returns the number of results stored."""
    if not ODDS_API_KEY:
        logger.warning("ODDS_API_KEY not set — skipping The Odds API result check")
        return 0

    supabase = get_supabase_admin()
    stored = 0

    pending_leagues = _leagues_with_pending_predictions(supabase, sport)
    leagues_to_check = {k: v for k, v in ODDS_API_LEAGUE_MAP.items() if k in pending_leagues}
    logger.info("%d/%d mapped leagues have unsettled predictions — checking those only",
                len(leagues_to_check), len(ODDS_API_LEAGUE_MAP))

    for league_key, sport_key in leagues_to_check.items():
        try:
            resp = httpx.get(
                f"{BASE_URL}/sports/{sport_key}/scores",
                params={"apiKey": ODDS_API_KEY, "daysFrom": days_from},
                timeout=30,
            )
            if resp.status_code != 200:
                logger.warning("Odds API scores error for %s (%s): %s", league_key, sport_key, resp.text[:200])
                continue
            games = resp.json()
        except Exception as exc:
            logger.warning("Odds API request failed for %s: %s", league_key, exc)
            continue

        completed = [g for g in games if g.get("completed") and g.get("scores")]
        if not completed:
            continue

        # Candidate fixtures for this league — narrowed so name-matching
        # doesn't have to scan the whole table.
        fx_res = (
            supabase.table("fixtures")
            .select("fixture_id, home_team, away_team, match_date")
            .eq("sport", sport).eq("league_key", league_key)
            .eq("status", "NS")
            .execute()
        )
        # NS-only would miss fixtures whose status is stuck stale (a known
        # separate issue), so also pull anything from the last few days
        # regardless of status.
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_from + 1)).date().isoformat()
        fx_res2 = (
            supabase.table("fixtures")
            .select("fixture_id, home_team, away_team, match_date")
            .eq("sport", sport).eq("league_key", league_key)
            .gte("match_date", cutoff)
            .execute()
        )
        candidates = {r["fixture_id"]: r for r in (fx_res.data or []) + (fx_res2.data or [])}
        by_names: dict[tuple[str, str], dict] = {
            (_normalize_name(r["home_team"]), _normalize_name(r["away_team"])): r
            for r in candidates.values()
        }

        for g in completed:
            home_norm = _normalize_name(g.get("home_team", ""))
            away_norm = _normalize_name(g.get("away_team", ""))
            fx = by_names.get((home_norm, away_norm))
            if fx is None:
                continue

            scores = {_normalize_name(s["name"]): s["score"] for s in g["scores"]}
            hg_raw = scores.get(home_norm)
            ag_raw = scores.get(away_norm)
            if hg_raw is None or ag_raw is None:
                continue
            try:
                hg, ag = int(hg_raw), int(ag_raw)
            except (TypeError, ValueError):
                continue

            row = {
                "sport": sport,
                "fixture_id": fx["fixture_id"],
                "home_team": fx["home_team"],
                "away_team": fx["away_team"],
                "status": "finished",
                "home_goals": hg,
                "away_goals": ag,
                "ftr": "H" if hg > ag else ("A" if hg < ag else "D"),
                "btts": bool(hg > 0 and ag > 0),
                "over15": bool((hg + ag) > 1.5),
                "over25": bool((hg + ag) > 2.5),
                "settled_at": datetime.now(timezone.utc).isoformat(),
            }
            supabase.table("match_results").upsert(row, on_conflict="sport,fixture_id").execute()
            supabase.table("fixtures").update({"status": "FT"}).eq("sport", sport).eq("fixture_id", fx["fixture_id"]).execute()
            stored += 1

    logger.info("The Odds API: stored %d results across %d leagues checked", stored, len(leagues_to_check))
    return stored


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fetch_and_store_results()
