"""Maps API-Football's numeric league ids to the internal `league_key`
convention that LEAGUE_TIERS (app/ml/league_tiers.py) and the Tier Picks
week calendar (app/routers/tiers.py) already use — either a football-data
.co.uk-style code ("E0") for the core anchor leagues, or the exact league
name string for leagues that only ever existed as named historical CSV
rows (e.g. "MLS"). Without this, live-ingested fixtures carry a bare
numeric league_key (e.g. "39") that never matches any LEAGUE_TIERS key, so
they're silently invisible to Tier Picks regardless of week/date filtering.

IDs verified live against GET /leagues (2026-09-18) — not guessed from
memory — by matching country + league name.
"""

API_FOOTBALL_LEAGUE_KEY_MAP: dict[str, str] = {
    # Anchor leagues (used for the season-week calendar)
    "39": "E0", "40": "E1", "41": "E2", "42": "E3", "43": "EC",
    "179": "SC0", "180": "SC1", "183": "SC2", "184": "SC3",
    "140": "SP1", "141": "SP2",
    "78": "D1", "79": "D2",
    "135": "I1", "136": "I2",
    "61": "F1", "62": "F2",
    "88": "N1",
    "144": "B1",
    "94": "P1",
    "203": "T1",
    "197": "G1",
    # Name-keyed leagues (LEAGUE_TIERS matches these by exact league name,
    # not a code, since they never had a football-data.co.uk CSV mapping)
    "218": "Bundesliga",       # Austria
    "235": "Premier League",   # Russia
    "207": "Super League",     # Switzerland
    "71": "Serie A",           # Brazil
    "128": "Liga Profesional", # Argentina
    "253": "MLS",              # USA
    "262": "Liga MX",          # Mexico
    "98": "J1 League",         # Japan
    "106": "Ekstraklasa",      # Poland
    "103": "Eliteserien",      # Norway
    "113": "Allsvenskan",      # Sweden
    "119": "Superliga",        # Denmark
    "244": "Veikkausliiga",    # Finland
    "208": "Challenge League", # Switzerland 2nd tier
    "357": "Premier Division", # Ireland
}


def map_league_key(api_football_league_id: str) -> str:
    """Translates a raw API-Football league id to our internal league_key
    convention. Leagues outside our tracked tier set pass through
    unchanged — they simply won't match any LEAGUE_TIERS entry (default
    tier 5), which is correct: we only classify leagues we've tiered."""
    return API_FOOTBALL_LEAGUE_KEY_MAP.get(api_football_league_id, api_football_league_id)


# Our internal league_key -> The Odds API's sport_key, for GET
# /v4/sports/{sport_key}/scores — one call per league returns dozens of
# recent results at once (vs API-Football's one call per fixture), so this
# is the far more quota-efficient primary result source for any league it
# covers. Verified live against GET /v4/sports (2026-09-18). Leagues with
# no match here (EC, SC1/SC2/SC3, Russia, Challenge League) simply aren't
# covered by The Odds API's free tier and fall through to API-Football.
ODDS_API_LEAGUE_MAP: dict[str, str] = {
    "E0": "soccer_epl",
    "E1": "soccer_efl_champ",
    "E2": "soccer_england_league1",
    "E3": "soccer_england_league2",
    "SC0": "soccer_spl",
    "D1": "soccer_germany_bundesliga",
    "D2": "soccer_germany_bundesliga2",
    "SP1": "soccer_spain_la_liga",
    "SP2": "soccer_spain_segunda_division",
    "I1": "soccer_italy_serie_a",
    "I2": "soccer_italy_serie_b",
    "F1": "soccer_france_ligue_one",
    "F2": "soccer_france_ligue_two",
    "N1": "soccer_netherlands_eredivisie",
    "B1": "soccer_belgium_first_div",
    "P1": "soccer_portugal_primeira_liga",
    "T1": "soccer_turkey_super_league",
    "G1": "soccer_greece_super_league",
    "Bundesliga": "soccer_austria_bundesliga",       # Austria
    "Super League": "soccer_switzerland_superleague", # Switzerland
    "Serie A": "soccer_brazil_campeonato",            # Brazil
    "Liga Profesional": "soccer_argentina_primera_division",
    "MLS": "soccer_usa_mls",
    "Liga MX": "soccer_mexico_ligamx",
    "J1 League": "soccer_japan_j_league",
    "Ekstraklasa": "soccer_poland_ekstraklasa",
    "Eliteserien": "soccer_norway_eliteserien",
    "Allsvenskan": "soccer_sweden_allsvenskan",
    "Superliga": "soccer_denmark_superliga",
    "Veikkausliiga": "soccer_finland_veikkausliiga",
    "Premier Division": "soccer_league_of_ireland",
}
