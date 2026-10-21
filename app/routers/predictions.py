"""
predictions.py — FastAPI router for match predictions and accumulators.
"""

from __future__ import annotations

import logging
from typing import List, Optional
from datetime import datetime, timezone

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from app.database import get_supabase_admin
from app.schemas.schemas import PredictionOut, AccumulatorOut, MatchOut
from app.redis_client import get_redis
from app.ml.outcome_resolver import resolve_actual_outcome

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/predictions",
    tags=["Predictions"]
)

CURRENT_SEASON = 2026

@router.get("/accumulators/today")
async def get_today_accumulators(background_tasks: BackgroundTasks):
    """
    Fetch all accumulators generated in the last 24 hours.
    Triggers generation if empty.
    """
    supabase = get_supabase_admin()

    now = datetime.now(timezone.utc)
    day_ago = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    try:
        res = (
            supabase.table("accumulators")
            .select("*, legs:accumulator_picks(*)")
            .gte("created_at", day_ago)
            .order("created_at", desc=True)
            .execute()
        )
        
        if res.data:
            # Filter to one per type
            seen_types = set()
            filtered = []
            for acca in res.data:
                acca_type = acca.get("acc_type")
                if acca_type not in seen_types:
                    filtered.append(acca)
                    seen_types.add(acca_type)
            
            return {"data": filtered, "count": len(filtered), "source": "database"}
            
        # check if already generating (Redis is just a duplicate-trigger
        # guard here — treat "unavailable" the same as "not in progress"
        # rather than failing the whole request over a cache miss)
        try:
            is_generating = get_redis().get("acca_generation_in_progress")
        except Exception:
            is_generating = None
        if is_generating:
            return {
                "status": "generating", 
                "message": "We are fetching real data. It will be loaded once it is completed.",
                "data": [],
                "count": 0
            }
        
        # Trigger generation
        from app.ml.accumulator_builder import run_accumulator_job
        background_tasks.add_task(run_accumulator_job)
        
        # Set flag in redis for 15 mins (best-effort — a cache miss here just
        # means a duplicate generation trigger next call, not a failure)
        try:
            get_redis().setex("acca_generation_in_progress", 900, "true")
        except Exception:
            pass
        
        return {
            "status": "generating",
            "message": "We are fetching real data. It will be loaded once it is completed.",
            "data": [],
            "count": 0
        }
    except Exception as exc:
        logger.error("Error fetching today's accumulators: %s", exc)
        return {"data": [], "count": 0, "error": str(exc)}

