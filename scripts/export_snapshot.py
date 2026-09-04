"""
export_snapshot.py — One-time bulk export of live Supabase tables to local
Parquet files under data_snapshot/, so feature building and training never
issue per-fixture REST round-trips again.

Usage:
    PYTHONPATH=. python3 scripts/export_snapshot.py [sport]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

from app.database import get_supabase_admin

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "data_snapshot"
PAGE_SIZE = 10_000


def fetch_all(client, table: str, select: str, filters: dict | None = None) -> pd.DataFrame:
    """
    PostgREST caps each response at its own server-side max-rows (commonly
    1000) regardless of the requested range width — so "got fewer rows than
    requested" does NOT mean "last page." Only an empty batch means done;
    otherwise keep advancing the offset by however many rows actually came back.
    """
    rows: list[dict] = []
    offset = 0
    page = 0
    t0 = time.monotonic()
    while True:
        q = client.table(table).select(select)
        for col, val in (filters or {}).items():
            q = q.eq(col, val)
        q = q.range(offset, offset + PAGE_SIZE - 1)
        res = q.execute()
        batch = res.data or []
        if not batch:
            break
        rows.extend(batch)
        print(f"  [{table}] page {page} -> {len(batch)} rows (total {len(rows)})")
        offset += len(batch)
        page += 1
    print(f"[{table}] done: {len(rows)} rows in {time.monotonic() - t0:.1f}s")
    return pd.DataFrame(rows)


def main(sport: str = "football") -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    client = get_supabase_admin()

    tables = {
        "fixtures": ("*", {"sport": sport}),
        "match_results": ("*", {"sport": sport}),
        "fixture_odds": ("*", {"sport": sport}),
        "team_form_cache": ("*", {"sport": sport}),
        "teams": ("*", {"sport": sport}),
    }

    for name, (select, filters) in tables.items():
        df = fetch_all(client, name, select, filters)
        out = SNAPSHOT_DIR / f"{name}_{sport}.parquet"
        df.to_parquet(out, index=False)
        print(f"[{name}] saved -> {out} ({len(df)} rows)")

    print("\nSnapshot complete:", SNAPSHOT_DIR)


if __name__ == "__main__":
    sport = sys.argv[1] if len(sys.argv) > 1 else "football"
    main(sport)
