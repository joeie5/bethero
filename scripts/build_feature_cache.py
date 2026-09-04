"""
build_feature_cache.py — Build the full feature matrix ONCE for every finished
football fixture, so all 7 markets in predictor.MARKET_SPEC can train off the
same cache instead of each re-running FeatureEngineer.build_batch() from
scratch (a fixture's 128-feature vector doesn't depend on which market you're
predicting — only the label does).

Runs entirely offline against data_snapshot/ (see scripts/export_snapshot.py)
— no Supabase requests.

Usage:
    PYTHONPATH=. python3 scripts/build_feature_cache.py [chunk_size] [cache_root]

    cache_root defaults to data_snapshot/ (next to this script's parent).
    Pass a path on a drive with more free space (e.g. D:\\bethero_cache) if
    C: runs low — part files and the final cache both live under cache_root.

Design notes (v3)
------------------
- v1 crashed with an OOM around row 15,000/297,904: it re-concatenated and
  rewrote the ENTIRE accumulated dataset to disk every chunk (O(n^2)
  memory/CPU).
- v2 fixed the OOM (each chunk writes its own small part file instead) but
  ran ~1.5x slower than the original benchmark, because FeatureEngineer's
  DixonColes/league-table caches are keyed by (league_key, exact date) and
  were being cleared every chunk. Fixtures were processed in GLOBAL date
  order, so a 2000-row chunk interleaved ~15-20 different countries —
  cache hits within a chunk were already rare even before clearing, so the
  fix cost real recompute for no real memory benefit.
- v3 (this version): process fixtures GROUPED BY LEAGUE, each league fully
  in its own chronological order. Consecutive fixtures within a league
  share nearly the same date and opponent pool, so the (league, date)
  cache gets genuine reuse across a whole league's run — caches are only
  cleared when moving to the NEXT league, not every chunk. Part files are
  still written periodically within a league for crash-resumability
  without losing the accumulated cache reuse mid-league.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

from app.ml.feature_engineer import FeatureEngineer

DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "data_snapshot"
LABEL_COLS = ["btts", "total_cards", "total_corners", "home_goals", "away_goals"]


def main(chunk_size: int = 2000, cache_root: Path | None = None) -> None:
    cache_root = Path(cache_root) if cache_root else DEFAULT_ROOT
    parts_dir = cache_root / "feature_cache_parts"
    out_path = cache_root / "feature_cache_football.parquet"
    parts_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot data itself always comes from DEFAULT_ROOT (where export_snapshot.py
    # put it) — cache_root only controls where the (much smaller) feature cache
    # and its part files are written, so a separate drive can be used if needed.
    fe = FeatureEngineer(supabase_client=None, data_dir=DEFAULT_ROOT)

    mr = fe._local["match_results"]
    fx = fe._local["fixtures"]
    eligible = mr[mr["home_goals"].notna()].copy()
    eligible = eligible.merge(fx[["fixture_id", "match_date", "league_key"]], on="fixture_id", how="inner")
    eligible["match_date"] = pd.to_datetime(eligible["match_date"], errors="coerce")
    eligible = eligible.dropna(subset=["match_date"])

    total = len(eligible)
    print(f"Eligible fixtures: {total}  |  cache_root: {cache_root}")

    done_ids: set[str] = set()
    existing_parts = sorted(parts_dir.glob("part_*.parquet"))
    for p in existing_parts:
        done_ids.update(pd.read_parquet(p, columns=["fixture_id"])["fixture_id"])
    if done_ids:
        print(f"Resuming — {len(done_ids)} fixtures already cached in {len(existing_parts)} part files")

    remaining = eligible[~eligible["fixture_id"].isin(done_ids)]
    print(f"Remaining: {len(remaining)}")

    leagues = remaining.groupby("league_key", dropna=False)
    league_sizes = leagues.size().sort_values(ascending=False)
    print(f"Leagues to process: {len(league_sizes)}")

    next_part_num = len(existing_parts)
    t_start = time.monotonic()
    processed = len(done_ids)

    for league_key in league_sizes.index:
        league_df = leagues.get_group(league_key).sort_values("match_date").reset_index(drop=True)
        n_league = len(league_df)
        print(f"\n--- League {league_key!r}: {n_league} fixtures ---", flush=True)

        for start in range(0, n_league, chunk_size):
            batch = league_df.iloc[start:start + chunk_size]
            pairs = list(zip(["football"] * len(batch), batch["fixture_id"].tolist()))

            t0 = time.monotonic()
            feats = fe.build_batch(pairs)
            if feats.empty:
                continue

            merged = feats.merge(batch[["fixture_id"] + LABEL_COLS + ["match_date"]], on="fixture_id", how="left")
            part_path = parts_dir / f"part_{next_part_num:05d}.parquet"
            merged.to_parquet(part_path, index=False)
            next_part_num += 1
            processed += len(merged)

            # Clear every chunk regardless of league boundary — some leagues
            # (e.g. a Div-code gap grouping matches across many scattered
            # seasons) span far more distinct dates than expected, and letting
            # (league,date)-keyed caches grow unbounded within one large
            # league risks the same OOM a purely between-league clear allowed.
            # Chunks are still date-contiguous within a league, so nearby
            # fixtures in the same chunk still benefit before the clear.
            fe._dc_cache.clear()
            fe._table_cache.clear()
            fe._elo_cache.clear()

            elapsed_chunk = time.monotonic() - t0
            elapsed_total = time.monotonic() - t_start
            rate = elapsed_chunk / max(len(batch), 1)
            remaining_n = total - processed
            eta_s = remaining_n * rate
            print(
                f"[{processed}/{total}] league={league_key} chunk={len(batch)} in {elapsed_chunk:.1f}s "
                f"({rate:.3f}s/row) — elapsed {elapsed_total/60:.1f}min, ETA {eta_s/60:.1f}min",
                flush=True,
            )

    # Final merge — only done once, at completion.
    parts = sorted(parts_dir.glob("part_*.parquet"))
    final = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True) if parts else pd.DataFrame()
    final.to_parquet(out_path, index=False)
    print(f"\nDone — {len(final)} rows written to {out_path}")
    print(f"Total time: {(time.monotonic() - t_start)/60:.1f} minutes")


if __name__ == "__main__":
    chunk_size = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    cache_root = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    main(chunk_size, cache_root)