@router.get("/accumulators/{acca_type}")
async def get_accumulators_by_type(acca_type: str, background_tasks: BackgroundTasks):
    """
    Fetch all accumulators of a specific type (3odds, 5odds, 10odds).
    """
    if acca_type not in ["3odds", "5odds", "10odds"]:
        raise HTTPException(status_code=400, detail="Invalid accumulator type.")
        
    supabase = get_supabase_admin()

    try:
        res = (
            supabase.table("accumulators")
            .select("*, legs:accumulator_picks(*)")
            .eq("acc_type", acca_type)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        data = res.data or []

        if not data:
            # check if today's accas exist at all
            now = datetime.now(timezone.utc)
            day_ago = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

            check_any = supabase.table("accumulators").select("id").gte("created_at", day_ago).limit(1).execute()

            if not check_any.data:
                try:
                    is_generating = get_redis().get("acca_generation_in_progress")
                except Exception:
                    is_generating = None
                if is_generating:
                    return {
                        "status": "generating",
                        "message": "We are fetching real data. It will be loaded once it is completed.",
                        "data": [],
                        "count": 0
                    }

                # Trigger generation
                from app.ml.accumulator_builder import run_accumulator_job
                background_tasks.add_task(run_accumulator_job)
                try:
                    get_redis().setex("acca_generation_in_progress", 900, "true")
                except Exception:
                    pass
                
                return {
                    "status": "generating",
                    "message": "We are fetching real data. It will be loaded once it is completed.",
                    "data": [],
                    "count": 0
                }
                
        return {"data": data, "count": len(data)}
    except Exception as exc:
        logger.error("Error fetching %s accumulators: %s", acca_type, exc)
        raise HTTPException(status_code=500, detail=f"Failed to fetch {acca_type} accumulators.")

@router.get("/longshots")
async def get_longshots(sport: str = "football", limit: int = 30):
    """
    Real long-shot picks (low model probability, by definition low-odds-of-
    hitting) from completed matches this season, paired with what actually
    happened. Football only — no other sport has trained models yet, so a
    non-football `sport` returns an empty list (the client shows a "coming
    soon" state for those rather than treating it as an error).
    """
    if sport not in ("football", "all"):
        return {"best_bet": None, "data": [], "count": 0}

    supabase = get_supabase_admin()
    try:
        # Query each market separately (not one combined query ordered by
        # generated_at) — otherwise whichever market was generated last
        # fills the whole result set, since all its rows share the most
        # recent timestamps.
        db_markets = ["BTTS", "Cards", "Over_Under_Corners", "Over_Under_Goals", "1X2"]
        preds: list[dict] = []
        for m in db_markets:
            r = (
                supabase.table("predictions")
                .select("*")
                .eq("sport", "football")
                .eq("market", m)
                .lt("model_probability", 0.40)
                .order("model_probability", desc=False)
                .limit(40)
                .execute()
            )
            preds.extend(r.data or [])
        if not preds:
            return {"best_bet": None, "data": [], "count": 0}

        fixture_ids = list({p["fixture_id"] for p in preds})
        fx_res = (
            supabase.table("fixtures")
            .select("fixture_id,home_team,away_team,league_name,match_date,status")
            .eq("sport", "football")
            .eq("season", CURRENT_SEASON)
            .in_("fixture_id", fixture_ids)
            .execute()
        )
        fixtures_by_id = {f["fixture_id"]: f for f in (fx_res.data or [])}

        mr_res = (
            supabase.table("match_results")
            .select("fixture_id,btts,total_cards,total_corners,home_goals,away_goals,ftr")
            .eq("sport", "football")
            .in_("fixture_id", fixture_ids)
            .execute()
        )
        results_by_id = {r["fixture_id"]: r for r in (mr_res.data or [])}

        rows = []
        for p in preds:
            fx = fixtures_by_id.get(p["fixture_id"])
            if not fx or fx.get("status") != "FT":
                continue
            result = results_by_id.get(p["fixture_id"])
            actual = resolve_actual_outcome(p["market"], p["selection"], result) if result else None
            if actual is None:
                continue
            odds = p.get("odds") or (round(1.0 / p["model_probability"], 2) if p["model_probability"] else None)
            rows.append({
                "fixture_id": p["fixture_id"],
                "sport": "football",
                "home_team": fx.get("home_team"),
                "away_team": fx.get("away_team"),
                "league": fx.get("league_name"),
                "match_date": fx.get("match_date"),
                "market": p["market"],
                "selection": p["selection"],
                "model_probability": p["model_probability"],
                "odds": odds,
                "predicted_outcome": p["selection"],
                "actual_outcome": actual,
                "was_correct": p["selection"] == actual,
            })

        # Diversity cap (mirrors CLAUDE.md's max-2-legs-per-market rule for
        # accumulators) — otherwise 1X2 "Draw" alone floods the list, since
        # its baseline probability sits ~33-40% for any three-way market,
        # crowding out genuinely more extreme longshots from other markets.
        rows.sort(key=lambda r: r["odds"] or 0, reverse=True)
        per_market_cap = 6
        market_counts: dict[str, int] = {}
        diverse_rows = []
        for r in rows:
            c = market_counts.get(r["market"], 0)
            if c >= per_market_cap:
                continue
            market_counts[r["market"]] = c + 1
            diverse_rows.append(r)
        rows = diverse_rows[:limit]

        best_bet = None
        edged = [p for p in preds if p.get("edge")]
        if edged:
            best_pred = max(edged, key=lambda p: p["edge"])
            fx = fixtures_by_id.get(best_pred["fixture_id"])
            result = results_by_id.get(best_pred["fixture_id"])
            if fx and result:
                actual = resolve_actual_outcome(best_pred["market"], best_pred["selection"], result)
                best_bet = {
                    "fixture_id": best_pred["fixture_id"],
                    "home_team": fx.get("home_team"),
                    "away_team": fx.get("away_team"),
                    "league": fx.get("league_name"),
                    "match_date": fx.get("match_date"),
                    "market": best_pred["market"],
                    "selection": best_pred["selection"],
                    "model_probability": best_pred["model_probability"],
                    "odds": best_pred.get("odds"),
                    "edge": best_pred.get("edge"),
                    "actual_outcome": actual,
                    "was_correct": best_pred["selection"] == actual,
                }

        return {"best_bet": best_bet, "data": rows, "count": len(rows)}
    except Exception as exc:
        logger.error("Error building longshots: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch longshots.")

@router.get("/fixtures/{sport}")
async def get_sport_fixtures(sport: str):
    """
    Fetch upcoming fixtures for a specific sport.
    """
    supabase = get_supabase_admin()
    try:
        now = datetime.now(timezone.utc).isoformat()

        res = (
            supabase.table("fixtures")
            .select("*")
            .eq("sport", sport)
            .eq("status", "NS")
            .gte("match_date", now)
            .order("match_date", desc=False)
            .limit(50)
            .execute()
        )
        return res.data or []
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching fixtures for %s: %s", sport, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch fixtures.")

