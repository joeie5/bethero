"""tiers.py — FastAPI router for the Tier Picks feature: a user picks a
calendar day, one or more league tiers, and how many matches they want; the
model returns its best-probability selections from that day's fixtures in
those tiers.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.database import get_supabase_admin
from app.ml.league_tiers import tiers_summary, LEAGUE_TIERS
from app.ml.outcome_resolver import resolve_actual_outcome
from app.ml.predictor import Predictor, _ModelCache

router = APIRouter(prefix="/tiers", tags=["Tiers"])

CURRENT_SEASON = 2026
DATA_DIR = "data_snapshot"


def _day_calendar(sport: str) -> list[dict]:
    """Available calendar dates this season with a fixture count, for the
    day picker. Reads live from Supabase (not the data_snapshot parquet,
    which is a one-time export last refreshed 2026-09-14 and never gains
    fixtures added by live ingestion) so new dates appear automatically as
    soon as they're ingested — no manual refresh needed.

    Unlike the old week calendar, this needs no anchor-league restriction:
    that restriction existed only to stop MLS/Liga MX's Jan-Dec calendar
    from shifting ISO week numbering — a single calendar date has no such
    cross-league ambiguity, so every tiered league is included."""
    supabase = get_supabase_admin()
    # PostgREST caps a response at 1000 rows by default, and this table
    # already holds 2800+ matching rows for just this season's tiered
    # leagues — confirmed live: querying without pagination silently
    # dropped whichever 1000 rows Postgres happened to return first, which
    # is why today's fixtures intermittently vanished from the day picker.
    # Paginate through everything instead of trusting a single page — and
    # explicitly order by (fixture_id) rather than leaving it unordered:
    # confirmed live that .range() pagination with no ORDER BY gives an
    # unstable row set between calls (Postgres makes no ordering guarantee
    # without one), which silently double-counted/dropped rows across page
    # boundaries and showed different fixture_count totals on every call.
    rows: list[dict] = []
    page_size = 1000
    start = 0
    while True:
        res = (
            supabase.table("fixtures")
            .select("match_date")
            .eq("sport", sport)
            .eq("season", str(CURRENT_SEASON))
            .in_("league_key", list(LEAGUE_TIERS.keys()))
            .order("fixture_id")
            .range(start, start + page_size - 1)
            .execute()
        )
        page = res.data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    if not rows:
        return []
    counts: dict[str, int] = {}
    for r in rows:
        d = r.get("match_date")
        if d:
            counts[d] = counts.get(d, 0) + 1
    return [{"date": d, "fixture_count": n} for d, n in sorted(counts.items())]


# Flat list of selectable options. Goals and Corners each have multiple
# independently-meaningful lines (per app/ml/predictor.py's MARKET_SPEC), so
# they're expanded into one option per line rather than one option for the
# whole market — letting the user pick e.g. "Goals: Over 2.5" specifically
# instead of only ever getting whichever line the market happens to favour.
# BTTS/Cards/1X2 aren't line-based (two_sided/three_way modes only ever
# produce one selection type per fixture), so they stay single options.
AVAILABLE_MARKETS = [
    {"market": "Over_Under_Goals", "selection": "Over 1.5", "label": "Goals: Over 1.5"},
    {"market": "Over_Under_Goals", "selection": "Over 2.5", "label": "Goals: Over 2.5"},
    {"market": "Over_Under_Goals", "selection": "Under 3.5", "label": "Goals: Under 3.5"},
    {"market": "Over_Under_Corners", "selection": "Over 7.5", "label": "Corners: Over 7.5"},
    {"market": "Over_Under_Corners", "selection": "Under 9.5", "label": "Corners: Under 9.5"},
    {"market": "BTTS", "selection": None, "label": "Both Teams to Score"},
    {"market": "Cards", "selection": None, "label": "Cards"},
    {"market": "1X2", "selection": None, "label": "Match Result (1X2)"},
]


# Maps a chosen (db_market, selection) line to the internal model_key its
# StackingEnsemble is trained/saved under (see app/ml/predictor.py's
# MARKET_SPEC) — needed to reach into that ensemble's base models directly
# when the user wants one specific ML algorithm's raw output instead of the
# combined ensemble.
LINE_MODEL_KEY = {
    ("Over_Under_Goals", "Over 1.5"): "Goals_1.5",
    ("Over_Under_Goals", "Over 2.5"): "Goals_2.5",
    ("Over_Under_Goals", "Under 3.5"): "Goals_3.5",
    ("Over_Under_Corners", "Over 7.5"): "Corners_7.5",
    ("Over_Under_Corners", "Under 9.5"): "Corners_9.5",
}
# Markets with no line concept — one model covers the whole market.
MARKET_MODEL_KEY = {
    "BTTS": "BTTS",
    "Cards": "Cards_3.5",
    "1X2": "1x2",
}

# The 5 base ML algorithms trained per market, plus the combined ensemble
# that stacks them — see app/ml/models/ensemble.py's BASE_MODEL_NAMES.
AVAILABLE_ML_MODELS = [
    {"id": "ensemble", "label": "Ensemble (all models combined)"},
    {"id": "RandomForestBetModel", "label": "Random Forest"},
    {"id": "XGBoostBetModel", "label": "XGBoost"},
    {"id": "LightGBMBetModel", "label": "LightGBM"},
    {"id": "NeuralNetworkBetModel", "label": "Neural Network"},
    {"id": "LSTMBetModel", "label": "LSTM"},
]

_predictor_instance: Predictor | None = None


def _get_predictor() -> Predictor:
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = Predictor(get_supabase_admin(), data_dir=DATA_DIR)
    return _predictor_instance


@router.get("/leagues")
async def get_league_tiers():
    """Tier 1..5 with their member leagues, for the tier-selection UI."""
    return {"tiers": tiers_summary()}


@router.get("/markets")
async def get_markets():
    """Markets the model predicts, for the market-selection UI."""
    return {"markets": AVAILABLE_MARKETS}


@router.get("/ml-models")
async def get_ml_models():
    """ML algorithms available to predict with, for the model-selection UI."""
    return {"models": AVAILABLE_ML_MODELS}


@router.get("/days")
async def get_available_days(sport: str = "football"):
    """Calendar dates with loaded fixtures this season, so the UI can offer
    a day picker."""
    days = _day_calendar(sport)
    return {"sport": sport, "season": CURRENT_SEASON, "days": days}


class TierPredictRequest(BaseModel):
    sport: str = "football"
    date: str  # "YYYY-MM-DD"
    tiers: List[int] = []
    league_keys: Optional[List[str]] = None   # specific leagues to restrict to; takes
                                               # precedence over `tiers` when given (lets
                                               # the UI offer per-league selection, not
                                               # just whole-tier, without losing the
                                               # tier grouping leagues_in_tier() already has)
    markets: Optional[List[str]] = None       # db_market codes to include; None/empty = all
    selections: Optional[List[str]] = None    # specific line selections (e.g. "Over 2.5") to further filter within markets
    ml_model: Optional[str] = None            # None/"ensemble" = stored ensemble predictions; else one AVAILABLE_ML_MODELS id
    match_count: int = 10


def _resolve_model_key(market: str, selection: str | None) -> str | None:
    if market in MARKET_MODEL_KEY:
        return MARKET_MODEL_KEY[market]
    return LINE_MODEL_KEY.get((market, selection))


def _predict_single_model(
    predictor: Predictor, sport: str, fixture_id: str, ml_model: str,
    market: str, selection: str | None, raw_features_cache: dict,
) -> dict | None:
    """One specific base ML algorithm's own raw probability for a
    (market, selection) — bypasses the stacking ensemble's meta-learner and
    weighting entirely, straight from that algorithm's predict_proba."""
    model_key = _resolve_model_key(market, selection)
    if model_key is None:
        return None
    ensemble = _ModelCache.get(sport, model_key)
    if ensemble is None:
        return None
    base = ensemble._base_models.get(ml_model)
    if base is None:
        return None

    if fixture_id not in raw_features_cache:
        try:
            raw = predictor._fe.build(sport, fixture_id)
        except Exception:
            raw_features_cache[fixture_id] = None
        else:
            raw_features_cache[fixture_id] = pd.DataFrame([raw]).fillna(0.0)
    X = raw_features_cache[fixture_id]
    if X is None:
        return None

    try:
        batch = base.predict_proba(X)
    except Exception:
        return None
    probs = batch.probabilities.iloc[0]

    if selection is not None:
        if selection not in probs.index:
            return None
        return {"selection": selection, "model_probability": float(probs[selection])}

    best_cls = probs.idxmax()
    return {"selection": str(best_cls), "model_probability": float(probs[best_cls])}


