"""
Generic Supabase Storage sync for the backtest tool.

Design goal: this must scale beyond today's exact file list (17 football
leagues, 4 sports "all_games.csv", tennis/cricket archives). It works by
LISTING whatever is in a given sport's folder and downloading every CSV it
finds, rather than hardcoding filenames. Drop a new league CSV into
football/ in Storage and it will be picked up on the next sync with no
code change.
"""
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BUCKET = "sports-data"
DATA_DIR = Path(__file__).parent.parent / "data"

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
}

SPORT_FOLDERS = [
    "football", "cricket", "mlb", "nba", "nfl", "tennis_atp", "tennis_wta",
]


def list_folder(prefix: str) -> list[dict]:
    """List all objects under a prefix (non-recursive per Supabase API, so we
    walk one level and recurse into any sub-folders returned)."""
    url = f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET}"
    out = []
    stack = [prefix]
    seen = set()
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        resp = requests.post(url, headers=HEADERS, json={"prefix": p, "limit": 1000}, timeout=30)
        resp.raise_for_status()
        items = resp.json()
        for item in items:
            name = item.get("name")
            if name is None:
                continue
            full = f"{p.rstrip('/')}/{name}" if p else name
            if item.get("id") is None and item.get("metadata") is None:
                # folder (no metadata) -> recurse
                stack.append(full + "/")
            else:
                out.append({"path": full, "size": item.get("metadata", {}).get("size")})
    return out


def download(path: str, dest: Path) -> Path:
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}"
    resp = requests.get(url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def sync_sport(sport: str, force: bool = False) -> list[Path]:
    """Download every CSV currently in Storage under <sport>/ that we don't
    already have locally (or all of them if force=True). Generic — does not
    assume any particular filename."""
    objs = list_folder(f"{sport}/")
    local_paths = []
    for obj in objs:
        rel = obj["path"]
        if not rel.lower().endswith(".csv"):
            continue
        dest = DATA_DIR / rel
        if force or not dest.exists() or dest.stat().st_size != (obj.get("size") or -1):
            download(rel, dest)
        local_paths.append(dest)
    return local_paths


def sync_all(force: bool = False) -> dict:
    result = {}
    for sport in SPORT_FOLDERS:
        try:
            result[sport] = sync_sport(sport, force=force)
        except Exception as e:
            result[sport] = f"ERROR: {e}"
    return result


def refresh_to_current_season(sport: str):
    """STUB — refresh a sport's data with matches completed since the last
    sync, for live/ongoing use of this tool during the season.

    NOT WIRED in this pass: there is no live fixtures/results API connected
    here. A real implementation would:
      1. Call api-sports.io (APP_SPORTS_KEY, see app/config.py) or
         the-odds-api.com (THE_ODDS_API_KEY) for completed fixtures since
         the last known match date in our local CSV for this sport.
      2. Normalize the response to the same columns used by the historical
         CSVs (varies per sport, see lib/loaders.py).
      3. Append new rows to the local CSV / re-upload to the Storage bucket
         so both this tool and any downstream consumer see the update.
    For now this simply re-syncs from the Storage bucket (i.e. whatever a
    human/ETL has already dropped in there), which is a no-op unless the
    bucket contents change out-of-band.
    """
    return sync_sport(sport, force=True)


if __name__ == "__main__":
    import json
    res = sync_all()
    for sport, paths in res.items():
        if isinstance(paths, str):
            print(sport, paths)
        else:
            print(sport, f"{len(paths)} files ->", [p.name for p in paths])
