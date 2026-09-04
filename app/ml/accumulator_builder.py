"""
accumulator_builder.py — Builds 3-leg (and, once gated, 5/10-leg) accumulators.

Strategy
--------
1. Fetch all PENDING predictions for upcoming fixtures
2. Filter to high-confidence, positive-edge selections
3. De-correlate (same league / same date / same fixture) and cap same-market
   legs at MAX_SAME_MARKET (§1.6 — an uncapped market took 53.6% of all picked
   legs in testing before this cap existed)
4. Rank by composite score and take top N for each tier
5. Compute combined odds and Kelly criterion recommended stake
6. Persist to Supabase accumulators + accumulator_picks tables, writing the
   REAL leg count (§1.4 — a "3-odds" ticket was previously found stacking
   5-10 legs while still labeled 3-odds)

Accumulator types
-----------------
- 3odds:  2-4 legs — the only tier currently validated (§1.5). Built by default.
- 5odds:  5-ish legs — GATED. Every construction method tested degraded past
          4 legs without exception. Config exists so it's ready the moment it
          clears the §4 go/no-go bar, but build() never runs it unless the
          caller explicitly opts in.
- 10odds: ~10 legs — GATED, same reasoning. Corners@7.5 in isolation is the
          one market with a real calibrated 10-odds sample so far; seed this
          tier from Corners specifically once gated, not a diluted blend.

Kelly Criterion
---------------
f* = (bp - q) / b
where b = decimal_odds - 1, p = model_prob, q = 1 - p

We apply a fractional Kelly (25%) for bankroll safety.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.database import get_supabase_admin

logger = logging.getLogger(__name__)

# ─────────────────────────── Config ────────────────────────────────────────

ACCA_CONFIGS = {
    "3odds":  {"min_legs": 2, "max_legs": 4, "min_edge": 0.03, "min_confidence": 55.0},
    # GATED per §1.5 — never built unless include_gated_tiers=True is passed explicitly.
    "5odds":  {"min_legs": 5, "max_legs": 5, "min_edge": 0.02, "min_confidence": 50.0},
    "10odds": {"min_legs": 10, "max_legs": 10, "min_edge": 0.01, "min_confidence": 45.0},
}

GATED_TIERS = {"5odds", "10odds"}

KELLY_FRACTION   = 0.25   # fractional Kelly (25%)
MIN_ODDS         = 1.20   # ignore selections shorter than this
MAX_SINGLE_ODDS  = 5.00   # cap runaway long shots in accumulators
MAX_SAME_LEAGUE  = 2       # max selections from same league in one acca
MAX_SAME_DATE    = 4       # max selections from same calendar date
MAX_SAME_MARKET  = 2       # §1.6 — max legs of the same market per ticket


# ─────────────────────────── Data Classes ──────────────────────────────────

@dataclass
class Selection:
    prediction_id:      int
    sport:              str
    fixture_id:         str
    market:             str
    selection:          str
    model_probability:  float
    odds:               float
    confidence:         float
    edge:               float
    league_key:         str | None
    match_date:         str
    home_team:          str = ""
    away_team:          str = ""
    league_name:        str = ""

    def kelly_fraction(self) -> float:
        """Fractional Kelly stake as % of bankroll."""
        b = self.odds - 1
        p = self.model_probability
        q = 1 - p
        f_full = (b * p - q) / b if b > 0 else 0.0
        return max(0.0, round(f_full * KELLY_FRACTION * 100, 2))


@dataclass
class AccumulatorResult:
    acc_type:       str           # "3odds" | "5odds" | "10odds"
    selections:     list[Selection]
    combined_odds:  float
    kelly_stake:    float
    expected_value: float
    status:         str = "pending"

    def to_db_rows(self) -> tuple[dict, list[dict]]:
        """Return (accumulator row, [pick rows]) matching the live schema."""
        acca_row = {
            "acc_type":     self.acc_type,
            "target_date":  datetime.now(timezone.utc).date().isoformat(),
            "target_odds":  round(self.combined_odds, 3),
            "actual_odds":  round(self.combined_odds, 3),
            "model_win_probability": round(
                (sum(s.model_probability for s in self.selections) / max(len(self.selections), 1))
                ** len(self.selections),
                4,
            ) if self.selections else None,
            "legs":         len(self.selections),   # §1.4 — real leg count, not the odds target
            "status":       self.status,
        }
        pick_rows = [
            {
                "sport":       s.sport,
                "fixture_id":  s.fixture_id,
                "prediction_id": s.prediction_id,
                "home_team":   s.home_team,
                "away_team":   s.away_team,
                "match_date":  s.match_date[:10] if s.match_date else None,
                "league_key":  s.league_key,
                "league_name": s.league_name,
                "market":      s.market,
                "selection":   s.selection,
                "confidence":  s.confidence,
                "odds":        s.odds,
                "leg_order":   i + 1,
            }
            for i, s in enumerate(self.selections)
        ]
        return acca_row, pick_rows


# ─────────────────────────── Correlation / diversity filter ────────────────

class CorrelationFilter:
    """
    Prevents over-correlated accumulators:
    - Same league: max MAX_SAME_LEAGUE selections
    - Same date:   max MAX_SAME_DATE selections
    - Same market: max MAX_SAME_MARKET selections (§1.6)
    - Exact same fixture: never pick two markets from the same match
    """

    def __init__(self, selections: list[Selection]):
        self._selections = selections

    def filter(self) -> list[Selection]:
        seen_fixtures: set[tuple[str, str]] = set()
        league_count:  dict[str, int]       = {}
        date_count:    dict[str, int]       = {}
        market_count:  dict[str, int]       = {}
        valid:         list[Selection]      = []

        for s in self._selections:
            fkey = (s.sport, s.fixture_id)
            if fkey in seen_fixtures:
                continue
            lkey = s.league_key or "-1"
            dt   = s.match_date[:10]
            if league_count.get(lkey, 0) >= MAX_SAME_LEAGUE:
                continue
            if date_count.get(dt, 0) >= MAX_SAME_DATE:
                continue
            if market_count.get(s.market, 0) >= MAX_SAME_MARKET:
                continue
            valid.append(s)
            seen_fixtures.add(fkey)
            league_count[lkey] = league_count.get(lkey, 0) + 1
            date_count[dt]     = date_count.get(dt, 0) + 1
            market_count[s.market] = market_count.get(s.market, 0) + 1

        return valid


# ─────────────────────────── Builder ───────────────────────────────────────

class AccumulatorBuilder:

    def __init__(self, supabase_client=None):
        self.client = supabase_client or get_supabase_admin()

    # ── Public API ──────────────────────────────────────────────

    def run(self, include_gated_tiers: bool = False) -> list[AccumulatorResult]:
        """
        Build accumulator types and persist them.

        include_gated_tiers must be explicitly set True to build 5odds/10odds
        (§1.5) — the default only builds 3odds. Do not flip this default for
        a deadline; it stays off until each gated tier clears §4's bar.
        """
        logger.info("AccumulatorBuilder starting …")
        pool = self._load_candidate_selections()
        logger.info("Candidate pool: %d selections", len(pool))

        if len(pool) < 2:
            logger.warning("Not enough selections to build accumulators")
            return []

        tiers = ["3odds"] + (["5odds", "10odds"] if include_gated_tiers else [])
        results: list[AccumulatorResult] = []
        for acca_type in tiers:
            cfg = ACCA_CONFIGS[acca_type]
            try:
                acca = self._build(acca_type, pool, cfg)
                if acca:
                    self._persist(acca)
                    results.append(acca)
                    logger.info(
                        "Built %s — legs=%d odds=%.2f EV=%.4f kelly=%.1f%%",
                        acca_type, len(acca.selections), acca.combined_odds,
                        acca.expected_value, acca.kelly_stake,
                    )
            except Exception as exc:
                logger.error("Failed to build %s: %s", acca_type, exc, exc_info=True)

        return results

    def build_single_type(self, acca_type: str) -> AccumulatorResult | None:
        """Build one accumulator type on demand. Raises for gated tiers."""
        if acca_type not in ACCA_CONFIGS:
            raise ValueError(f"Unknown acca_type '{acca_type}'")
        if acca_type in GATED_TIERS:
            raise ValueError(
                f"'{acca_type}' is gated per §1.5 — it has not cleared the §4 "
                "go/no-go bar. Use run(include_gated_tiers=True) only once it has."
            )
        pool = self._load_candidate_selections()
        cfg  = ACCA_CONFIGS[acca_type]
        acca = self._build(acca_type, pool, cfg)
        if acca:
            self._persist(acca)
        return acca

    # ── Core build ──────────────────────────────────────────────

    def _build(self, acca_type: str, pool: list[Selection], cfg: dict) -> AccumulatorResult | None:
        min_legs  = cfg["min_legs"]
        max_legs  = cfg["max_legs"]
        min_edge  = cfg["min_edge"]
        min_conf  = cfg["min_confidence"]

        eligible = [
            s for s in pool
            if s.edge >= min_edge
            and s.confidence >= min_conf
            and MIN_ODDS <= s.odds <= MAX_SINGLE_ODDS
        ]

        if len(eligible) < min_legs:
            logger.warning("[%s] Only %d eligible after filter (need %d)",
                           acca_type, len(eligible), min_legs)
            return None

        eligible = CorrelationFilter(eligible).filter()

        if len(eligible) < min_legs:
            logger.warning("[%s] Only %d after correlation/diversity filter (need %d)",
                           acca_type, len(eligible), min_legs)
            return None

        eligible.sort(key=lambda s: (
            0.5 * s.confidence / 100
            + 0.3 * min(s.edge / 0.15, 1.0)
            + 0.2 * (abs(s.model_probability - 0.5) * 2)
        ), reverse=True)

        selections = eligible[:max_legs]
        if len(selections) < min_legs:
            return None

        combined_odds = 1.0
        for s in selections:
            combined_odds *= s.odds
        combined_odds = round(combined_odds, 3)

        n_legs    = len(selections)
        avg_prob  = sum(s.model_probability for s in selections) ** (1.0 / n_legs)
        b_acca    = combined_odds - 1
        q_acca    = 1 - avg_prob
        f_full    = (b_acca * avg_prob - q_acca) / b_acca if b_acca > 0 else 0.0
        kelly_pct = round(max(0.0, f_full * KELLY_FRACTION * 100), 2)

        ev = avg_prob * combined_odds - 1.0

        return AccumulatorResult(
            acc_type=acca_type,
            selections=selections,
            combined_odds=combined_odds,
            kelly_stake=kelly_pct,
            expected_value=round(ev, 4),
        )

    # ── DB I/O ──────────────────────────────────────────────────

    def _load_candidate_selections(self) -> list[Selection]:
        """
        Load PENDING predictions for upcoming (NS) fixtures.
        Join fixture data for league and date correlation filtering.
        """
        res = (
            self.client.table("predictions")
            .select(
                "id, sport, fixture_id, market, selection, "
                "model_probability, odds, confidence, edge, "
                "fixtures!inner(match_date, league_key, league_name, status, home_team, away_team)"
            )
            .is_("settled_at", "null")
            .eq("fixtures.status", "NS")
            .gt("edge", 0.0)
            .gt("odds", MIN_ODDS)
            .order("confidence", desc=True)
            .execute()
        )
        rows = res.data or []
        selections: list[Selection] = []
        for r in rows:
            fx = r.get("fixtures") or {}
            try:
                selections.append(Selection(
                    prediction_id=r["id"],
                    sport=r["sport"],
                    fixture_id=r["fixture_id"],
                    market=r["market"],
                    selection=r["selection"],
                    model_probability=float(r.get("model_probability", 0.5)),
                    odds=float(r.get("odds") or 2.0),
                    confidence=float(r.get("confidence", 50)),
                    edge=float(r.get("edge") or 0),
                    league_key=fx.get("league_key"),
                    match_date=str(fx.get("match_date", "")),
                    home_team=fx.get("home_team") or "",
                    away_team=fx.get("away_team") or "",
                    league_name=fx.get("league_name") or "",
                ))
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("Skipping invalid selection row: %s", exc)
        return selections

    def _persist(self, acca: AccumulatorResult) -> None:
        """Insert accumulator and its picks into Supabase."""
        acca_row, pick_payloads = acca.to_db_rows()
        try:
            res = self.client.table("accumulators").insert(acca_row).execute()
            acca_id = res.data[0]["id"] if res.data else None
            if acca_id and pick_payloads:
                for pick in pick_payloads:
                    pick["accumulator_id"] = acca_id
                self.client.table("accumulator_picks").insert(pick_payloads).execute()
                logger.info("Persisted %s (id=%s) with %d legs",
                            acca.acc_type, acca_id, len(pick_payloads))
        except Exception as exc:
            logger.error("Failed to persist accumulator: %s", exc, exc_info=True)

    # ── Return-on-investment tracker ─────────────────────────────

    def roi_report(self, lookback_days: int = 90) -> dict[str, Any]:
        """Fetch recent settled accumulators and calculate ROI per type."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
        res = (
            self.client.table("accumulators")
            .select("acc_type, actual_odds, outcome, created_at")
            .eq("settled", True)
            .gte("created_at", cutoff)
            .execute()
        )
        rows = res.data or []

        report: dict[str, Any] = {}
        for acca_type in ACCA_CONFIGS:
            subset = [r for r in rows if r["acc_type"] == acca_type]
            if not subset:
                report[acca_type] = {"bets": 0, "won": 0, "roi": None}
                continue
            won  = sum(1 for r in subset if r["outcome"] == "won")
            bets = len(subset)
            total_return = sum(r["actual_odds"] for r in subset if r["outcome"] == "won" and r.get("actual_odds"))
            roi = (total_return - bets) / bets if bets > 0 else 0.0
            report[acca_type] = {
                "bets": bets,
                "won":  won,
                "win_rate": round(won / bets, 4),
                "roi": round(roi, 4),
            }

        return report


# ─────────────────────────── Scheduler Entry Point ─────────────────────────

def run_accumulator_job(include_gated_tiers: bool = False) -> list[AccumulatorResult]:
    """
    Called by APScheduler after daily fixtures + predictions are ready.
    Expects predictions table to have fresh PENDING rows.
    """
    builder = AccumulatorBuilder()
    results = builder.run(include_gated_tiers=include_gated_tiers)
    logger.info("AccumulatorBuilder job complete — %d accas created", len(results))
    return results


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    run_accumulator_job()