@router.get("/match/{fixture_id}")
async def get_match_prediction(fixture_id: str, sport: str = "football"):
    """
    Fetch a specific match and all its associated predictions.
    """
    supabase = get_supabase_admin()
    try:
        # Fetch match — composite (sport, fixture_id) key, not a bare integer id
        match_res = (
            supabase.table("fixtures")
            .select("*")
            .eq("sport", sport)
            .eq("fixture_id", fixture_id)
            .maybe_single()
            .execute()
        )
        if not match_res or not match_res.data:
            raise HTTPException(status_code=404, detail="Match not found.")

        # Fetch predictions
        pred_res = (
            supabase.table("predictions")
            .select("*")
            .eq("sport", sport)
            .eq("fixture_id", fixture_id)
            .execute()
        )

        return {
            "match": match_res.data,
            "predictions": pred_res.data or []
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching match data for %s/%s: %s", sport, fixture_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch match data.")


# Display order/labels for the match-stats UI — only fields API-Sports'
# free-tier /fixtures/statistics endpoint actually returns (confirmed live
# 2026-10-21). Throw-ins/Crosses/Goal kicks are NOT in that response, so
# they're deliberately left out rather than faked.
_STAT_DISPLAY = [
    ("expected_goals", "Expected goals (xG)", "decimal"),
    ("Shots on Goal", "Shots on target", "int"),
    ("Shots off Goal", "Shots off target", "int"),
    ("Blocked Shots", "Blocked Shots", "int"),
    ("Ball Possession", "Possession (%)", "percent"),
    ("Corner Kicks", "Corner Kicks", "int"),
    ("Offsides", "Offsides", "int"),
    ("Fouls", "Fouls", "int"),
    ("Yellow Cards", "Yellow Cards", "int"),
    ("Goalkeeper Saves", "Goalkeeper Saves", "int"),
    ("Passes %", "Pass accuracy (%)", "percent"),
]


