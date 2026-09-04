"""
fixture_fetcher.py — Pulls upcoming/live football fixtures + odds from
API-Sports and writes them into the LIVE schema (fixtures / fixture_odds /
match_results), keyed by (sport, fixture_id) — not the abandoned `matches`
table this file used to target (confirmed gone from the live DB: PostgREST
returns PGRST205 "Perhaps you meant... match_results").

Only football is wired to the real schema here — basketball/NFL/hockey/
baseball have no trained model_keys yet (CLAUDE.md §6 sequencing: only
sports that clear Section 4's gate get wired into live ingestion), so their
fetch paths are left as explicit no-ops rather than silently writing to a
schema no one has designed yet.
"""
import os
import httpx
import asyncio
from datetime import datetime, timedelta, timezone
from app.database import get_supabase_admin

API_KEY = os.getenv("API_SPORTS_KEY", "")

HEADERS = {
    "x-apisports-key": API_KEY
}

# API-Sports fixture.status.short → our fixtures.status convention
# (NS = Not Started, matches predictor.py's predict_upcoming() filter)
_STATUS_MAP = {
    "NS": "NS", "TBD": "NS",
    "1H": "LIVE", "HT": "LIVE", "2H": "LIVE", "ET": "LIVE", "P": "LIVE", "LIVE": "LIVE",
    "FT": "FT", "AET": "FT", "PEN": "FT",
    "PST": "PST", "CANC": "CANC", "ABD": "ABD", "AWD": "FT", "WO": "FT",
}
_FINISHED_STATUSES = {"FT"}

TOP_LEAGUE_IDS = [
    2, 3, 848, 39, 140, 78, 135, 61, 94, 88, 203, 144, 253, 292, 307, 188,
]


def map_football_fixture(f: dict) -> dict:
    """Maps one API-Sports fixture object → our `fixtures` row shape."""
    fixture = f.get("fixture", {})
    teams   = f.get("teams", {})
    league  = f.get("league", {})

    status_short = fixture.get("status", {}).get("short", "NS")
    status = _STATUS_MAP.get(status_short, "NS")

    return {
        "sport":           "football",
        "fixture_id":      str(fixture.get("id")),
        "provider":        "api-sports",
        "league_key":      str(league.get("id", "")),
        "league_name":     league.get("name", "Unknown"),
        "season":          str(league.get("season", "")),
        "round":           league.get("round", ""),
        "match_date":      fixture.get("date", ""),
        "kickoff_time":    fixture.get("date", ""),
        "venue":           (fixture.get("venue") or {}).get("name", ""),
        "referee":         fixture.get("referee") or None,
        "status":          status,
        "home_team":       (teams.get("home") or {}).get("name", ""),
        "away_team":       (teams.get("away") or {}).get("name", ""),
        "home_team_id":    str((teams.get("home") or {}).get("id", "")),
        "away_team_id":    str((teams.get("away") or {}).get("id", "")),
        "home_team_logo":  (teams.get("home") or {}).get("logo", ""),
        "away_team_logo":  (teams.get("away") or {}).get("logo", ""),
    }


def _map_match_result(f: dict, fixture_id: str) -> dict | None:
    """If the fixture is finished, build a `match_results` row. None otherwise."""
    fixture = f.get("fixture", {})
    status_short = fixture.get("status", {}).get("short", "NS")
    if status_short not in _FINISHED_STATUSES:
        return None

    goals = f.get("goals", {})
    hg, ag = goals.get("home"), goals.get("away")
    if hg is None or ag is None:
        return None

    teams = f.get("teams", {})
    ftr = "H" if hg > ag else ("A" if hg < ag else "D")
    return {
        "sport":       "football",
        "fixture_id":  fixture_id,
        "home_team":   (teams.get("home") or {}).get("name", ""),
        "away_team":   (teams.get("away") or {}).get("name", ""),
        "status":      "finished",
        "home_goals":  hg,
        "away_goals":  ag,
        # total_goals / goal_diff are DB-generated columns — confirmed live
        # ("cannot insert a non-DEFAULT value into column 'total_goals'")
        "ftr":         ftr,
        "btts":        bool(hg > 0 and ag > 0),
        "over15":      bool((hg + ag) > 1.5),
        "over25":      bool((hg + ag) > 2.5),
        "settled_at":  datetime.now(timezone.utc).isoformat(),
    }


