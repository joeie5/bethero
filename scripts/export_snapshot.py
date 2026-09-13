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


def fetch_all(client, table: str, select: str, filters: dict | None = None,
              order_cols: list[str] | None = None) -> pd.DataFrame:
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
        # Without a stable order, Postgres/PostgREST doesn't guarantee a
        # consistent row partition across separate paginated requests —
        # any concurrent write between page fetches (e.g. an importer run
        # upserting into this same table, which happened repeatedly the
        # night this bug was found) can shift the query plan's ordering,
        # causing offset-based pagination to both skip AND repeat rows.
        # No single column is guaranteed present/unique across every table
        # this script touches (fixtures/team_form_cache have no `id`), so
        # the caller supplies whichever column(s) are actually stable+unique
        # for that table.
        for col in (order_cols or []):
            q = q.order(col)
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

    # order_cols must be a combination that's actually unique per row, since
    # it's the only thing keeping offset-based pagination stable — see
    # fetch_all's docstring.
    tables = {
        "fixtures":        ("*", {"sport": sport}, ["fixture_id"]),
        "match_results":   ("*", {"sport": sport}, ["fixture_id"]),
        "fixture_odds":    ("*", {"sport": sport}, ["id"]),
        "team_form_cache": ("*", {"sport": sport}, ["team_id", "as_of_date"]),
        "teams":           ("*", {"sport": sport}, ["id"]),
    }

    for name, (select, filters, order_cols) in tables.items():
        df = fetch_all(client, name, select, filters, order_cols)
        out = SNAPSHOT_DIR / f"{name}_{sport}.parquet"
        df.to_parquet(out, index=False)
        print(f"[{name}] saved -> {out} ({len(df)} rows)")

    print("\nSnapshot complete:", SNAPSHOT_DIR)


if __name__ == "__main__":
    sport = sys.argv[1] if len(sys.argv) > 1 else "football"
    main(sport)
