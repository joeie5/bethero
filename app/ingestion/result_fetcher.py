"""
result_fetcher.py — Resolves unsettled predictions against actual match
results, feeding the retrain counter.

Responsibilities
----------------
1. Poll Supabase every 2 hours for all predictions with is_correct IS NULL
   whose fixture's match_date is in the past
2. Fetch actual results from API-Sports if not already in match_results
3. Upsert the real outcome into match_results (sport, fixture_id) — the
   live schema, not the abandoned `matches`/`match_stats` tables this file
   used to target (confirmed gone from the DB: PostgREST returns PGRST205
   "Perhaps you meant... match_results").
4. Update predictions.is_correct / actual_outcome / settled_at
5. When 200+ new resolutions accumulate, set a retraining flag in Redis

APScheduler interval: every 2 hours
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import httpx

from app.config import settings
from app.database import get_supabase_admin
from app.redis_client import get_redis, cache_set, cache_get

logger = logging.getLogger(__name__)

RETRAIN_FLAG_KEY     = "ml:retrain_needed"
RETRAIN_COUNTER_KEY  = "ml:new_results_since_last_train"
RETRAIN_THRESHOLD    = 200

API_SPORTS_SPORT_MAP: dict[str, str] = {
    "football":   "football",
    "basketball": "basketball",
    "tennis":     "tennis",
    "nfl":        "american-football",
    "cricket":    "cricket",
    "nhl":        "hockey",
    "mlb":        "baseball",
}


class QuotaExhausted(Exception):
    """API-Sports' daily request quota is spent."""


def _api_retry(fn):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError,)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )(fn)


class ResultAPIClient:

    def __init__(self):
        self._http = httpx.Client(
            timeout=15.0,
            headers={
                "x-rapidapi-host": "v3.football.api-sports.io",
                "x-rapidapi-key":  settings.API_SPORTS_KEY,
            },
        )

    @_api_retry
    def get_fixture(self, sport_slug: str, fixture_id: str) -> dict | None:
        """Look up one fixture by its real API-Sports id — fixture_id in our
        schema IS the API-Sports id (see fixture_fetcher.map_football_fixture),
        so this is a direct, precise lookup, not a fuzzy name/date search."""
        sport = API_SPORTS_SPORT_MAP.get(sport_slug, "football")
        base  = f"https://v3.{sport}.api-sports.io"
        resp  = self._http.get(f"{base}/fixtures", params={"id": fixture_id})
        resp.raise_for_status()
        body = resp.json()
        # API-Sports reports an exhausted daily quota as HTTP 200 with an
        # `errors` body (confirmed live on /fixtures/statistics), not always
        # a 429 — without this the caller reads it as "no result" and keeps
        # spending a request per prediction against a spent quota.
        if isinstance(body.get("errors"), dict) and "requests" in body["errors"]:
            raise QuotaExhausted(body["errors"]["requests"])
        items = body.get("response", [])
        return items[0] if items else None

    def close(self):
        self._http.close()


# ─────────────────────────── Outcome Resolver ──────────────────────────────