def _map_odds(f: dict, fixture_id: str) -> dict | None:
    """Best-effort 1x2 odds row from whatever API-Sports embeds on the fixture."""
    home_odds = draw_odds = away_odds = None
    for odd in f.get("odds", []) or []:
        for value in odd.get("values", []):
            v = value.get("value")
            if v == "Home":
                home_odds = float(value.get("odd", 0)) or None
            elif v == "Away":
                away_odds = float(value.get("odd", 0)) or None
            elif v == "Draw":
                draw_odds = float(value.get("odd", 0)) or None
    if home_odds is None and away_odds is None and draw_odds is None:
        return None
    return {
        "sport":      "football",
        "fixture_id": fixture_id,
        "bookmaker":  "api-sports",
        # markets_catalog registers this as "1X2" (uppercase) — fixture_odds.market
        # FK-validates against it; confirmed live that lowercase "1x2" is rejected.
        "market":     "1X2",
        "home_odds":  home_odds,
        "draw_odds":  draw_odds,
        "away_odds":  away_odds,
        "pulled_at":  datetime.now(timezone.utc).isoformat(),
    }


async def fetch_football_with_odds() -> int:
    """Pulls the next few days of football fixtures and writes fixtures /
    fixture_odds / (if already finished) match_results, all keyed by the
    real (sport, fixture_id) schema."""
    supabase = get_supabase_admin()
    inserted = 0
    today = datetime.now()

    for days_ahead in range(0, 3):
        target_date = today + timedelta(days=days_ahead)
        date_str = target_date.strftime("%Y-%m-%d")
        print(f"Fetching fixtures for {date_str}...")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    "https://v3.football.api-sports.io/fixtures",
                    headers={"x-apisports-key": API_KEY},
                    params={"date": date_str},
                )
                if resp.status_code != 200:
                    print(f"API error {resp.status_code}")
                    continue

                data = resp.json()
                if data.get("errors"):
                    print(f"API errors: {data['errors']}")
                    continue

                all_fixtures = data.get("response", [])
                top    = [f for f in all_fixtures if f.get("league", {}).get("id") in TOP_LEAGUE_IDS]
                others = [f for f in all_fixtures if f.get("league", {}).get("id") not in TOP_LEAGUE_IDS]
                fixtures_to_save = top + others[:200]
                print(f"{date_str}: {len(top)} top league + {len(others)} other fixtures")

                for f in fixtures_to_save:
                    try:
                        row = map_football_fixture(f)
                        if not row["home_team"] or not row["fixture_id"] or row["fixture_id"] == "None":
                            continue

                        supabase.table("fixtures").upsert(
                            row, on_conflict="sport,fixture_id"
                        ).execute()
                        inserted += 1

                        odds_row = _map_odds(f, row["fixture_id"])
                        if odds_row:
                            # fixture_odds has no unique constraint on
                            # (sport,fixture_id,bookmaker,market) — confirmed
                            # live (42P10: no matching constraint). It's
                            # append-only by design: predictor.py's
                            # OddsLookup already sorts by pulled_at and takes
                            # the latest row, so plain insert is correct here.
                            supabase.table("fixture_odds").insert(odds_row).execute()

                        result_row = _map_match_result(f, row["fixture_id"])
                        if result_row:
                            supabase.table("match_results").upsert(
                                result_row, on_conflict="sport,fixture_id"
                            ).execute()

                    except Exception as e:
                        print(f"Fixture upsert error: {e}")
                        continue

                await asyncio.sleep(2)

        except Exception as e:
            print(f"Fetch error {date_str}: {e}")
            continue

    print(f"Total football fixtures upserted: {inserted}")
    return inserted


async def fetch_all_fixtures() -> int:
    """Football only — see module docstring for why other sports are no-ops."""
    print("Fetching fixtures from API-Sports...")
    count = await fetch_football_with_odds()
    print(f"Football: {count}")
    print(f"Total fixtures: {count}")
    return count


async def create_upcoming_fixtures_from_history():
    """Only used as last resort fallback"""
    print("WARNING: Using history-based fixture fallback")
    return 0
