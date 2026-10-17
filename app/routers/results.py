from __future__ import annotations
import logging
from typing import List, Optional, Dict
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from app.database import get_supabase_admin
from app.ml.outcome_resolver import resolve_actual_outcome

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/results",
    tags=["Results"]
)

_MAIN_TIER_LEAGUES = [
    "E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3",
    "D1", "D2", "SP1", "SP2", "I1", "I2", "F1", "F2",
    "N1", "B1", "P1", "T1", "G1",
]


def _season_week_number(target_date: str, season_start_iso_week: tuple[int, int]) -> int | None:
    """Season-relative week number (1, 2, ...) for a ticket's target_date,
    based on ISO (year, week) distance from the season's first week."""
    if not target_date:
        return None
    d = date.fromisoformat(str(target_date)[:10])
    iso = d.isocalendar()
    start_year, start_week = season_start_iso_week
    # Simple week-count difference — good enough within one season, which
    # never spans a year boundary's ISO-week wraparound in a way that
    # breaks this for the handful of weeks we show.
    return (iso[0] - start_year) * 52 + (iso[1] - start_week) + 1


@router.get("/history")
async def get_results_history():
    supabase = get_supabase_admin()
    try:
        result = supabase.table("accumulators")\
            .select("*, legs:accumulator_picks(*)")\
            .order("target_date", desc=True)\
            .limit(100)\
            .execute()
        accas = result.data or []

        # Season week numbering is relative to this season's actual first
        # match — computed once per request rather than hardcoded, so it
        # keeps working if/when a new season's data is loaded.
        season_start_res = (
            supabase.table("fixtures")
            .select("match_date")
            .eq("sport", "football")
            .eq("status", "FT")
            .eq("season", 2026)
            .in_("league_key", _MAIN_TIER_LEAGUES)
            .order("match_date")
            .limit(1)
            .execute()
        )
        season_start_iso_week = None
        if season_start_res.data:
            d = date.fromisoformat(str(season_start_res.data[0]["match_date"])[:10])
            iso = d.isocalendar()
            season_start_iso_week = (iso[0], iso[1])

        for a in accas:
            a["season_week"] = (
                _season_week_number(a.get("target_date"), season_start_iso_week)
                if season_start_iso_week else None
            )

        # Enrich each leg with what actually happened — accumulator_picks
        # has no outcome column of its own, so this is resolved at read
        # time from match_results rather than stored redundantly.
        fixture_ids = list({leg["fixture_id"] for a in accas for leg in (a.get("legs") or [])})
        results_by_id: dict[str, dict] = {}
        if fixture_ids:
            mr_res = (
                supabase.table("match_results")
                .select("fixture_id,btts,total_cards,total_corners,home_goals,away_goals,ftr")
                .eq("sport", "football")
                .in_("fixture_id", fixture_ids)
                .execute()
            )
            results_by_id = {r["fixture_id"]: r for r in (mr_res.data or [])}

        for a in accas:
            for leg in (a.get("legs") or []):
                mr = results_by_id.get(leg["fixture_id"])
                actual = resolve_actual_outcome(leg["market"], leg["selection"], mr) if mr else None
                leg["actual_outcome"] = actual
                leg["status"] = (
                    "won" if actual == leg["selection"]
                    else "lost" if actual is not None
                    else "pending"
                )

        return {"data": accas, "count": len(accas)}
    except Exception as e:
        return {"data": [], "count": 0, "error": str(e)}

@router.get("/performance")
async def get_overall_performance():
    supabase = get_supabase_admin()
    try:
        accas = supabase.table("accumulators")\
            .select("acc_type, status, outcome, actual_odds")\
            .execute()
        data = accas.data or []
        total = len(data)
        won = sum(1 for a in data if a.get("outcome") == "won")
        lost = sum(1 for a in data if a.get("outcome") == "lost")
        pending = sum(1 for a in data if a.get("outcome") is None)
        win_rate = round(won / total * 100, 1) if total > 0 else 0

        by_type = {}
        for t in ["10odds", "5odds", "3odds"]:
            type_data = [
                a for a in data if a.get("acc_type") == t
            ]
            type_won = sum(
                1 for a in type_data if a.get("outcome") == "won"
            )
            by_type[t] = {
                "total": len(type_data),
                "won": type_won,
                "win_rate": round(
                    type_won / len(type_data) * 100, 1
                ) if type_data else 0
            }

        try:
            model_perf = supabase.table("model_performance")\
                .select("*")\
                .order("recorded_at", desc=True)\
                .limit(10)\
                .execute()
            model_perf_data = model_perf.data or []
        except Exception:
            # table doesn't exist yet — per-model tracking isn't wired up,
            # not a reason to fail the whole performance summary
            model_perf_data = []

        return {
            "total_predictions": total,
            "won": won,
            "lost": lost,
            "pending": pending,
            "win_rate": win_rate,
            "by_type": by_type,
            "models": model_perf_data
        }
    except Exception as e:
        return {"error": str(e)}