class OutcomeResolver:
    """
    Determines whether a prediction was correct given the real match_results
    row. Matches predictor.py's actual db_market strings exactly — the prior
    version string-matched against markets ("OVER/UNDER", "1X2") that never
    matched what predictor.py actually emits (Over_Under_Goals, 1x2, ...),
    so most markets silently resolved INCORRECT regardless of outcome.
    """

    @staticmethod
    def resolve(db_market: str, selection: str, result: dict) -> bool | None:
        """Returns True (correct) / False (incorrect) / None (can't tell —
        the result source doesn't carry this stat, e.g. a goals-only feed
        like API-Sports's basic fixture result or The Odds API's /scores
        endpoint has no corner/card counts). Callers must leave a None
        prediction unresolved rather than writing it as incorrect — a
        missing stat is not evidence the pick lost. `result` is a
        match_results row: home_goals, away_goals, btts, total_corners,
        total_cards, ftr."""
        market = (db_market or "").strip()
        sel    = (selection or "").strip().upper()
        hg, ag = result.get("home_goals"), result.get("away_goals")

        try:
            if market == "BTTS":
                both = bool(hg > 0 and ag > 0)
                return (sel == "YES") == both

            if market == "1X2":
                ftr = result.get("ftr")
                actual = {"H": "HOME", "D": "DRAW", "A": "AWAY"}.get(ftr)
                return sel == actual

            if market == "Double_Chance":
                ftr = result.get("ftr")
                covers = {
                    "1X": {"H", "D"}, "X2": {"D", "A"}, "12": {"H", "A"},
                }.get(sel, set())
                return ftr in covers

            if market == "Over_Under_Goals":
                direction, line = sel.split()
                total = (hg or 0) + (ag or 0)
                return total > float(line) if direction == "OVER" else total < float(line)

            if market == "Over_Under_Corners":
                total_corners = result.get("total_corners")
                if total_corners is None:
                    return None
                direction, line = sel.split()
                return total_corners > float(line) if direction == "OVER" else total_corners < float(line)

            if market == "Cards":
                total_cards = result.get("total_cards")
                if total_cards is None:
                    return None
                direction, line = sel.split()
                return total_cards > float(line) if direction == "OVER" else total_cards < float(line)

        except Exception as exc:
            logger.warning("Outcome resolve error (market=%s, sel=%s): %s", market, selection, exc)
            return None

        return None


# ─────────────────────────── Result Fetcher ────────────────────────────────

