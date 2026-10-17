"""
fetch_current_season.py — Downloads the current-season (2026/27) Main-tier
CSVs from football-data.co.uk and saves them alongside the existing
historical files (football-data.co.uk publishes one file per season, so
last season's file never gets these new rows — a fresh file is needed).

Usage:
    python3 scripts/fetch_current_season.py
"""
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "backtest_web" / "data" / "football"
SEASON_CODE = "2627"  # football-data.co.uk's folder naming: 26/27 season

# code -> country folder
LEAGUES = {
    "E0": "england", "E1": "england", "E2": "england", "E3": "england", "EC": "england",
    "SC0": "scotland", "SC1": "scotland", "SC2": "scotland", "SC3": "scotland",
    "D1": "germany", "D2": "germany",
    "SP1": "spain", "SP2": "spain",
    "I1": "italy", "I2": "italy",
    "F1": "france", "F2": "france",
    "N1": "netherlands",
    "B1": "belgium",
    "P1": "portugal",
    "T1": "turkey",
    "G1": "greece",
}


def main() -> None:
    ok, failed = 0, 0
    for code, country in LEAGUES.items():
        url = f"https://football-data.co.uk/mmz4281/{SEASON_CODE}/{code}.csv"
        dest = DATA_ROOT / country / f"{code}_{SEASON_CODE}.csv"
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            if len(resp.content) < 200:
                print(f"  {code}: suspiciously small response ({len(resp.content)} bytes), skipping")
                failed += 1
                continue
            dest.write_bytes(resp.content)
            n_rows = resp.text.count("\n") - 1
            print(f"  {code} -> {dest.relative_to(REPO_ROOT)} ({n_rows} rows)")
            ok += 1
        except Exception as exc:
            print(f"  {code}: FAILED ({exc})")
            failed += 1
        time.sleep(0.5)  # be polite to the source
    print(f"\n{ok} downloaded, {failed} failed")


if __name__ == "__main__":
    main()
