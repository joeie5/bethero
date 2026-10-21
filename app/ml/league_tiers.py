"""League tier classification, used by the Tier Picks feature to let a user
pick which quality-tier of leagues (Tier 1 = top-flight elite, down to
Tier 5 = non-league/smallest sample) the model should draw its selections
from for a given season week.

Tiers reflect competitive level and data reliability, not just country size.
Two source labels ("Super League", "Superliga") are shared by two distinct
countries' competitions in the raw historical data and can't be split by
league_key alone — flagged rather than guessed.
"""
from __future__ import annotations

LEAGUE_TIERS: dict[str, int] = {
    # Tier 1 — top-flight elite leagues
    "E0": 1, "SP1": 1, "D1": 1, "I1": 1, "F1": 1, "N1": 1, "P1": 1,
    "B1": 1, "T1": 1, "G1": 1,
    "Bundesliga": 1,        # Austria
    "Premier League": 1,    # Russia
    "Super League": 1,      # Switzerland / China (ambiguous label, see module note)
    "Serie A": 1,           # Brazil
    "Liga Profesional": 1,  # Argentina
    "MLS": 1,               # USA
    "Liga MX": 1,           # Mexico
    "J1 League": 1,         # Japan
    "Ekstraklasa": 1,       # Poland
    "Eliteserien": 1,       # Norway
    "Allsvenskan": 1,       # Sweden
    "Superliga": 1,         # Denmark / Romania (ambiguous label, see module note)
    "Veikkausliiga": 1,     # Finland (also playable as tier 2 — small sample top flight)

    # Tier 2 — second-tier / strong domestic
    "E1": 2, "SP2": 2, "D2": 2, "I2": 2, "F2": 2, "SC0": 2,
    "Challenge League": 2,             # Switzerland 2nd tier
    "Copa De La Liga Profesional": 2,  # Argentina secondary competition
    "Premier Division": 2,             # Ireland

    # Tier 3 — lower domestic divisions
    "E2": 3, "SC1": 3,

    # Tier 4 — minor/regional
    "E3": 4, "SC2": 4,

    # Tier 5 — non-league / smallest sample
    "EC": 5, "SC3": 5,
}

LEAGUE_NAMES: dict[str, str] = {
    "E0": "England - Premier League", "E1": "England - Championship",
    "E2": "England - League One", "E3": "England - League Two",
    "EC": "England - National League",
    "SC0": "Scotland - Premiership", "SC1": "Scotland - Championship",
    "SC2": "Scotland - League One", "SC3": "Scotland - League Two",
    "SP1": "Spain - La Liga", "SP2": "Spain - La Liga 2",
    "D1": "Germany - Bundesliga", "D2": "Germany - 2. Bundesliga",
    "I1": "Italy - Serie A", "I2": "Italy - Serie B",
    "F1": "France - Ligue 1", "F2": "France - Ligue 2",
    "N1": "Netherlands - Eredivisie",
    "B1": "Belgium - Pro League",
    "P1": "Portugal - Primeira Liga",
    "T1": "Turkey - Super Lig",
    "G1": "Greece - Super League",
    "Bundesliga": "Austria - Bundesliga",
    "Premier League": "Russia - Premier League",
    "Super League": "Switzerland/China - Super League",
    "Serie A": "Brazil - Serie A",
    "Liga Profesional": "Argentina - Liga Profesional",
    "Copa De La Liga Profesional": "Argentina - Copa de la Liga",
    "MLS": "USA - MLS",
    "Liga MX": "Mexico - Liga MX",
    "J1 League": "Japan - J1 League",
    "Ekstraklasa": "Poland - Ekstraklasa",
    "Eliteserien": "Norway - Eliteserien",
    "Allsvenskan": "Sweden - Allsvenskan",
    "Superliga": "Denmark/Romania - Superliga",
    "Veikkausliiga": "Finland - Veikkausliiga",
    "Challenge League": "Switzerland - Challenge League",
    "Premier Division": "Ireland - Premier Division",
}


# The 22 "Main tier" league_keys (CLAUDE.md §5) sourced from football-data
# .co.uk's per-season-per-division files, which include real corner-kick
# (HC/AC) and card (HY/AY/HR/AR) columns. The 16 "Extra tier" leagues' single
# combined-file source has NEITHER — confirmed live (2026-10-21) by
# inspecting its actual CSV schema (Country,League,Season,Date,Time,Home,
# Away,HG,AG,Res + odds only). The Corners model trained almost entirely on
# Main-tier data as a result, and produces degenerate, uncalibrated
# probabilities on Extra-tier fixtures (confirmed live same day: ~18-21%
# predicted vs ~70%+ everywhere else, on a handful of samples) — not a
# legitimate prediction, just the model extrapolating outside what it was
# ever trained on. Used to suppress Corners (and, by the same reasoning,
# would apply to Cards) predictions for the 16 Extra-tier leagues until a
# tier-stratified retrain gives them real signal.
MAIN_TIER_LEAGUE_KEYS: frozenset[str] = frozenset({
    "E0", "E1", "E2", "E3", "EC",
    "SC0", "SC1", "SC2", "SC3",
    "D1", "D2", "SP1", "SP2", "I1", "I2", "F1", "F2",
    "N1", "B1", "P1", "T1", "G1",
})


def tier_of(league_key: str) -> int:
    return LEAGUE_TIERS.get(league_key, 5)


def leagues_in_tier(tier: int) -> list[str]:
    return [k for k, v in LEAGUE_TIERS.items() if v == tier]


def tiers_summary() -> list[dict]:
    out = []
    for tier in range(1, 6):
        keys = leagues_in_tier(tier)
        out.append({
            "tier": tier,
            "leagues": [
                {"league_key": k, "league_name": LEAGUE_NAMES.get(k, k)}
                for k in keys
            ],
        })
    return out
