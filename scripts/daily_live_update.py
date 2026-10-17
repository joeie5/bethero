"""
daily_live_update.py — The one job that keeps live fixtures/predictions/
accumulators fresh. Meant to run once a day (via Windows Task Scheduler,
see scripts/setup_daily_task.ps1) since API-Football's free tier only
exposes a short rolling date window — running this daily is what advances
the fixture calendar forward instead of it going stale.

Steps, in order (each is independently idempotent — upserts, not inserts):
  1. Fetch upcoming football fixtures from API-Football -> `fixtures` table.
  2. Generate/refresh ML predictions for all NS fixtures -> `predictions`.
  3. Best-effort: fetch real bookmaker odds for today/tomorrow's fixtures
     -> `fixture_odds` (free tier caps this at ~30 fixtures/day; the rest
     of the predictions still work, just without a computed edge).
  4. Re-run predictions for the fixtures that just got odds, so edge/
     confidence reflect the real market price.
  5. Rebuild today's accumulators ("Today's AI Tickets").
  6. Check results for finished matches: The Odds API first (one call per
     league, no meaningful daily cap), then API-Football as a fallback for
     leagues it doesn't cover — settling predictions and accumulator picks.
     This step exists here too (not just app/main.py's in-process 2h
     scheduler) because that scheduler only runs while the backend process
     stays continuously alive, which this environment's restart history
     shows can't be relied on.

Usage:
    python3 scripts/daily_live_update.py

Requires API_SPORTS_KEY, ODDS_API_KEY and MODEL_DIR to be set in the
environment (see start_backend.ps1 for the values already in use).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

import httpx

# stream=sys.stdout, not the logging module's stderr default — this runs
# unattended under run_daily_update.ps1's `*> $logFile` redirect, and
# PowerShell 5.1 wraps every stderr line from a native process (python3.exe)
# in a NativeCommandError object (confirmed live), which is pure noise here
# since these are routine operational logs, not actual crashes.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
logger = logging.getLogger("daily_live_update")

API_KEY = os.getenv("API_SPORTS_KEY", "")
ODDS_URL = "https://v3.football.api-sports.io/odds"
BOOKMAKER_PRIORITY = ["Pinnacle", "Bet365", "Marathonbet", "Betano"]
GOALS_LINES = {1.5, 2.5, 3.5}
CORNERS_LINES = {7.5, 9.5}


def _pick_bookmaker(bookmakers: list[dict], bet_name: str) -> dict | None:
    by_name = {bm["name"]: bm for bm in bookmakers}
    for pref in BOOKMAKER_PRIORITY:
        bm = by_name.get(pref)
        if bm and any(b["name"] == bet_name for b in bm["bets"]):
            return bm
    for bm in bookmakers:
        if any(b["name"] == bet_name for b in bm["bets"]):
            return bm
    return None


def _get_bet(bookmaker: dict, bet_name: str) -> dict | None:
    return next((b for b in bookmaker["bets"] if b["name"] == bet_name), None)


def _parse_line(value: str) -> float | None:
    m = re.search(r"[\d.]+", value)
    return float(m.group()) if m else None


def fetch_odds_for_date(supabase, known_ids: set[str], date_str: str) -> list[dict]:
    """Best-effort odds pull for one date. Free tier caps /odds at page<=3
    (~30 fixtures), so this only ever covers a subset — that's expected,
    not a bug (see app/routers/predictions.py's accumulator builder, which
    only needs a positive-edge pool, not full coverage)."""
    rows: list[dict] = []
    page, total_pages = 1, 1
    while page <= total_pages:
        for attempt in range(3):
            try:
                resp = httpx.get(ODDS_URL, headers={"x-apisports-key": API_KEY},
                                  params={"date": date_str, "page": page}, timeout=30)
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.info("odds request failed on page %d: %s", page, exc)
                time.sleep(2)
                continue
            if data.get("errors"):
                logger.info("odds API error on page %d: %s", page, data["errors"])
                time.sleep(2)
                continue
            break
        else:
            break
        total_pages = data.get("paging", {}).get("total", page)

        for entry in data.get("response", []):
            fid = str(entry["fixture"]["id"])
            if fid not in known_ids:
                continue
            bookmakers = entry.get("bookmakers", [])
            now_iso = datetime.now(timezone.utc).isoformat()

            bm = _pick_bookmaker(bookmakers, "Match Winner")
            if bm:
                vals = {v["value"]: float(v["odd"]) for v in _get_bet(bm, "Match Winner")["values"]}
                if {"Home", "Draw", "Away"} <= vals.keys():
                    rows.append({"sport": "football", "fixture_id": fid, "bookmaker": bm["name"],
                                 "market": "1X2", "line": None, "home_odds": vals["Home"],
                                 "draw_odds": vals["Draw"], "away_odds": vals["Away"], "pulled_at": now_iso})

            bm = _pick_bookmaker(bookmakers, "Both Teams Score")
            if bm:
                vals = {v["value"]: float(v["odd"]) for v in _get_bet(bm, "Both Teams Score")["values"]}
                if {"Yes", "No"} <= vals.keys():
                    rows.append({"sport": "football", "fixture_id": fid, "bookmaker": bm["name"],
                                 "market": "BTTS", "line": None, "home_odds": vals["Yes"],
                                 "away_odds": vals["No"], "pulled_at": now_iso})

            for bet_name, market, lines in (
                ("Goals Over/Under", "Over_Under_Goals", GOALS_LINES),
                ("Corners Over Under", "Over_Under_Corners", CORNERS_LINES),
            ):
                bm = _pick_bookmaker(bookmakers, bet_name)
                if not bm:
                    continue
                by_line: dict[float, dict] = {}
                for v in _get_bet(bm, bet_name)["values"]:
                    line = _parse_line(v["value"])
                    if line not in lines:
                        continue
                    side = "over" if v["value"].lower().startswith("over") else "under"
                    by_line.setdefault(line, {})[side] = float(v["odd"])
                for line, sides in by_line.items():
                    rows.append({"sport": "football", "fixture_id": fid, "bookmaker": bm["name"],
                                 "market": market, "line": line, "over_odds": sides.get("over"),
                                 "under_odds": sides.get("under"), "pulled_at": now_iso})

        page += 1
        time.sleep(1)
    return rows


def main() -> None:
    from app.database import get_supabase_admin
    from app.ingestion.fixture_fetcher import fetch_all_fixtures
    from app.ml.predictor import Predictor
    from app.ml.accumulator_builder import run_accumulator_job

    if not API_KEY:
        logger.error("API_SPORTS_KEY not set — aborting")
        return

    supabase = get_supabase_admin()
    predictor = Predictor(supabase)

    # Each step is independent and idempotent (upserts) — this runs
    # unattended once a day, so one step's failure (e.g. a transient
    # Supabase DNS blip, confirmed to happen intermittently on this setup)
    # must not skip the steps after it. Whatever succeeds today still moves
    # the fixture/prediction/odds state forward; a failed step just retries
    # naturally on tomorrow's run.
    try:
        logger.info("Step 1/6: fetching upcoming fixtures")
        inserted = asyncio.run(fetch_all_fixtures())
        logger.info("Fixtures upserted: %d", inserted)
    except Exception:
        logger.exception("Step 1/6 failed")

    try:
        logger.info("Step 2/6: generating predictions for upcoming fixtures")
        results = predictor.predict_upcoming(sport="football", hours_ahead=72)
        logger.info("Predictions generated: %d", len(results))
    except Exception:
        logger.exception("Step 2/6 failed")

    odds_rows: list[dict] = []
    try:
        logger.info("Step 3/6: fetching real bookmaker odds (best effort, free-tier capped)")
        known = (
            supabase.table("fixtures").select("fixture_id")
            .eq("sport", "football").eq("status", "NS").eq("provider", "api-sports")
            .execute()
        )
        known_ids = {r["fixture_id"] for r in known.data}
        today = datetime.now().strftime("%Y-%m-%d")
        odds_rows = fetch_odds_for_date(supabase, known_ids, today)
        if odds_rows:
            for i in range(0, len(odds_rows), 200):
                supabase.table("fixture_odds").insert(odds_rows[i:i + 200]).execute()
        logger.info("Odds rows inserted: %d", len(odds_rows))
    except Exception:
        logger.exception("Step 3/6 failed")

    try:
        if odds_rows:
            logger.info("Step 4/6: re-predicting fixtures that now have real odds")
            odds_fixture_ids = sorted({r["fixture_id"] for r in odds_rows})
            n = 0
            for fid in odds_fixture_ids:
                try:
                    n += len(predictor.predict_match("football", fid, persist=True))
                except Exception:
                    logger.exception("Re-predict failed for %s — skipping", fid)
            logger.info("Re-predicted %d fixture(s), %d predictions", len(odds_fixture_ids), n)
        else:
            logger.info("Step 4/6: skipped (no odds fetched)")
    except Exception:
        logger.exception("Step 4/6 failed")

    try:
        logger.info("Step 5/6: rebuilding accumulators")
        accas = run_accumulator_job()
        logger.info("Accumulators built: %d", len(accas))
    except Exception:
        logger.exception("Step 5/6 failed (non-fatal)")

    try:
        logger.info("Step 6/6: checking results for finished matches")
        from app.ingestion.odds_api_results import fetch_and_store_results
        from app.ingestion.result_fetcher import ResultFetcher
        stored = fetch_and_store_results(sport="football")
        logger.info("The Odds API: %d results stored", stored)
        # Corners/cards next, before ResultFetcher's fallback lookups: those
        # goals-only sources can never settle a Corners/Cards pick, and this
        # is the only call that can, so it gets first claim on the quota.
        from app.ingestion.match_stats_fetcher import fill_corners_and_cards
        filled = fill_corners_and_cards(sport="football")
        logger.info("Corner/card stats filled for %d match(es)", filled)
        ResultFetcher().run()
    except Exception:
        logger.exception("Step 6/6 failed")

    logger.info("Daily live update complete.")


if __name__ == "__main__":
    main()
