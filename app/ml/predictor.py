"""
predictor.py — Live prediction engine for Bet Hero.

Markets (per CLAUDE.md §2 — final, decided scope)
---------------------------------------------------
- BTTS     : Yes / No               — two-sided classifier, higher-confidence side wins
- Goals    : Over1.5 / Over2.5 / Under3.5 — three independently-trained line models;
             selection is the line with the BEST EDGE (model_prob - implied_prob),
             not the highest raw confidence (raw confidence always collapses to the
             safest extreme and never picks the 2.5 line — tested and rejected).
- Corners  : Over 7.5 (and independently) Under 9.5 — two fixed asymmetric lines,
             each evaluated independently and both may be emitted as separate legs
             (NOT a two-sided evaluation of a single line — a single-line two-sided
             test showed "Under" never wins at 7.5 because the line is too easy).
- Cards    : Over 3.5 / Under 3.5   — two-sided classifier like BTTS.

Each market/line is trained as its own binary StackingEnsemble, keyed internally
by a model_key distinct from the DB's `market` string (which follows the shared
markets_catalog convention). See MARKET_SPEC below.

Workflow per (sport, fixture_id)
---------------------------------
1. Build feature vector via FeatureEngineer.build(sport, fixture_id)
2. For each configured market: load its StackingEnsemble(s), get calibrated
   probabilities, evaluate per the market's selection rule above
3. Convert odds → implied probability from fixture_odds (line-aware)
4. Compute edge = model_prob - implied_prob
5. Assign confidence score (0-100)
6. Persist prediction rows to Supabase `predictions` table
7. Return list[PredictionResult]

Caching
-------
StackingEnsemble objects are cached in-process by (sport, model_key).
Feature vectors are not cached (always fresh before match).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.ml.feature_engineer import FeatureEngineer
from app.ml.models import StackingEnsemble, MODEL_DIR

logger = logging.getLogger(__name__)

# ─────────────────────────── Market specification (§2) ─────────────────────

# db_market must match a row already present in markets_catalog for the sport.
# model_key is the internal (sport, model_key) key StackingEnsemble files are
# trained/saved under — distinct from db_market because Goals/Corners need one
# trained model PER LINE, while the catalog only tracks the market family.
MARKET_SPEC: dict[str, dict[str, Any]] = {
    "BTTS": {
        "db_market": "BTTS",
        "mode":      "two_sided",
        "model_key": "BTTS",
        "line":      None,
    },
    "Cards": {
        "db_market": "Cards",
        "mode":      "two_sided",
        "model_key": "Cards_3.5",
        "line":      3.5,
    },
    "Goals": {
        "db_market": "Over_Under_Goals",
        "mode":      "best_edge_across_lines",
        "lines": [
            # baseline_prob: real historical base rate for this exact line
            # (computed from match_results — see predictor.py's
            # best_edge_across_lines handling), used as the "implied
            # probability" fallback when there's no real market odds for
            # this line (only 2.5 has real bookmaker odds from the CSV
            # import). Over 1.5 and Under 3.5 are both true ~73% of the
            # time regardless of the match — using a flat 0.5 (or 0.0)
            # fallback made their raw ~75% model probability look like a
            # huge "edge" against 2.5's genuine, much smaller market-based
            # edge, so this always won the comparison and 2.5/other lines
            # were never selected — exactly the "collapses to the safest
            # extreme" failure this mode exists to avoid.
            {"model_key": "Goals_1.5", "line": 1.5, "selection": "Over 1.5",  "side": "over",  "baseline_prob": 0.737},
            {"model_key": "Goals_2.5", "line": 2.5, "selection": "Over 2.5",  "side": "over",  "baseline_prob": 0.491},
            {"model_key": "Goals_3.5", "line": 3.5, "selection": "Under 3.5", "side": "under", "baseline_prob": 0.725},
        ],
    },
    "Corners": {
        "db_market": "Over_Under_Corners",
        "mode":      "independent_lines",
        "lines": [
            {"model_key": "Corners_7.5", "line": 7.5, "selection": "Over 7.5",  "side": "over"},
            {"model_key": "Corners_9.5", "line": 9.5, "selection": "Under 9.5", "side": "under"},
        ],
    },
    "1x2": {
        # db_market MUST be the exact markets_catalog value ("1X2", not
        # "1x2") — predictions.market has a FK to markets_catalog(sport,
        # market); confirmed live via a throwaway insert that lowercase
        # "1x2" is rejected. model_key stays lowercase — that's just our
        # own file-naming convention (StackingEnsemble_football_1x2.joblib),
        # unrelated to the DB constraint.
        "db_market": "1X2",
        "mode":      "three_way",
        "model_key": "1x2",
        "line":      None,
    },
    # Double Chance is not independently trained — it's the exact sum of the
    # already-calibrated 1x2 probabilities (P(1X)=P(Home)+P(Draw), etc.), so
    # training a second model would just add calibration risk for a number
    # that's already a deterministic function of one we trust.
    "Double Chance": {
        "db_market": "Double_Chance",
        "mode":      "double_chance_derived",
        "model_key": "1x2",   # reuses the 1x2 model, no separate training
        "line":      None,
    },
}

SUPPORTED_MARKETS = list(MARKET_SPEC.keys())


# ─────────────────────────── Data Classes ──────────────────────────────────

@dataclass
class PredictionResult:
    sport:               str
    fixture_id:          str
    market:              str     # db_market — matches markets_catalog (exact casing, e.g. "1X2")
    selection:           str     # e.g. "Yes", "Over 2.5", "Under 9.5"
    model_probability:   float   # P(selection), calibrated
    implied_probability: float | None   # from fixture_odds, None if odds missing
    odds:                float | None   # decimal odds for this selection
    confidence:          float   # 0-100 composite confidence
    league_key:          str = ""   # predictions.league_key is NOT NULL — from fixtures.league_key
    generated_at:        str = ""

    def to_db_row(self) -> dict:
        d = asdict(self)
        d.pop("generated_at", None)
        d["generated_at"] = self.generated_at or datetime.now(timezone.utc).isoformat()
        # `edge` is a DB-generated column — never write it directly.
        return d


# ─────────────────────────── Odds lookup ────────────────────────────────────

class OddsLookup:
    """Looks up implied probability / decimal odds from fixture_odds rows."""

    def __init__(self, odds_rows: list[dict]):
        self._rows = odds_rows

    def _find_row(self, db_market: str, line: float | None) -> dict | None:
        candidates = [r for r in self._rows if (r.get("market") or "") == db_market]
        if line is not None:
            candidates = [
                r for r in candidates
                if r.get("line") is not None and abs(float(r["line"]) - line) < 1e-6
            ]
        if not candidates:
            return None
        pinnacle = [r for r in candidates if "pinnacle" in (r.get("bookmaker") or "").lower()]
        rows = pinnacle or candidates
        rows_sorted = sorted(rows, key=lambda r: r.get("pulled_at") or "")
        return rows_sorted[-1]

    def implied_and_odds(
        self, db_market: str, line: float | None, side: str,
    ) -> tuple[float | None, float | None]:
        """
        side: "yes"/"no" for no-line markets, "over"/"under" for line markets.
        Returns (implied_probability, decimal_odds), both None if unavailable.
        """
        row = self._find_row(db_market, line)
        if not row:
            return None, None

        prob_col, odds_col = {
            "yes":   ("home_prob", "home_odds"),
            "no":    ("away_prob", "away_odds"),
            "over":  ("over_prob", "over_odds"),
            "under": ("under_prob", "under_odds"),
            "home":  ("home_prob", "home_odds"),
            "draw":  ("draw_prob", "draw_odds"),
            "away":  ("away_prob", "away_odds"),
        }[side]

        odds = row.get(odds_col)
        prob = row.get(prob_col)
        if prob is not None:
            implied = float(prob)
        elif odds:
            implied = 1.0 / float(odds)
        else:
            implied = None
        return implied, (float(odds) if odds else None)


# ─────────────────────────── Model Cache ───────────────────────────────────

class _ModelCache:
    _store: dict[str, StackingEnsemble] = {}

    @classmethod
    def get(cls, sport: str, model_key: str) -> StackingEnsemble | None:
        key = f"{sport}::{model_key}"
        if key not in cls._store:
            path = MODEL_DIR / f"StackingEnsemble_{sport}_{model_key}.joblib"
            if path.exists():
                try:
                    model = StackingEnsemble(sport=sport, market=model_key, model_dir=MODEL_DIR)
                    model.load_base_models(MODEL_DIR)
                    model.load(path)
                    cls._store[key] = model
                    logger.info("Loaded StackingEnsemble %s", key)
                except Exception as exc:
                    logger.error("Failed to load model %s: %s", key, exc)
                    return None
            else:
                logger.debug("No trained model for %s — skipping", key)
                return None
        return cls._store[key]

    @classmethod
    def invalidate(cls, sport: str, model_key: str) -> None:
        cls._store.pop(f"{sport}::{model_key}", None)


# ─────────────────────────── Confidence Scorer ─────────────────────────────

def _confidence_score(
    model_prob: float,
    edge: float | None,
    overround: float,
    feature_completeness: float,
) -> float:
    """
    Composite confidence score in [0, 100].

    Components
    ----------
    - Edge magnitude:        higher edge = higher confidence (40% weight)
    - Model probability:     extreme probabilities → more confident (20%)
    - Market efficiency:     low overround = efficient/trusted market (20%)
    - Feature completeness:  more valid features = more confident (20%)
    """
    edge_val   = edge if edge is not None else 0.0
    edge_score = min(1.0, max(0.0, edge_val / 0.15)) * 40.0
    prob_score = min(1.0, abs(model_prob - 0.5) * 2) * 20.0
    eff = max(0.0, min(1.0, (1.12 - overround) / (1.12 - 1.02)))
    market_score = eff * 20.0
    feat_score = feature_completeness * 20.0
    total = edge_score + prob_score + market_score + feat_score
    return round(min(100.0, max(0.0, total)), 2)


# ─────────────────────────── Predictor ─────────────────────────────────────

_DEFAULT_SNAPSHOT_DIR = Path(__file__).resolve().parent.parent.parent / "data_snapshot"


class Predictor:
    """
    Generates predictions for one or many matches and persists them to Supabase.
    """

    def __init__(self, supabase_client, data_dir: "Path | None" = _DEFAULT_SNAPSHOT_DIR):
        """
        data_dir : local Parquet snapshot dir (see scripts/export_snapshot.py).
                   Defaults to data_snapshot/ — FeatureEngineer then runs in
                   HYBRID mode (fast local base + one small top-up query for
                   anything newer than the snapshot), not the old fully-online
                   path that paginated the entire match_results table on every
                   cold instance (confirmed live: ~298 sequential API calls,
                   several minutes, before building even one feature vector).
                   Pass None to force the old fully-online behavior.
        """
        self.client = supabase_client
        if data_dir is not None and not Path(data_dir).exists():
            logger.warning("Predictor: snapshot dir %s not found — falling back to fully-online mode", data_dir)
            data_dir = None
        self._fe = FeatureEngineer(supabase_client, data_dir=data_dir)

    # ── Public API ──────────────────────────────────────────────

    def predict_match(
        self,
        sport: str,
        fixture_id: str,
        markets: list[str] | None = None,
        persist: bool = True,
    ) -> list[PredictionResult]:
        """
        Generate predictions for all requested markets for a single match.
        Returns list of PredictionResult objects.
        """
        markets = markets or SUPPORTED_MARKETS

        try:
            raw_features = self._fe.build(sport, fixture_id)
        except Exception as exc:
            logger.error("Feature build failed for %s/%s: %s", sport, fixture_id, exc)
            return []

        X = pd.DataFrame([raw_features]).fillna(0.0)
        feat_completeness = float((X != 0).mean().mean())

        odds_data = self._load_odds(sport, fixture_id)
        odds = OddsLookup(odds_data)
        league_key = self._load_league_key(sport, fixture_id)

        results: list[PredictionResult] = []
        for market in markets:
            spec = MARKET_SPEC.get(market)
            if not spec:
                logger.warning("Unknown market %r — skipping", market)
                continue
            try:
                results.extend(
                    self._predict_market(sport, fixture_id, market, spec, X, odds, feat_completeness, league_key)
                )
            except Exception as exc:
                logger.error("Prediction failed %s/%s market=%s: %s", sport, fixture_id, market, exc)

        if persist and results:
            self._persist(results)

        return results

    def predict_upcoming(
        self,
        sport: str | None = None,
        hours_ahead: int = 48,
        markets: list[str] | None = None,
    ) -> list[PredictionResult]:
        """Predict all upcoming fixtures in the next *hours_ahead* hours."""
        from datetime import date, timedelta
        today  = date.today()
        cutoff = today + timedelta(hours=hours_ahead) if hours_ahead < 24 else today + timedelta(days=hours_ahead // 24)

        q = (
            self.client.table("fixtures")
            .select("sport, fixture_id")
            .eq("status", "NS")
            .gte("match_date", today.isoformat())
            .lte("match_date", cutoff.isoformat())
        )
        if sport:
            q = q.eq("sport", sport)

        res = q.execute()
        pairs = [(r["sport"], r["fixture_id"]) for r in (res.data or [])]
        logger.info("Predicting %d upcoming fixtures …", len(pairs))

        all_results: list[PredictionResult] = []
        for sp, fid in pairs:
            # This runs unattended (daily scheduled job) — a single fixture
            # hitting Supabase's intermittent DNS flakiness
            # ([Errno 11001] getaddrinfo failed, confirmed live) must not
            # abort the whole batch and lose every fixture after it.
            try:
                preds = self.predict_match(sp, fid, markets=markets, persist=True)
            except Exception:
                logger.exception("predict_match failed for %s/%s — skipping", sp, fid)
                continue
            all_results.extend(preds)
        return all_results

    # ── Core market prediction ───────────────────────────────────

    def _predict_market(
        self,
        sport: str,
        fixture_id: str,
        market: str,
        spec: dict[str, Any],
        X: pd.DataFrame,
        odds: OddsLookup,
        feat_completeness: float,
        league_key: str = "",
    ) -> list[PredictionResult]:
        mode = spec["mode"]

        if mode == "two_sided":
            pred = self._eval_two_sided(sport, fixture_id, spec, X, odds, feat_completeness, league_key)
            return [pred] if pred else []

        if mode == "best_edge_across_lines":
            paired = [
                (line_spec, self._eval_line(sport, fixture_id, spec["db_market"], line_spec, X, odds, feat_completeness, league_key))
                for line_spec in spec["lines"]
            ]
            paired = [(ls, c) for ls, c in paired if c is not None]
            if not paired:
                return []
            # Real market odds only exist for the 2.5 line (the CSV import's
            # odds cascade never carries 1.5/3.5 lines) — falling back to a
            # flat baseline for the other two made their "edge" equal to
            # (roughly) their full raw probability against 2.5's genuine,
            # much smaller market-based edge, so this always picked
            # whichever line had the highest raw probability (Over 1.5,
            # almost every time) — exactly the "collapses to the safest
            # extreme" failure this edge-based mode was built to avoid.
            # Each line's own real historical base rate (baseline_prob) is
            # the correct fallback — Over 1.5 being true ~74% of the time
            # regardless of the match means a ~75% model probability has
            # almost no real edge, not a ~75% one.
            best_spec, best = max(
                paired,
                key=lambda t: t[1].model_probability - (
                    t[1].implied_probability if t[1].implied_probability is not None
                    else t[0].get("baseline_prob", 0.5)
                ),
            )
            return [best]

        if mode == "independent_lines":
            candidates = [
                self._eval_line(sport, fixture_id, spec["db_market"], line_spec, X, odds, feat_completeness, league_key)
                for line_spec in spec["lines"]
            ]
            return [c for c in candidates if c is not None]

        if mode == "three_way":
            pred = self._eval_three_way(sport, fixture_id, spec, X, odds, feat_completeness, league_key)
            return [pred] if pred else []

        if mode == "double_chance_derived":
            pred = self._eval_double_chance(sport, fixture_id, spec, X, odds, feat_completeness, league_key)
            return [pred] if pred else []

        raise ValueError(f"Unknown market mode {mode!r}")

    def _eval_three_way(
        self, sport: str, fixture_id: str, spec: dict[str, Any], X: pd.DataFrame,
        odds: OddsLookup, feat_completeness: float, league_key: str = "",
    ) -> PredictionResult | None:
        model = _ModelCache.get(sport, spec["model_key"])
        if model is None:
            return None

        batch = model.predict_proba(X)
        probs = batch.probabilities.iloc[0]   # index: Home / Draw / Away

        best_cls   = probs.idxmax()
        model_prob = float(probs[best_cls])
        side       = best_cls.lower()   # "home" / "draw" / "away"

        implied, dec_odds = odds.implied_and_odds(spec["db_market"], None, side)
        edge = (model_prob - implied) if implied is not None else None
        overround = implied if implied is not None else 1.02
        confidence = _confidence_score(model_prob, edge, overround=overround, feature_completeness=feat_completeness)

        return PredictionResult(
            sport=sport, fixture_id=fixture_id, market=spec["db_market"], selection=best_cls,
            model_probability=round(model_prob, 4),
            implied_probability=round(implied, 4) if implied is not None else None,
            odds=round(dec_odds, 3) if dec_odds is not None else None,
            confidence=confidence, league_key=league_key,
        )

    def _eval_double_chance(
        self, sport: str, fixture_id: str, spec: dict[str, Any], X: pd.DataFrame,
        odds: OddsLookup, feat_completeness: float, league_key: str = "",
    ) -> PredictionResult | None:
        """
        Not a separately trained model — sums the already-calibrated 1x2
        probabilities (P(1X)=P(Home)+P(Draw), etc.) so it inherits 1x2's own
        §1.2 calibration exactly, rather than needing its own.
        """
        model = _ModelCache.get(sport, spec["model_key"])   # "1x2" model
        if model is None:
            return None

        batch = model.predict_proba(X)
        probs = batch.probabilities.iloc[0]   # Home / Draw / Away
        p_home, p_draw, p_away = float(probs.get("Home", 0.0)), float(probs.get("Draw", 0.0)), float(probs.get("Away", 0.0))

        combos = {
            "1X": (p_home + p_draw, ("home", "draw")),
            "X2": (p_draw + p_away, ("draw", "away")),
            "12": (p_home + p_away, ("home", "away")),
        }

        best_sel, best_edge, best_prob, best_implied, best_odds = None, None, None, None, None
        for sel, (model_prob, sides) in combos.items():
            implied_a, _ = odds.implied_and_odds("1X2", None, sides[0])
            implied_b, _ = odds.implied_and_odds("1X2", None, sides[1])
            implied = (implied_a + implied_b) if implied_a is not None and implied_b is not None else None
            edge = (model_prob - implied) if implied is not None else model_prob - (2.0 / 3.0)
            if best_edge is None or edge > best_edge:
                best_sel, best_edge, best_prob, best_implied = sel, edge, model_prob, implied

        overround = best_implied if best_implied is not None else 1.02
        confidence = _confidence_score(best_prob, best_edge, overround=overround, feature_completeness=feat_completeness)

        return PredictionResult(
            sport=sport, fixture_id=fixture_id, market=spec["db_market"], selection=best_sel,
            model_probability=round(best_prob, 4),
            implied_probability=round(best_implied, 4) if best_implied is not None else None,
            odds=None,   # no direct market odds for a derived selection
            confidence=confidence, league_key=league_key,
        )

    def _eval_two_sided(
        self, sport: str, fixture_id: str, spec: dict[str, Any], X: pd.DataFrame,
        odds: OddsLookup, feat_completeness: float, league_key: str = "",
    ) -> PredictionResult | None:
        model = _ModelCache.get(sport, spec["model_key"])
        if model is None:
            return None

        batch   = model.predict_proba(X)
        classes = list(batch.probabilities.columns)
        probs   = batch.probabilities.iloc[0]

        best_cls  = probs.idxmax()
        model_prob = float(probs[best_cls])

        side = "yes" if best_cls.lower() in ("yes", "over") else "no"
        # For Cards ("Over 3.5"/"Under 3.5") the class text IS the selection.
        selection = best_cls if spec["line"] else best_cls
        odds_side = "over" if "over" in best_cls.lower() else ("under" if "under" in best_cls.lower() else side)

        implied, dec_odds = odds.implied_and_odds(spec["db_market"], spec["line"], odds_side)
        edge = (model_prob - implied) if implied is not None else None
        overround = self._overround_for(classes, probs) if implied is None else max(implied, 1.0 / max(model_prob, 1e-6))
        confidence = _confidence_score(model_prob, edge, overround=1.02 if implied is None else overround, feature_completeness=feat_completeness)

        return PredictionResult(
            sport=sport, fixture_id=fixture_id, market=spec["db_market"], selection=selection,
            model_probability=round(model_prob, 4),
            implied_probability=round(implied, 4) if implied is not None else None,
            odds=round(dec_odds, 3) if dec_odds is not None else None,
            confidence=confidence, league_key=league_key,
        )

    def _eval_line(
        self, sport: str, fixture_id: str, db_market: str, line_spec: dict[str, Any], X: pd.DataFrame,
        odds: OddsLookup, feat_completeness: float, league_key: str = "",
    ) -> PredictionResult | None:
        model = _ModelCache.get(sport, line_spec["model_key"])
        if model is None:
            return None

        batch   = model.predict_proba(X)
        side    = line_spec["side"]
        target_cls = next(
            (c for c in batch.probabilities.columns if c.lower() == side or side in c.lower()),
            None,
        )
        if target_cls is None:
            logger.warning("Model %s/%s has no %r class — got %s",
                           sport, line_spec["model_key"], side, list(batch.probabilities.columns))
            return None
        model_prob = float(batch.probabilities.iloc[0][target_cls])

        implied, dec_odds = odds.implied_and_odds(db_market, line_spec["line"], side)
        edge = (model_prob - implied) if implied is not None else None
        overround = implied if implied is not None else 1.02
        confidence = _confidence_score(model_prob, edge, overround=1.02, feature_completeness=feat_completeness)

        return PredictionResult(
            sport=sport, fixture_id=fixture_id, market=db_market, selection=line_spec["selection"],
            model_probability=round(model_prob, 4),
            implied_probability=round(implied, 4) if implied is not None else None,
            odds=round(dec_odds, 3) if dec_odds is not None else None,
            confidence=confidence, league_key=league_key,
        )

    @staticmethod
    def _overround_for(classes: list[str], probs: pd.Series) -> float:
        return 1.02

    # ── Helpers ─────────────────────────────────────────────────

    def _load_odds(self, sport: str, fixture_id: str) -> list[dict]:
        res = (
            self.client.table("fixture_odds")
            .select("*")
            .eq("sport", sport)
            .eq("fixture_id", fixture_id)
            .execute()
        )
        return res.data or []

    def _load_league_key(self, sport: str, fixture_id: str) -> str:
        """predictions.league_key is NOT NULL — pull it from the fixture."""
        res = (
            self.client.table("fixtures")
            .select("league_key")
            .eq("sport", sport).eq("fixture_id", fixture_id)
            .limit(1).execute()
        )
        rows = res.data or []
        return rows[0].get("league_key") or "" if rows else ""

    def _persist(self, results: list[PredictionResult]) -> None:
        """
        Row-by-row, not one batch upsert — predictions has a UNIQUE
        constraint on (sport, fixture_id, market, selection), and Corners
        legitimately emits TWO rows under the same market
        ("Over_Under_Corners") for its two lines (§1.3 — both lines are
        required, not a workaround); a batch call is atomic in Postgres, so
        one bad row would silently kill every other valid row in the same
        call. Uses upsert (not insert) on that same unique key so
        re-running prediction generation after a model fix — e.g. excluding
        a base model that turned out to saturate into a near-constant
        output — actually overwrites the stale row instead of silently
        failing with a duplicate-key error and leaving the old value in
        place (confirmed live: re-running after the NN exclusion fix hit
        exactly this with plain insert).
        """
        ok = 0
        for r in results:
            try:
                self.client.table("predictions").upsert(
                    r.to_db_row(), on_conflict="sport,fixture_id,market,selection"
                ).execute()
                ok += 1
            except Exception as exc:
                logger.error("Failed to persist prediction %s/%s: %s", r.market, r.selection, exc)
        logger.info("Persisted %d/%d predictions", ok, len(results))