class ResultFetcher:

    def __init__(self):
        self.supabase = get_supabase_admin()
        self.api      = ResultAPIClient()
        self._new_resolutions = 0
        # Set once API-Sports answers 429 (daily quota spent). From then on
        # this run only settles predictions whose result is already cached
        # in match_results — before this, every remaining fixture burned
        # 3 retries against a maxed-out quota, so the job crawled through
        # the backlog and never reached the predictions that needed no API
        # call at all (confirmed live: 223 Sep 18 predictions had a cached
        # result but stayed unsettled).
        self._api_exhausted = False
        self._marked_ft: set[tuple[str, str]] = set()

    def run(self) -> None:
        logger.info("🔍 ResultFetcher starting — %s UTC", datetime.now(timezone.utc).isoformat())
        pending = self._fetch_pending_predictions()
        logger.info("Found %d unresolved predictions to check", len(pending))

        for pred in pending:
            try:
                self._resolve_prediction(pred)
            except Exception as exc:
                logger.error("Error resolving prediction %s: %s", pred.get("id"), exc, exc_info=True)

        if self._new_resolutions > 0:
            self._update_retrain_counter(self._new_resolutions)

        logger.info("✅ ResultFetcher done — resolved %d predictions", self._new_resolutions)
        self._new_resolutions = 0

    # ── Pending predictions ─────────────────────────────────────

    def _fetch_pending_predictions(self) -> list[dict]:
        """
        Predictions not yet settled (is_correct IS NULL), whose fixture is
        due to be checked: status='FT' (fixture_fetcher.py sets this once
        API-Sports reports the match finished) OR match_date is a prior
        calendar day (catch-all for anything whose status update was
        missed). fixtures.match_date is a bare `date` column, not a
        timestamp (kickoff_time is separately `time without time zone`,
        never combined) — confirmed live: comparing it against a full ISO
        datetime silently failed to match same-day finished fixtures, so
        status='FT' is the primary signal here, not match_date. No FK-based
        embed to fixtures (composite sport+fixture_id keys, not a declared
        PostgREST relationship) — fetched and joined in Python instead.
        """
        from datetime import date as _date
        today = _date.today().isoformat()

        # PostgREST caps a response at 1000 rows by default, and this table
        # can easily hold 3000+ unsettled rows — confirmed live. An
        # unordered .range() also gives an unstable row set between calls
        # (Postgres makes no ordering guarantee without one), so both the
        # pagination and the explicit .order() below are required, not
        # just the pagination alone (see app/routers/tiers.py's
        # _day_calendar for the same bug pattern found and fixed there).
        preds: list[dict] = []
        start = 0
        PAGE = 1000
        while True:
            pred_res = (
                self.supabase.table("predictions")
                .select("id, sport, fixture_id, market, selection")
                .is_("is_correct", "null")
                .order("id")
                .range(start, start + PAGE - 1)
                .execute()
            )
            page = pred_res.data or []
            preds.extend(page)
            if len(page) < PAGE:
                break
            start += PAGE
        if not preds:
            return []

        pairs = {(p["sport"], p["fixture_id"]) for p in preds}
        fixture_ids = [fid for _, fid in pairs]
        fx_rows: list[dict] = []
        for i in range(0, len(fixture_ids), 500):
            chunk = fixture_ids[i:i + 500]
            fx_res = (
                self.supabase.table("fixtures")
                .select("sport, fixture_id, match_date, status")
                .in_("fixture_id", chunk)
                .or_(f"status.eq.FT,match_date.lt.{today}")
                .execute()
            )
            fx_rows.extend(fx_res.data or [])
        due_keys = {(r["sport"], r["fixture_id"]) for r in fx_rows}

        return [p for p in preds if (p["sport"], p["fixture_id"]) in due_keys]

    # ── Core resolution ─────────────────────────────────────────

    def _resolve_prediction(self, pred: dict) -> None:
        sport, fixture_id = pred["sport"], pred["fixture_id"]

        result = self._get_or_fetch_result(sport, fixture_id)
        if result is None:
            logger.debug("No result yet for %s/%s", sport, fixture_id)
            return

        # A stored result means the match is over — fixtures.status is only
        # ever set at ingestion, so without this a played match stays NS/LIVE
        # forever (confirmed live: 105 of Sep 18's fixtures).
        if (sport, fixture_id) not in self._marked_ft:
            self.supabase.table("fixtures").update({"status": "FT"}) \
                .eq("sport", sport).eq("fixture_id", fixture_id).execute()
            self._marked_ft.add((sport, fixture_id))

        is_correct = OutcomeResolver.resolve(pred["market"], pred["selection"], result)
        if is_correct is None:
            # Result source doesn't carry the stat this market needs (e.g. a
            # goals-only feed for a Corners/Cards pick) — leave unresolved
            # rather than writing a false verdict; a later source with the
            # full stat line can still settle it properly.
            logger.debug("Cannot resolve prediction %s (market=%s) — source missing required stat",
                         pred["id"], pred["market"])
            return

        actual_outcome = {"H": "Home", "D": "Draw", "A": "Away"}.get(result.get("ftr"), result.get("ftr"))

        self.supabase.table("predictions").update({
            "is_correct":    is_correct,
            "actual_outcome": actual_outcome,
            "settled_at":    datetime.now(timezone.utc).isoformat(),
        }).eq("id", pred["id"]).execute()

        self._resolve_accumulator_picks(pred["id"], is_correct, actual_outcome)

        self._new_resolutions += 1
        logger.debug("Prediction %s → %s", pred["id"], "CORRECT" if is_correct else "INCORRECT")

    # ── Accumulator resolution ──────────────────────────────────

    def _resolve_accumulator_picks(self, prediction_id: int, is_correct: bool, actual_value: str) -> None:
        """
        accumulator_picks (not accumulator_legs — that table doesn't exist in
        the live schema; accumulator_builder.py already writes picks here,
        keyed by prediction_id) references predictions.id directly, so a
        settled prediction resolves its picks the same way.
        """
        picks_res = (
            self.supabase.table("accumulator_picks")
            .select("id, accumulator_id")
            .eq("prediction_id", prediction_id)
            .execute()
        )
        picks = picks_res.data or []
        if not picks:
            return

        self.supabase.table("accumulator_picks").update({
            "outcome":      "CORRECT" if is_correct else "INCORRECT",
            "actual_value": actual_value,
            "settled":      True,
            "updated_at":   datetime.now(timezone.utc).isoformat(),
        }).eq("prediction_id", prediction_id).execute()

        for acca_id in {p["accumulator_id"] for p in picks}:
            self._recompute_accumulator(acca_id)

    def _recompute_accumulator(self, accumulator_id: int) -> None:
        """
        WON only if every pick is settled AND correct; LOST as soon as any
        pick is settled INCORRECT (no need to wait for the rest); otherwise
        left pending — matches accumulators.status/outcome/settled shape.
        """
        picks_res = (
            self.supabase.table("accumulator_picks")
            .select("outcome, settled")
            .eq("accumulator_id", accumulator_id)
            .execute()
        )
        picks = picks_res.data or []
        if not picks:
            return

        if any(p["settled"] and p["outcome"] == "INCORRECT" for p in picks):
            outcome = "LOST"
        elif all(p["settled"] and p["outcome"] == "CORRECT" for p in picks):
            outcome = "WON"
        else:
            return   # still pending — some picks unresolved, none lost yet

        self.supabase.table("accumulators").update({
            "status":     "settled",
            "outcome":    outcome,
            "settled":    True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", accumulator_id).execute()
        logger.debug("Accumulator %s → %s", accumulator_id, outcome)

    def _get_or_fetch_result(self, sport: str, fixture_id: str) -> dict | None:
        """Prefer whatever's already in match_results; fall back to a live
        API-Sports lookup by the real fixture_id and upsert what we find."""
        res = (
            self.supabase.table("match_results")
            .select("home_goals, away_goals, ftr, total_corners, total_cards, status")
            .eq("sport", sport).eq("fixture_id", fixture_id)
            .execute()
        )
        rows = res.data or []
        if rows and rows[0].get("home_goals") is not None:
            return rows[0]

        if self._api_exhausted:
            return None
        try:
            api_result = self.api.get_fixture(sport, fixture_id)
        except QuotaExhausted:
            logger.warning("API-Sports daily quota exhausted — settling from cached results only for the rest of this run")
            self._api_exhausted = True
            return None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("API-Sports rate-limited (429) — settling from cached results only for the rest of this run")
                self._api_exhausted = True
                return None
            raise
        if not api_result:
            return None

        status_short = api_result.get("fixture", {}).get("status", {}).get("short")
        if status_short != "FT":
            return None

        goals = api_result.get("goals", {})
        hg, ag = goals.get("home"), goals.get("away")
        if hg is None or ag is None:
            return None

        teams = api_result.get("teams", {})
        row = {
            "sport":       sport,
            "fixture_id":  fixture_id,
            "home_team":   (teams.get("home") or {}).get("name", ""),
            "away_team":   (teams.get("away") or {}).get("name", ""),
            "status":      "finished",
            "home_goals":  hg,
            "away_goals":  ag,
            # total_goals / goal_diff are DB-generated columns — confirmed live
            "ftr":         "H" if hg > ag else ("A" if hg < ag else "D"),
            "btts":        bool(hg > 0 and ag > 0),
            "over15":      bool((hg + ag) > 1.5),
            "over25":      bool((hg + ag) > 2.5),
            "settled_at":  datetime.now(timezone.utc).isoformat(),
        }
        self.supabase.table("match_results").upsert(row, on_conflict="sport,fixture_id").execute()
        return row

    # ── Retraining flag ─────────────────────────────────────────

    def _update_retrain_counter(self, count: int) -> None:
        """
        Increments a Redis counter. When it crosses RETRAIN_THRESHOLD,
        sets a flag that the ML service polls to trigger retraining.
        """
        try:
            redis = get_redis()
            new_count = redis.incrby(RETRAIN_COUNTER_KEY, count)
            logger.info("Retrain counter: %d / %d", new_count, RETRAIN_THRESHOLD)
            if new_count >= RETRAIN_THRESHOLD:
                redis.set(RETRAIN_FLAG_KEY, "1")
                redis.set(RETRAIN_COUNTER_KEY, "0")   # reset
                logger.info(
                    "🚀 Retraining flag SET — %d new results accumulated", new_count
                )
        except Exception as exc:
            logger.error("Failed to update retrain counter: %s", exc)

    def close(self):
        self.api.close()


# ─────────────────────────── APScheduler Entry Point ───────────────────────

def run_result_scheduler() -> None:
    """
    Starts a BackgroundScheduler that fires ResultFetcher.run() every 2 hours.
    Returns the scheduler so callers can integrate it with other schedulers.
    """
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        lambda: ResultFetcher().run(),
        trigger=IntervalTrigger(hours=2),
        id="result_fetcher",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("📅 ResultFetcher scheduler started — interval: 2h")
    return scheduler


if __name__ == "__main__":
    run_result_scheduler()