@router.post("/predict")
async def predict_for_tiers(req: TierPredictRequest):
    """Best model selections for the given calendar day, restricted to
    leagues in the requested tiers, capped to match_count picks (one
    selection per fixture, ranked by real model probability).

    Daily rather than weekly on purpose: a week needed the ANCHOR_LEAGUES
    restriction to avoid MLS/Liga MX's Jan-Dec calendar shifting the week
    numbering — a single calendar date has no such cross-league ambiguity,
    so every tiered league (not just the European anchors) is eligible."""
    if not req.tiers and not req.league_keys:
        raise HTTPException(status_code=400, detail="Select at least one tier or league")
    if req.match_count < 1 or req.match_count > 50:
        raise HTTPException(status_code=400, detail="match_count must be between 1 and 50")

    if req.league_keys:
        wanted_leagues = {k for k in req.league_keys if k in LEAGUE_TIERS}
    else:
        wanted_leagues = {k for k, v in LEAGUE_TIERS.items() if v in req.tiers}
    if not wanted_leagues:
        raise HTTPException(status_code=400, detail="No leagues found for the requested selection")

    supabase = get_supabase_admin()
    fixtures_res = (
        supabase.table("fixtures").select("*")
        .eq("sport", req.sport).eq("season", str(CURRENT_SEASON))
        .eq("match_date", req.date)
        .in_("league_key", list(wanted_leagues))
        .execute()
    )
    target_fixtures = pd.DataFrame(fixtures_res.data or [])
    if target_fixtures.empty:
        return {
            "date": req.date, "tiers": req.tiers, "count": 0, "predictions": [],
            "message": "No fixtures have been loaded for this day's leagues yet — check back soon.",
        }

    fixture_ids = target_fixtures["fixture_id"].tolist()
    fixtures_by_id = target_fixtures.set_index("fixture_id").to_dict("index")

    results_res = (
        supabase.table("match_results").select("*")
        .eq("sport", req.sport).in_("fixture_id", fixture_ids)
        .execute()
    )
    results_by_id = {r["fixture_id"]: r for r in (results_res.data or [])}

    if req.ml_model and req.ml_model != "ensemble":
        valid_ids = {m["id"] for m in AVAILABLE_ML_MODELS if m["id"] != "ensemble"}
        if req.ml_model not in valid_ids:
            raise HTTPException(status_code=400, detail=f"Unknown ml_model '{req.ml_model}'")
        if not req.markets:
            raise HTTPException(status_code=400, detail="Select at least one market to use a specific ML model")

        # Reconstruct the (market, selection) combos the user actually
        # picked: a market with chosen lines (Goals/Corners) evaluates just
        # those lines; a line-less market (BTTS/Cards/1X2) evaluates its one
        # whole-market model.
        combos: list[tuple[str, str | None]] = []
        for market in req.markets:
            line_sels = [s for s in (req.selections or []) if (market, s) in LINE_MODEL_KEY]
            if line_sels:
                combos.extend((market, s) for s in line_sels)
            else:
                combos.append((market, None))

        predictor = _get_predictor()
        raw_cache: dict = {}
        single_market = len(set(req.markets)) == 1
        single_combo = len(combos) == 1
        sorted_fixtures = target_fixtures.sort_values("match_date")

        # A single (market, selection) combo means every result is the same
        # bet, so "N picks" should mean the model's N most confident ones —
        # requires evaluating every fixture before cutting, not stopping
        # early once match_count rows are found in date order (that just
        # returns whichever fixtures happen to be first by date, not the
        # best ones — the same bug already fixed for the stored-ensemble
        # path above). Multiple combos still cut in date order to preserve
        # the real mix across genuinely independent lines (e.g. Corners).
        candidates = []
        for _, fx_row in sorted_fixtures.iterrows():
            fid = fx_row["fixture_id"]
            fixture_results = []
            for market, selection in combos:
                r = _predict_single_model(predictor, req.sport, fid, req.ml_model, market, selection, raw_cache)
                if r is not None:
                    fixture_results.append((market, r))
            if not fixture_results:
                continue
            # Single market with independent lines (Corners): show every
            # requested line as its own pick, same reasoning as the ensemble
            # path below — Over 7.5 and Under 9.5 aren't mutually exclusive.
            # Otherwise keep only this fixture's best-probability combo.
            chosen = fixture_results if single_market else [max(fixture_results, key=lambda t: t[1]["model_probability"])]
            for market, r in chosen:
                candidates.append((fx_row, market, r))
            if not single_combo and len(candidates) >= req.match_count:
                break

        if single_combo:
            candidates.sort(key=lambda c: c[2]["model_probability"], reverse=True)
        candidates = candidates[:req.match_count]

        out = []
        for fx_row, market, r in candidates:
            fid = fx_row["fixture_id"]
            result = results_by_id.get(fid)
            actual_outcome = None
            status = "pending"
            if result:
                actual_outcome = resolve_actual_outcome(market, r["selection"], result)
                if actual_outcome is not None:
                    status = "won" if actual_outcome == r["selection"] else "lost"
            league_key = fx_row.get("league_key")
            out.append({
                "fixture_id": fid,
                "home_team": fx_row.get("home_team"),
                "away_team": fx_row.get("away_team"),
                "match_date": str(fx_row.get("match_date")) if fx_row.get("match_date") is not None else None,
                "league_key": league_key,
                "league_name": fx_row.get("league_name"),
                "tier": LEAGUE_TIERS.get(league_key, 5),
                "market": market,
                "selection": r["selection"],
                "model_probability": round(r["model_probability"], 4),
                "odds": None,
                "actual_outcome": actual_outcome,
                "status": status,
            })

        response = {
            "date": req.date,
            "tiers": req.tiers,
            "markets": req.markets,
            "selections": req.selections,
            "ml_model": req.ml_model,
            "sport": req.sport,
            "count": len(out[:req.match_count]),
            "predictions": out[:req.match_count],
        }
        if not out:
            response["message"] = "Fixtures for this week are in, but predictions haven't been generated yet — check back soon."
        return response

    client = get_supabase_admin()
    preds: list[dict] = []
    CHUNK = 500
    PAGE = 1000  # PostgREST's own per-request cap — each chunk can still
    # exceed it (500 fixtures x ~6 markets can be 3000+ rows), so paginate
    # within the chunk too rather than trusting a single page. Explicit
    # .order("id") makes .range() pagination deterministic — see
    # _day_calendar's docstring for why an unordered .range() silently
    # gives a different, inconsistent row set on every call.
    for i in range(0, len(fixture_ids), CHUNK):
        chunk = fixture_ids[i:i + CHUNK]
        start = 0
        while True:
            res = (
                client.table("predictions")
                .select("*")
                .eq("sport", req.sport)
                .in_("fixture_id", chunk)
                .order("id")
                .range(start, start + PAGE - 1)
                .execute()
            )
            page = res.data or []
            preds.extend(page)
            if len(page) < PAGE:
                break
            start += PAGE

    # Goals uses best_edge_across_lines: only one line should ever be
    # "current" per fixture, chosen by whichever has the best edge at
    # generation time. When a retrain shifts which line wins for a given
    # fixture (e.g. was "Over 1.5", now "Over 2.5"), the new line's row is
    # a genuinely different (market, selection) key, so it gets inserted
    # alongside the old one instead of replacing it — confirmed live (718
    # fixtures had 2 stored Goals rows after the Goals retrain). Dedup to
    # the freshest row per (fixture_id, market) for those markets. Corners
    # is the one exception: its two lines (Over 7.5 / Under 9.5) are NOT
    # mutually exclusive and are BOTH meant to persist simultaneously per
    # fixture (independent_lines mode), so it dedups per (fixture_id,
    # market, selection) instead — collapsing to one row per market there
    # would silently undo the earlier independent-lines fix.
    INDEPENDENT_LINES_MARKETS = {"Over_Under_Corners"}
    freshest: dict[tuple, dict] = {}
    for p in preds:
        market = p["market"]
        key = (p["fixture_id"], market, p.get("selection")) if market in INDEPENDENT_LINES_MARKETS else (p["fixture_id"], market)
        cur = freshest.get(key)
        if cur is None or (p.get("generated_at") or "") > (cur.get("generated_at") or ""):
            freshest[key] = p
    preds = list(freshest.values())

    if not req.markets:
        # Double_Chance is derived, not independently modeled — it's just
        # P(Home)+P(Draw) etc. from the 1X2 model (app/ml/predictor.py's
        # _eval_double_chance), so combining two outcomes always scores a
        # higher raw probability than any single-outcome market. Left in
        # the "compare across markets, keep the most confident per fixture"
        # pool below, it silently won that comparison for nearly every
        # fixture regardless of the actual match (confirmed live: 13/13
        # picks came back "Double Chance: 1X") — not genuine per-match
        # signal, just a property of the market type. It's also not even
        # in AVAILABLE_MARKETS, so a user can never explicitly ask for it;
        # only exclude it here, when no explicit market filter was given.
        preds = [p for p in preds if p.get("market") != "Double_Chance"]
    else:
        wanted_markets = set(req.markets)
        preds = [p for p in preds if p.get("market") in wanted_markets]
    if req.selections:
        wanted_selections = set(req.selections)
        preds = [p for p in preds if p.get("selection") in wanted_selections]

    if not preds:
        return {
            "date": req.date, "tiers": req.tiers, "markets": req.markets, "selections": req.selections,
            "count": 0, "predictions": [],
            "message": "Fixtures for this day are in, but predictions haven't been generated yet — check back soon.",
        }

    def _match_date(p: dict) -> str:
        fx = fixtures_by_id.get(p["fixture_id"], {})
        return str(fx.get("match_date") or "")

    def _fixture_score(p: dict) -> float:
        c = p.get("confidence")
        return c if c is not None else (p.get("model_probability") or 0) * 100

    distinct_selections = {p.get("selection") for p in preds}

    if req.match_count == 1:
        # A single pick has no "diversity across slots" to protect — there's
        # only one slot, so it must always be the single most confident
        # prediction in the whole pool. Confirmed live: with "All markets"
        # selected, the per-fixture/date-ordered branch below returned
        # whichever fixture happened to sort first by date (chronological
        # order, all same-day matches effectively arbitrary), not the best
        # one — e.g. it surfaced a 67.7% pick when a 73.6% one was
        # available the same day. That date-ordering exists to preserve
        # market mix across multiple slots; with only one slot to fill,
        # ranking by confidence is unambiguously correct.
        top = sorted(preds, key=_fixture_score, reverse=True)[:1]
    elif len(distinct_selections) == 1:
        # Every remaining row is the exact same selection (e.g. the user
        # picked "Goals: Over 1.5" specifically) — there's no diversity to
        # protect here, every pick already agrees on what to bet, so "N
        # picks" should mean the N the model is most confident about, not
        # just whichever matches happen to be earliest by date. Confidence
        # is now genuinely calibrated after the meta-learner retrain (real,
        # verified monotonic win-rate by confidence bucket), so ranking by
        # it surfaces real quality instead of an artifact.
        ranked = sorted(preds, key=_fixture_score, reverse=True)
        top = ranked[:req.match_count]
    elif req.markets and len(req.markets) == 1:
        # A single market was chosen but with multiple distinct selections
        # still present — e.g. both Corners lines (Over 7.5 and Under 9.5)
        # are NOT mutually exclusive (both are commonly true for the same
        # match, e.g. a 9-corner total), so collapsing to "one pick per
        # fixture" is a category error: Over 7.5's raw probability beats
        # Under 9.5's for ~1060 of 1061 fixtures, so any per-fixture "best"
        # collapse always picks Over 7.5 and hides the (also genuine)
        # Under 9.5 predictions entirely. Show every prediction row for the
        # chosen market as its own pick, ordered chronologically so both
        # lines' real mix shows through rather than one dominating.
        ranked = sorted(preds, key=_match_date)
        top = ranked[:req.match_count]
    else:
        # Comparing across markets (or no market filter): different markets
        # ARE mutually-exclusive choices for the same match slot, so keep
        # one pick per fixture — the higher-confidence of its candidates —
        # then order chronologically rather than by score. A global
        # score-sorted cut always collapses to one extreme (whichever
        # selection type scores higher on average across the whole pool);
        # ordering by date instead lets the real mix already present in the
        # stored predictions show through.
        best_by_fixture: dict[str, dict] = {}
        for p in preds:
            fid = p["fixture_id"]
            cur = best_by_fixture.get(fid)
            if cur is None or _fixture_score(p) > _fixture_score(cur):
                best_by_fixture[fid] = p

        ranked = sorted(best_by_fixture.values(), key=_match_date)
        top = ranked[:req.match_count]

    out = []
    for p in top:
        fx = fixtures_by_id.get(p["fixture_id"], {})
        result = results_by_id.get(p["fixture_id"])
        actual_outcome = None
        status = "pending"
        if result:
            actual_outcome = resolve_actual_outcome(p["market"], p["selection"], result)
            if actual_outcome is not None:
                status = "won" if actual_outcome == p["selection"] else "lost"
        league_key = fx.get("league_key")
        out.append({
            "fixture_id": p["fixture_id"],
            "home_team": fx.get("home_team"),
            "away_team": fx.get("away_team"),
            "match_date": str(fx.get("match_date")) if fx.get("match_date") is not None else None,
            "league_key": league_key,
            "league_name": fx.get("league_name"),
            "tier": LEAGUE_TIERS.get(league_key, 5),
            "market": p["market"],
            "selection": p["selection"],
            "model_probability": p.get("model_probability"),
            "odds": p.get("odds"),
            "edge": p.get("edge"),
            "confidence": p.get("confidence"),
            "actual_outcome": actual_outcome,
            "status": status,
        })

    return {
        "date": req.date,
        "tiers": req.tiers,
        "markets": req.markets,
        "sport": req.sport,
        "count": len(out),
        "predictions": out,
    }