def _parse_stat_value(raw):
    if raw is None:
        return None
    if isinstance(raw, str) and raw.endswith("%"):
        raw = raw[:-1]
    try:
        f = float(raw)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def _build_stats_rows(raw_stats: list) -> list[dict]:
    """raw_stats is API-Sports' /fixtures/statistics `response` array: one
    entry per team, each with its own `statistics` list of {type, value}."""
    if not raw_stats or len(raw_stats) < 2:
        return []
    by_team = [
        {s["type"]: s.get("value") for s in (team.get("statistics") or [])}
        for team in raw_stats[:2]
    ]
    rows = []
    for api_key, label, _kind in _STAT_DISPLAY:
        home_val = _parse_stat_value(by_team[0].get(api_key))
        away_val = _parse_stat_value(by_team[1].get(api_key))
        if home_val is None and away_val is None:
            continue
        rows.append({"label": label, "home": home_val, "away": away_val})
    return rows


@router.get("/match/{fixture_id}/stats")
async def get_match_stats(fixture_id: str, sport: str = "football"):
    """Full match-stats comparison (shots, possession, fouls, cards, xG,
    etc.) for the match-detail "Stats" view. API-Sports' statistics
    endpoint is quota-limited, so the raw response is fetched once and
    cached in match_results.raw_stats — every later view is a DB read, not
    a fresh API call.

    Only ever available for fixtures API-Sports itself knows about
    (provider == 'api-sports', a real numeric fixture_id) — fixtures
    inserted from the football-data.co.uk backfill (provider ==
    'football-data', synthetic 'fd-...' ids) have no matching API-Sports
    fixture to query, same reason their Corners/Cards markets can't settle
    either. Reported as stats_available=false rather than erroring."""
    supabase = get_supabase_admin()

    fx_res = (
        supabase.table("fixtures").select("*")
        .eq("sport", sport).eq("fixture_id", fixture_id)
        .maybe_single().execute()
    )
    if not fx_res or not fx_res.data:
        raise HTTPException(status_code=404, detail="Match not found.")
    fixture = fx_res.data

    mr_res = (
        supabase.table("match_results").select("*")
        .eq("sport", sport).eq("fixture_id", fixture_id)
        .maybe_single().execute()
    )
    match_result = mr_res.data if mr_res else None

    header = {
        "fixture_id": fixture_id,
        "home_team": fixture.get("home_team"),
        "away_team": fixture.get("away_team"),
        "home_team_logo": fixture.get("home_team_logo"),
        "away_team_logo": fixture.get("away_team_logo"),
        "status": fixture.get("status"),
        "home_goals": match_result.get("home_goals") if match_result else None,
        "away_goals": match_result.get("away_goals") if match_result else None,
    }

    if match_result and match_result.get("raw_stats"):
        return {**header, "stats_available": True, "stats": _build_stats_rows(match_result["raw_stats"])}

    can_query_api_sports = (
        fixture.get("provider") == "api-sports"
        and fixture.get("status") == "FT"
        and str(fixture_id).isdigit()
    )
    if not can_query_api_sports:
        return {**header, "stats_available": False, "stats": []}

    api_key = os.getenv("API_SPORTS_KEY", "")
    if not api_key:
        return {**header, "stats_available": False, "stats": []}

    try:
        resp = httpx.get(
            "https://v3.football.api-sports.io/fixtures/statistics",
            headers={"x-apisports-key": api_key},
            params={"fixture": fixture_id},
            timeout=20,
        )
        data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("API-Sports statistics request failed for %s: %s", fixture_id, exc)
        return {**header, "stats_available": False, "stats": []}

    raw_stats = data.get("response") or []
    if not raw_stats:
        return {**header, "stats_available": False, "stats": []}

    try:
        if match_result:
            supabase.table("match_results").update({"raw_stats": raw_stats}).eq("sport", sport).eq("fixture_id", fixture_id).execute()
        else:
            supabase.table("match_results").upsert(
                {"sport": sport, "fixture_id": fixture_id, "raw_stats": raw_stats},
                on_conflict="sport,fixture_id",
            ).execute()
    except Exception as exc:
        logger.warning("Failed to cache raw_stats for %s: %s", fixture_id, exc)

    return {**header, "stats_available": True, "stats": _build_stats_rows(raw_stats)}
