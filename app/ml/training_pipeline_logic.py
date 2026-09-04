"""
training_pipeline_logic.py — Core training and data loading logic.

Trains real, calibrated StackingEnsemble models for the markets defined in
app.ml.predictor.MARKET_SPEC, against the live fixtures/match_results schema.
Model files land flat under app.ml.models.MODEL_DIR — the exact location
predictor.py's _ModelCache expects (StackingEnsemble_{sport}_{model_key}.joblib),
so anything trained here is immediately loadable for prediction.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd

from app.database import get_supabase_admin
from app.ml.feature_engineer import FeatureEngineer
from app.ml.feature_validator import validate_before_training
from app.ml.models import (
    BetHeroBaseModel,
    LightGBMBetModel,
    LSTMBetModel,
    MODEL_DIR,
    NeuralNetworkBetModel,
    RandomForestBetModel,
    StackingEnsemble,
    TrainingResult,
    XGBoostBetModel,
)

logger = logging.getLogger(__name__)

# ─────────────────────────── Constants ─────────────────────────────────────

VAL_FRACTION: float  = 0.15
CAL_FRACTION: float  = 0.15   # §1.2 — held-out ~15%, must be the MOST RECENT slice
MIN_ROWS: int        = 200
DEFAULT_N_TRIALS: int = 50

# Raw label columns build_feature_cache.py merges into feature_cache_{sport}.parquet
# so every market can read its own target back out (see scripts/build_feature_cache.py
# LABEL_COLS). They must never reach model.fit() as features — whichever one matches
# the market being trained is the target itself (§1.1).
LABEL_COLS: set[str] = {"btts", "total_cards", "total_corners", "home_goals", "away_goals"}

MODEL_REGISTRY: dict[str, type[BetHeroBaseModel]] = {
    "random_forest":    RandomForestBetModel,
    "xgboost":          XGBoostBetModel,
    "lightgbm":         LightGBMBetModel,
    "neural_network":   NeuralNetworkBetModel,
    "lstm":             LSTMBetModel,
}

# ─────────────────────────── Data Classes ──────────────────────────────────

@dataclass
class PipelineConfig:
    sport:      str
    market:     str            # a predictor.MARKET_SPEC model_key, e.g. "BTTS", "Goals_2.5"
    model_name: str            # a MODEL_REGISTRY key, or "StackingEnsemble"
    n_trials:   int              = DEFAULT_N_TRIALS
    n_meta_trials: int           = 20
    dry_run:    bool             = False
    force:      bool             = False

@dataclass
class PipelineResult:
    sport:            str
    market:           str
    model_name:       str
    status:           str         # "ok" | "skipped" | "failed"
    training_result:  TrainingResult | None = None
    error:            str         = ""
    duration_s:       float       = 0.0
    model_path:       str         = ""
    mlflow_run_id:    str         = ""
    calibration_table: pd.DataFrame | None = None

# ─────────────────────────── Target Builder ────────────────────────────────

class MarketTargetBuilder:
    """
    One target function per predictor.MARKET_SPEC model_key, using the
    model_key strings directly so trained files line up with what
    predictor.py's _ModelCache loads.
    """

    @staticmethod
    def build(df: pd.DataFrame, model_key: str) -> pd.Series:
        total_goals = df["home_goals"].fillna(0) + df["away_goals"].fillna(0)

        if model_key == "BTTS":
            return pd.Series(np.where(df["btts"].fillna(False), "Yes", "No"), index=df.index)

        if model_key == "Cards_3.5":
            tc = df["total_cards"]
            return pd.Series(np.where(tc > 3.5, "Over 3.5", "Under 3.5"), index=df.index)

        if model_key == "Goals_1.5":
            return pd.Series(np.where(total_goals > 1.5, "Over 1.5", "Under 1.5"), index=df.index)
        if model_key == "Goals_2.5":
            return pd.Series(np.where(total_goals > 2.5, "Over 2.5", "Under 2.5"), index=df.index)
        if model_key == "Goals_3.5":
            return pd.Series(np.where(total_goals > 3.5, "Over 3.5", "Under 3.5"), index=df.index)

        if model_key == "Corners_7.5":
            tc = df["total_corners"]
            return pd.Series(np.where(tc > 7.5, "Over 7.5", "Under 7.5"), index=df.index)
        if model_key == "Corners_9.5":
            tc = df["total_corners"]
            return pd.Series(np.where(tc > 9.5, "Over 9.5", "Under 9.5"), index=df.index)

        if model_key == "1x2":
            hg, ag = df["home_goals"], df["away_goals"]
            return pd.Series(
                np.where(hg > ag, "Home", np.where(hg < ag, "Away", "Draw")),
                index=df.index,
            )

        raise ValueError(f"Unknown model_key {model_key!r} — no target rule defined")

    # Columns in match_results that must be non-null for this market's
    # target to be well-defined. Corners rows are null for Extra-tier
    # countries (§5) — those rows must be DROPPED, never zero-filled,
    # since zero-filling would fabricate a false "Under" label.
    REQUIRED_COLUMNS: dict[str, list[str]] = {
        "BTTS":       ["btts"],
        "Cards_3.5":  ["total_cards"],
        "Goals_1.5":  ["home_goals", "away_goals"],
        "Goals_2.5":  ["home_goals", "away_goals"],
        "Goals_3.5":  ["home_goals", "away_goals"],
        "Corners_7.5": ["total_corners"],
        "Corners_9.5": ["total_corners"],
        "1x2":        ["home_goals", "away_goals"],
    }


# ─────────────────────────── Data Loader ───────────────────────────────────

class TrainingDataLoader:
    """
    Builds a labeled training frame for one (sport, model_key) by pulling
    finished fixtures from match_results/fixtures and computing the real,
    leakage-safe feature vector for each via FeatureEngineer — the same
    pipeline used at prediction time, not a reimplementation.
    """

    def __init__(self, supabase_client, data_dir: "Path | None" = None):
        """
        data_dir : optional local Parquet snapshot (scripts/export_snapshot.py).
                   When set, no network requests are made — everything is read
                   from the in-memory snapshot, matching FeatureEngineer's
                   offline mode so training never hits Supabase per-fixture.
        """
        self.client = supabase_client
        self._data_dir = data_dir
        self._fe = FeatureEngineer(supabase_client, data_dir=data_dir)

    def load(
        self,
        sport: str,
        model_key: str,
        limit: int | None = None,
        countries: list[str] | None = None,
    ) -> pd.DataFrame | None:
        required = MarketTargetBuilder.REQUIRED_COLUMNS[model_key]

        cached = self._load_from_feature_cache(sport, model_key, required, countries, limit)
        if cached is not None:
            return cached

        if self._data_dir is not None:
            rows = self._load_offline(sport, required, countries)
        else:
            rows = self._load_online(sport, required, countries, limit)

        if not rows or len(rows) < MIN_ROWS:
            logger.warning("[%s/%s] Only %d labeled rows (need >= %d)", sport, model_key, len(rows or []), MIN_ROWS)
            return None

        df = pd.DataFrame(rows)
        df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
        df = df.dropna(subset=["match_date"]).sort_values("match_date").reset_index(drop=True)
        if limit:
            df = df.tail(limit).reset_index(drop=True)

        df["target"] = MarketTargetBuilder.build(df, model_key)

        logger.info("[%s/%s] Building features for %d fixtures …", sport, model_key, len(df))
        pairs = list(zip([sport] * len(df), df["fixture_id"].tolist()))
        feats = self._fe.build_batch(pairs)
        if feats.empty:
            return None

        merged = feats.merge(
            df[["fixture_id", "match_date", "target"]],
            on="fixture_id", how="inner",
        ).sort_values("match_date").reset_index(drop=True)
        return merged

    # ── shared feature cache (scripts/build_feature_cache.py) ────

    def _load_from_feature_cache(
        self, sport: str, model_key: str, required: list[str],
        countries: list[str] | None, limit: int | None,
    ) -> pd.DataFrame | None:
        """
        If a pre-built feature cache exists (one row per fixture, built once
        for the full eligible universe — see scripts/build_feature_cache.py),
        use it directly: attach this market's label and filter, no repeated
        FeatureEngineer.build_batch() pass. Every market shares the same
        underlying feature vectors, only the label/eligibility differs.
        """
        if self._data_dir is None:
            return None
        cache_path = Path(self._data_dir) / f"feature_cache_{sport}.parquet"
        if not cache_path.exists():
            return None

        df = pd.read_parquet(cache_path)
        for col in required:
            df = df[df[col].notna()]
        if countries:
            fx = self._fe._local["fixtures"][["fixture_id", "league_key"]]
            df = df.merge(fx, on="fixture_id", how="left")
            df = df[df["league_key"].isin(countries)]

        if df.empty or len(df) < MIN_ROWS:
            logger.warning("[%s/%s] Feature cache has only %d eligible rows (need >= %d)",
                           sport, model_key, len(df), MIN_ROWS)
            return None

        df = df.sort_values("match_date").reset_index(drop=True)
        if limit:
            df = df.tail(limit).reset_index(drop=True)
        df["target"] = MarketTargetBuilder.build(df, model_key)
        logger.info("[%s/%s] Loaded %d rows from feature cache (%s)",
                    sport, model_key, len(df), cache_path.name)
        return df

    # ── row loaders ─────────────────────────────────────────────

    def _load_online(
        self, sport: str, required: list[str], countries: list[str] | None, limit: int | None,
    ) -> list[dict]:
        query = (
            self.client.table("match_results")
            .select(
                "fixture_id, home_goals, away_goals, btts, total_cards, total_corners,"
                " fixtures!inner(match_date, league_key)"
            )
            .eq("sport", sport)
            .not_.is_("home_goals", "null")
        )
        for col in required:
            query = query.not_.is_(col, "null")
        if countries:
            query = query.in_("fixtures.league_key", countries)

        rows: list[dict] = []
        offset, psize = 0, 1_000
        while True:
            q = query.range(offset, offset + psize - 1)
            res = q.execute()
            batch = res.data or []
            if not batch:
                break
            for r in batch:
                fx = r.pop("fixtures", {}) or {}
                r["match_date"] = fx.get("match_date")
            rows.extend(batch)
            offset += len(batch)
            if limit and len(rows) >= limit:
                break
        return rows

    def _load_offline(
        self, sport: str, required: list[str], countries: list[str] | None,
    ) -> list[dict]:
        mr = self._fe._local["match_results"]
        fx = self._fe._local["fixtures"]
        mask = (mr["sport"] == sport) & mr["home_goals"].notna()
        for col in required:
            mask &= mr[col].notna()
        rows_df = mr[mask][["fixture_id", "home_goals", "away_goals", "btts", "total_cards", "total_corners"]]
        fx_cols = fx[["fixture_id", "match_date", "league_key"]]
        merged = rows_df.merge(fx_cols, on="fixture_id", how="inner")
        if countries:
            merged = merged[merged["league_key"].isin(countries)]
        return merged.to_dict(orient="records")


# ─────────────────────────── Splitter ──────────────────────────────────────

class TemporalSplitter:
    """
    Expanding-window split, calibration slice LAST (most recent) per §1.2 —
    "hold out the last ~15% of each training window purely for calibration,
    never used for fitting."
    """

    def split(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        n = len(df)
        n_cal = int(n * CAL_FRACTION)
        n_val = int(n * VAL_FRACTION)
        n_train = n - n_val - n_cal
        train = df.iloc[:n_train]
        val   = df.iloc[n_train: n_train + n_val]
        cal   = df.iloc[n_train + n_val:]           # most recent — true holdout
        return train, val, cal


# ─────────────────────────── Logger ────────────────────────────────────────

class MLflowLogger:
    def __init__(self):
        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "./mlruns"))

    def log_training(self, result: TrainingResult, config: PipelineConfig, model_path: str) -> str:
        mlflow.set_experiment(f"BetHero/{config.sport}/{config.market}")
        with mlflow.start_run(run_name=config.model_name) as run:
            mlflow.set_tags({"sport": config.sport, "market": config.market, "model": config.model_name})
            mlflow.log_params(result.best_params)
            mlflow.log_metrics({
                "val_accuracy": result.val_accuracy,
                "val_log_loss": result.val_log_loss,
            })
            if model_path:
                mlflow.log_artifact(model_path)
            return run.info.run_id


# ─────────────────────────── Trainer ───────────────────────────────────────

class ModelTrainer:
    def __init__(self, config: PipelineConfig, mlflow_logger: MLflowLogger, df: pd.DataFrame | None = None):
        self.config, self.mlflow = config, mlflow_logger
        self.client = get_supabase_admin()
        self._df = df   # allow reusing an already-loaded frame across base models + ensemble

    def run(self) -> PipelineResult:
        cfg = self.config
        t0 = time.monotonic()

        df = self._df
        if df is None:
            df = TrainingDataLoader(self.client).load(cfg.sport, cfg.market)
        if df is None:
            return PipelineResult(cfg.sport, cfg.market, cfg.model_name, "skipped", error="No data")

        split = TemporalSplitter()
        tr, va, ca = split.split(df)

        exclude = {"fixture_id", "sport", "match_date", "target"} | LABEL_COLS
        f_cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]

        Xt, xv, xc = tr[f_cols].fillna(0), va[f_cols].fillna(0), ca[f_cols].fillna(0)
        yt, yv, yc = tr["target"], va["target"], ca["target"]

        report = validate_before_training(
            Xt, yt, xv, yv,
            match_dates_train=tr["match_date"], match_dates_val=va["match_date"],
        )
        if not report.passed:
            return PipelineResult(cfg.sport, cfg.market, cfg.model_name, "failed",
                                   error=f"Leakage detected: {report.critical_errors}")

        if cfg.dry_run:
            return PipelineResult(cfg.sport, cfg.market, cfg.model_name, "skipped", error="dry_run")

        if cfg.model_name == "StackingEnsemble":
            model = StackingEnsemble(cfg.sport, cfg.market, model_dir=MODEL_DIR, n_meta_trials=cfg.n_meta_trials)
            model.load_base_models(MODEL_DIR)
            if not model._base_models:
                return PipelineResult(cfg.sport, cfg.market, cfg.model_name, "failed",
                                       error="No base models found on disk — train base models first")
            res = model.train(Xt, yt, xv, yv)
            model.calibrate(xc, yc)
            m_path = model.save()
            cal_table = model.calibration_table(xc, yc)
        else:
            cls = MODEL_REGISTRY[cfg.model_name]
            # Not every model does Optuna search — RF/XGB/LightGBM take n_trials,
            # NeuralNetwork/LSTM take epochs instead. Only pass what the
            # constructor actually accepts.
            import inspect
            accepted = set(inspect.signature(cls.__init__).parameters)
            extra_kwargs = {"n_trials": cfg.n_trials} if "n_trials" in accepted else {}
            model = cls(cfg.sport, cfg.market, model_dir=MODEL_DIR, **extra_kwargs)
            res = model.train(Xt, yt, xv, yv)
            model.calibrate(xc, yc)
            m_path = model.save()
            cal_table = None

        try:
            run_id = self.mlflow.log_training(res, cfg, str(m_path))
        except Exception as exc:
            logger.warning("MLflow logging failed (non-fatal): %s", exc)
            run_id = ""

        return PipelineResult(
            cfg.sport, cfg.market, cfg.model_name, "ok",
            training_result=res, model_path=str(m_path), mlflow_run_id=run_id,
            duration_s=round(time.monotonic() - t0, 1),
            calibration_table=cal_table,
        )


# ─────────────────────────── One-call driver ───────────────────────────────

def train_market(
    sport: str,
    model_key: str,
    n_trials: int = DEFAULT_N_TRIALS,
    n_meta_trials: int = 20,
    limit: int | None = None,
    countries: list[str] | None = None,
    dry_run: bool = False,
    data_dir: "Path | None" = None,
) -> list[PipelineResult]:
    """
    Train every base model, then the StackingEnsemble, for one (sport, model_key).

    This is the operation admin.py's /train routes and any scheduled retrain
    job should call — training a StackingEnsemble alone is not possible
    (ensemble.load_base_models() requires the 5 base model files to already
    exist on disk under MODEL_DIR).

    data_dir : optional local Parquet snapshot (scripts/export_snapshot.py) —
               when set, no network requests hit Supabase during training.
    """
    client = get_supabase_admin()
    df = TrainingDataLoader(client, data_dir=data_dir).load(sport, model_key, limit=limit, countries=countries)
    if df is None:
        return [PipelineResult(sport, model_key, "ALL", "skipped", error="No data")]

    logger.info("[%s/%s] Training frame: %d rows, %d features", sport, model_key, len(df),
                len([c for c in df.columns if c not in ("fixture_id", "sport", "match_date", "target")]))

    mlflow_logger = MLflowLogger()
    results: list[PipelineResult] = []

    for model_name in MODEL_REGISTRY:
        cfg = PipelineConfig(sport=sport, market=model_key, model_name=model_name,
                             n_trials=n_trials, n_meta_trials=n_meta_trials, dry_run=dry_run)
        res = ModelTrainer(cfg, mlflow_logger, df=df).run()
        results.append(res)
        logger.info("[%s/%s] %s -> %s", sport, model_key, model_name, res.status)
        if res.status == "failed":
            logger.error("[%s/%s] %s failed: %s — aborting ensemble stage", sport, model_key, model_name, res.error)
            return results

    cfg = PipelineConfig(sport=sport, market=model_key, model_name="StackingEnsemble",
                         n_trials=n_trials, n_meta_trials=n_meta_trials, dry_run=dry_run)
    ensemble_res = ModelTrainer(cfg, mlflow_logger, df=df).run()
    results.append(ensemble_res)
    logger.info("[%s/%s] StackingEnsemble -> %s", sport, model_key, ensemble_res.status)
    if ensemble_res.calibration_table is not None:
        logger.info("[%s/%s] Calibration table:\n%s", sport, model_key,
                    ensemble_res.calibration_table.to_string(index=False))

    return results
