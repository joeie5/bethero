"""
base_importer.py — Shared base class for all sport historical data importers.

Live schema (see app/ml/feature_engineer.py for the verified column list)
---------------------------------------------------------------------------
    fixtures        PK (sport, fixture_id) — scheduling/context, no scores
    match_results   PK (sport, fixture_id) — post-match stats (label source)
    teams           PK id (bigint identity), unique (sport, team_name)
    fixture_odds    — bookmaker odds per (sport, fixture_id, bookmaker, market)

There is no `leagues` table in the live schema — league is carried as plain
text (`league_key`, `league_name`) directly on `fixtures`.

Features
--------
- Recursively discovers CSV and JSON files under a given folder
- Normalises team names via a configurable alias map + fuzzy matching (difflib)
- Generates a deterministic fixture_id (sha1 of sport|home|away|date) since
  these historical CSVs carry no external fixture id — this keeps re-runs
  idempotent via upsert rather than inserting duplicates
- Writes fixtures and match_results separately, matching the live schema's
  scheduling/post-match-stats split (which is also the §1.1 leakage boundary)
- Upserts into Supabase in configurable batch sizes (default 1000)
- Structured logging with per-file progress
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import difflib
import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────── Team Name Registry ────────────────────────────

class TeamRegistry:
    """
    Holds a canonical name → DB id mapping and resolves aliases / fuzzy matches.
    Populated lazily from the teams table at importer startup.
    """

    def __init__(self, extra_aliases: dict[str, str] | None = None):
        # canonical_name → team_id
        self._id_map: dict[str, int] = {}
        # raw alias → canonical_name (built from aliases + DB team_name)
        self._alias_map: dict[str, str] = {}
        if extra_aliases:
            for alias, canonical in extra_aliases.items():
                self._alias_map[alias.lower().strip()] = canonical.lower().strip()

    def register(self, team_id: int, name: str) -> None:
        key = name.lower().strip()
        self._id_map[key] = team_id
        self._alias_map[key] = key

    def resolve_id(self, raw_name: str) -> int | None:
        """
        Returns DB team_id for *raw_name*.
        1. Exact alias match (fast)
        2. Fuzzy match against all known canonical names (fallback)
        """
        if not raw_name:
            return None
        key = self._normalize(raw_name)

        canonical = self._alias_map.get(key)
        if canonical and canonical in self._id_map:
            return self._id_map[canonical]

        all_keys = list(self._id_map.keys())
        matches = difflib.get_close_matches(key, all_keys, n=1, cutoff=0.75)
        if matches:
            logger.debug("Fuzzy matched '%s' -> '%s'", raw_name, matches[0])
            self._alias_map[key] = matches[0]
            return self._id_map[matches[0]]

        return None

    @staticmethod
    def _normalize(name: str) -> str:
        name = name.lower().strip()
        name = re.sub(r"['\-–]", " ", name)
        name = re.sub(r"\s+", " ", name)
        return name


# ─────────────────────────── fixture_id generation ─────────────────────────

def make_fixture_id(sport: str, home_name: str, away_name: str, match_date: str) -> str:
    """
    Deterministic fixture id for historical CSV rows that carry no external
    provider id. Stable across re-runs so upserts stay idempotent instead of
    duplicating rows on every import.
    """
    key = f"{sport}|{home_name.strip().lower()}|{away_name.strip().lower()}|{match_date}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


# ─────────────────────────── Base Importer ─────────────────────────────────

class BaseImporter(ABC):
    """
    Abstract base for all sport importers.

    Subclasses must implement:
        sport_slug: str
        load_aliases() -> dict[str, str]
        normalize(df, source_file) -> pd.DataFrame  (unified schema rows)
    """

    BATCH_SIZE = 500

    def __init__(self, data_dir: str | Path, supabase_admin):
        self.data_dir = Path(data_dir)
        self.client = supabase_admin   # service-role Supabase client
        self.registry = TeamRegistry(extra_aliases=self.load_aliases())
        self._sport: str | None = None

    # ── Abstract interface ──────────────────────────────────────

    @property
    @abstractmethod
    def sport_slug(self) -> str: ...

    @abstractmethod
    def load_aliases(self) -> dict[str, str]:
        """Return {raw_name: canonical_name} alias mappings for this sport."""
        ...

    @abstractmethod
    def normalize(self, df: pd.DataFrame, source_file: Path) -> pd.DataFrame:
        """
        Transform a raw DataFrame into rows matching the unified schema:
            home_team_name, away_team_name, match_date (ISO str),
            league_key, league_name, season, round (opt), venue (opt),
            home_score (opt), away_score (opt), status,
            extra_stats (opt dict — sport-specific post-match columns,
                         e.g. corners/cards for football when available),
            odds (opt list[dict] — rows ready for fixture_odds)
        """
        ...

    # ── Template method: run() ──────────────────────────────────

    def run(self) -> None:
        logger.info("[%s] Starting import from %s", self.sport_slug, self.data_dir)
        self._sport = self.sport_slug
        self._ensure_sport_catalog_row()
        self._load_team_registry()

        files = self._discover_files()
        logger.info("[%s] Found %d files", self.sport_slug, len(files))

        total_inserted = total_skipped = total_errors = 0

        for file_path in files:
            logger.info("[%s] Processing %s", self.sport_slug, file_path.name)
            try:
                raw_df = self._read_file_safe(file_path)
                if raw_df is None or raw_df.empty:
                    continue
                norm_df = self.normalize(raw_df, file_path)
                if norm_df is None or norm_df.empty:
                    continue
                inserted, skipped = self._upsert_fixtures(norm_df)
                total_inserted += inserted
                total_skipped  += skipped
            except Exception as exc:
                logger.error("[%s] Error in %s: %s", self.sport_slug, file_path.name, exc, exc_info=True)
                total_errors += 1

        logger.info(
            "[%s] Done — inserted=%d skipped=%d file_errors=%d",
            self.sport_slug, total_inserted, total_skipped, total_errors,
        )

    # ── File discovery ──────────────────────────────────────────

    def _discover_files(self) -> list[Path]:
        files: list[Path] = []
        for pattern in ("**/*.csv", "**/*.json"):
            files.extend(self.data_dir.rglob(pattern))
        return sorted(set(files))

    def _read_file_safe(self, path: Path) -> pd.DataFrame | None:
        try:
            if path.suffix.lower() == ".json":
                with path.open(encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                return pd.DataFrame(data if isinstance(data, list) else [data])
            else:
                for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
                    try:
                        return pd.read_csv(path, encoding=enc, low_memory=False)
                    except UnicodeDecodeError:
                        continue
        except Exception as exc:
            logger.error("Failed to read %s: %s", path, exc)
        return None

    # ── Supabase helpers ────────────────────────────────────────

    def _ensure_sport_catalog_row(self) -> None:
        """sports_catalog already ships with all 7 sports pre-seeded — no-op if present."""
        res = self.client.table("sports_catalog").select("sport").eq("sport", self.sport_slug).execute()
        if not res.data:
            logger.warning(
                "[%s] sport not present in sports_catalog — fixtures FK will fail until it's added",
                self.sport_slug,
            )

    def _load_team_registry(self) -> None:
        res = (
            self.client.table("teams")
            .select("id, team_name")
            .eq("sport", self._sport)
            .execute()
        )
        for row in (res.data or []):
            self.registry.register(row["id"], row["team_name"])
        logger.info("[%s] Loaded %d teams into registry", self.sport_slug, len(res.data or []))

    def _get_or_create_team(self, name: str) -> int:
        team_id = self.registry.resolve_id(name)
        if team_id:
            return team_id
        data = {"sport": self._sport, "team_name": name.strip()}
        res = (
            self.client.table("teams")
            .upsert(data, on_conflict="sport,team_name")
            .execute()
        )
        tid = res.data[0]["id"]
        self.registry.register(tid, name)
        return tid

    def _upsert_fixtures(self, df: pd.DataFrame) -> tuple[int, int]:
        """Batch-upsert normalised rows into fixtures + match_results + fixture_odds."""
        inserted = skipped = 0
        rows = df.to_dict(orient="records")

        for batch_start in range(0, len(rows), self.BATCH_SIZE):
            batch = rows[batch_start : batch_start + self.BATCH_SIZE]
            fixture_rows: list[dict[str, Any]] = []
            result_rows:  list[dict[str, Any]] = []
            odds_rows:    list[dict[str, Any]] = []

            for row in batch:
                try:
                    fx, res, odds = self._build_rows(row)
                    if fx is None:
                        skipped += 1
                        continue
                    fixture_rows.append(fx)
                    if res is not None:
                        result_rows.append(res)
                    odds_rows.extend(odds)
                except Exception as exc:
                    logger.debug("Skipping row (%s): %s", row, exc)
                    skipped += 1

            if fixture_rows:
                try:
                    fx_res = (
                        self.client.table("fixtures")
                        .upsert(fixture_rows, on_conflict="sport,fixture_id")
                        .execute()
                    )
                    inserted += len(fx_res.data or [])
                except Exception as exc:
                    logger.error("Fixtures batch upsert failed: %s", exc)
                    skipped += len(fixture_rows)
                    continue

            if result_rows:
                try:
                    self.client.table("match_results").upsert(
                        result_rows, on_conflict="sport,fixture_id"
                    ).execute()
                except Exception as exc:
                    logger.error("match_results batch upsert failed: %s", exc)

            if odds_rows:
                try:
                    # fixture_odds is keyed by a coalesce(line,-1) expression index
                    # (NULL lines wouldn't dedupe under plain ON CONFLICT semantics),
                    # so PostgREST upsert can't target it directly — instead delete
                    # this batch's existing odds rows and re-insert, keeping re-runs
                    # idempotent without duplicating rows.
                    fixture_ids = sorted({r["fixture_id"] for r in odds_rows})
                    self.client.table("fixture_odds").delete().eq(
                        "sport", self._sport
                    ).in_("fixture_id", fixture_ids).execute()
                    self.client.table("fixture_odds").insert(odds_rows).execute()
                except Exception as exc:
                    logger.error("fixture_odds batch upsert failed: %s", exc)

        return inserted, skipped

    def _build_rows(
        self, row: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
        home_name = str(row.get("home_team_name", "") or "").strip()
        away_name = str(row.get("away_team_name", "") or "").strip()
        if home_name.lower() == "nan":
            home_name = ""
        if away_name.lower() == "nan":
            away_name = ""
        if not home_name or not away_name:
            return None, None, []

        match_date = row.get("match_date")
        if not match_date:
            return None, None, []
        if isinstance(match_date, str):
            parsed = self._parse_date(match_date)
        else:
            parsed = match_date
        if parsed is None:
            return None, None, []
        date_iso = parsed.date().isoformat() if isinstance(parsed, datetime) else str(parsed)

        home_id = self._get_or_create_team(home_name)
        away_id = self._get_or_create_team(away_name)
        fixture_id = make_fixture_id(self._sport, home_name, away_name, date_iso)

        fixture_row: dict[str, Any] = {
            "sport":          self._sport,
            "fixture_id":     fixture_id,
            "provider":       "historical_csv",
            "league_key":     str(row.get("league_key", "") or "unknown"),
            "league_name":    str(row.get("league_name", "Unknown") or "Unknown"),
            "season":         self._safe_int(row.get("season")),
            "round":          str(row.get("round", "") or "") or None,
            "match_date":     date_iso,
            "venue":          str(row.get("venue", "") or "") or None,
            "status":         str(row.get("status", "FT") or "FT"),
            "home_team":      home_name,
            "home_team_id":   home_id,
            "away_team":      away_name,
            "away_team_id":   away_id,
        }

        result_row: dict[str, Any] | None = None
        home_score = row.get("home_score")
        away_score = row.get("away_score")
        if home_score is not None and away_score is not None:
            hg, ag = self._safe_int(home_score), self._safe_int(away_score)
            if hg is not None and ag is not None:
                result_row = {
                    "sport":       self._sport,
                    "fixture_id":  fixture_id,
                    "home_team":   home_name,
                    "away_team":   away_name,
                    "status":      "FT",
                    "home_goals":  hg,
                    "away_goals":  ag,
                    "ftr":         "H" if hg > ag else ("A" if ag > hg else "D"),
                    "btts":        bool(hg > 0 and ag > 0),
                    "over25":      bool((hg + ag) > 2.5),
                    "over15":      bool((hg + ag) > 1.5),
                }
                extra = row.get("extra_stats") or {}
                result_row.update(extra)

        odds_rows: list[dict[str, Any]] = []
        for o in (row.get("odds") or []):
            odds_row = dict(o)
            odds_row["sport"] = self._sport
            odds_row["fixture_id"] = fixture_id
            odds_rows.append(odds_row)

        return fixture_row, result_row, odds_rows

    # ── Utility helpers ─────────────────────────────────────────

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        formats = [
            "%d/%m/%Y", "%d/%m/%y",
            "%Y-%m-%d", "%m/%d/%Y",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
            "%d-%m-%Y", "%d %b %Y", "%B %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(value.strip(), fmt)
            except (ValueError, AttributeError):
                continue
        return None

    @staticmethod
    def _safe_int(val: Any) -> int | None:
        try:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            return int(float(val))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_float(val: Any) -> float | None:
        try:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            return float(val)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
        """Drop all-NA rows and reset index."""
        return df.dropna(how="all").drop_duplicates().reset_index(drop=True)
