/// Literal mock data ported from bethero-src/data/*.ts for screens that do not
/// yet have a backend endpoint (Sports hub, Longshots, Notifications list, Profile
/// stats). Replace with real repository calls once the API exists.
class MockSport {
  final String id;
  final String name;
  final int fixtureCount;
  const MockSport(this.id, this.name, this.fixtureCount);
}

const List<MockSport> kMockSports = [
  MockSport('football', 'Football', 42),
  MockSport('basketball', 'Basketball', 11),
  MockSport('nfl', 'NFL', 6),
  MockSport('mlb', 'MLB', 9),
  MockSport('nhl', 'NHL', 7),
  MockSport('tennis', 'Tennis', 24),
  MockSport('cricket', 'Cricket', 4),
];

class MockLongshot {
  final String id;
  final String fixtureId;
  final String sport;
  final String league;
  final String home;
  final String away;
  final String kickoff;
  final String market;
  final String outcome;
  final double odds;
  final double probability;
  final bool isBestBet;
  final String? rationale;

  const MockLongshot({
    required this.id,
    required this.fixtureId,
    required this.sport,
    required this.league,
    required this.home,
    required this.away,
    required this.kickoff,
    required this.market,
    required this.outcome,
    required this.odds,
    required this.probability,
    this.isBestBet = false,
    this.rationale,
  });
}

const List<MockLongshot> kMockLongshots = [
  MockLongshot(
    id: 'ls-1',
    fixtureId: 'bay-lev',
    sport: 'football',
    league: 'Bundesliga',
    home: 'Bayern Munich',
    away: 'Bayer Leverkusen',
    kickoff: '17:30',
    market: 'Correct Score',
    outcome: '3–2 Bayern Munich',
    odds: 19.5,
    probability: 0.072,
    isBestBet: true,
    rationale:
        'The model gives this 7.2% against a 5.1% implied price — the widest relative edge of any longshot on the card. Both sides average over 1.6 goals per game against top-six opposition and eight of the last nine meetings produced four or more goals.',
  ),
  MockLongshot(
    id: 'ls-2',
    fixtureId: 'ars-bha',
    sport: 'football',
    league: 'Premier League',
    home: 'Arsenal',
    away: 'Brighton',
    kickoff: '15:00',
    market: 'Over/Under',
    outcome: 'Over 5.5 Goals',
    odds: 12.0,
    probability: 0.089,
  ),
  MockLongshot(
    id: 'ls-3',
    fixtureId: 'den-okc',
    sport: 'basketball',
    league: 'NBA',
    home: 'Denver Nuggets',
    away: 'Oklahoma City Thunder',
    kickoff: '02:00',
    market: 'Spread',
    outcome: 'Nuggets +14.5 & Over 240',
    odds: 11.5,
    probability: 0.081,
  ),
  MockLongshot(
    id: 'ls-4',
    fixtureId: 'alc-rune',
    sport: 'tennis',
    league: 'ATP Masters — Paris',
    home: 'Carlos Alcaraz',
    away: 'Holger Rune',
    kickoff: '14:00',
    market: 'Set Betting',
    outcome: 'Rune 2–0',
    odds: 9.5,
    probability: 0.098,
  ),
  MockLongshot(
    id: 'ls-5',
    fixtureId: 'rma-gir',
    sport: 'football',
    league: 'LaLiga',
    home: 'Real Madrid',
    away: 'Girona',
    kickoff: '20:00',
    market: '1X2',
    outcome: 'Girona to win',
    odds: 7.5,
    probability: 0.07,
  ),
  MockLongshot(
    id: 'ls-6',
    fixtureId: 'col-veg',
    sport: 'nhl',
    league: 'NHL',
    home: 'Colorado Avalanche',
    away: 'Vegas Golden Knights',
    kickoff: '02:00',
    market: 'Correct Score',
    outcome: '5–4 Vegas Golden Knights',
    odds: 7.0,
    probability: 0.11,
  ),
  MockLongshot(
    id: 'ls-7',
    fixtureId: 'nyy-hou',
    sport: 'mlb',
    league: 'MLB',
    home: 'New York Yankees',
    away: 'Houston Astros',
    kickoff: '00:05',
    market: 'Over/Under',
    outcome: 'Over 12.5 Runs',
    odds: 6.5,
    probability: 0.13,
  ),
  MockLongshot(
    id: 'ls-8',
    fixtureId: 'kc-buf',
    sport: 'nfl',
    league: 'NFL — Week 12',
    home: 'Kansas City Chiefs',
    away: 'Buffalo Bills',
    kickoff: '21:25',
    market: 'Spread',
    outcome: 'Bills −10.5',
    odds: 6.2,
    probability: 0.14,
  ),
  MockLongshot(
    id: 'ls-9',
    fixtureId: 'ind-aus',
    sport: 'cricket',
    league: 'ODI Series',
    home: 'India',
    away: 'Australia',
    kickoff: '09:00',
    market: 'Margin',
    outcome: 'Australia by 100+ runs',
    odds: 5.8,
    probability: 0.15,
  ),
  MockLongshot(
    id: 'ls-10',
    fixtureId: 'int-laz',
    sport: 'football',
    league: 'Serie A',
    home: 'Inter Milan',
    away: 'Lazio',
    kickoff: '19:45',
    market: '1X2',
    outcome: 'Lazio to win',
    odds: 5.0,
    probability: 0.18,
  ),
];

final MockLongshot kMockBestBet = kMockLongshots.firstWhere((l) => l.isBestBet);

// MOCK: ported from bethero-src/data/performance.ts. The backend's
// PerformanceModel does not yet break results down by week / sport / market,
// so pages/Performance.tsx's weekly trend and by-sport/by-market bar charts
// are seeded with the same literal mock rows used in the design kit.
class WeeklyHitRate {
  final String week;
  final double hitRate;
  const WeeklyHitRate(this.week, this.hitRate);
}

const List<WeeklyHitRate> kMockWeeklyTrend = [
  WeeklyHitRate('Wk 1', 0.62),
  WeeklyHitRate('Wk 2', 0.58),
  WeeklyHitRate('Wk 3', 0.71),
  WeeklyHitRate('Wk 4', 0.44),
  WeeklyHitRate('Wk 5', 0.55),
  WeeklyHitRate('Wk 6', 0.67),
  WeeklyHitRate('Wk 7', 0.49),
  WeeklyHitRate('Wk 8', 0.73),
];

class BreakdownRow {
  final String label;
  final double hitRate;
  final int legs;
  const BreakdownRow(this.label, this.hitRate, this.legs);
}

const List<BreakdownRow> kMockSportPerformance = [
  BreakdownRow('Football', 0.61, 214),
  BreakdownRow('Basketball', 0.57, 88),
  BreakdownRow('Tennis', 0.64, 52),
  BreakdownRow('NFL', 0.49, 31),
  BreakdownRow('NHL', 0.55, 27),
  BreakdownRow('MLB', 0.52, 24),
];

const List<BreakdownRow> kMockMarketPerformance = [
  BreakdownRow('Match Result', 0.59, 176),
  BreakdownRow('Over/Under', 0.63, 141),
  BreakdownRow('BTTS', 0.58, 97),
  BreakdownRow('Handicap', 0.51, 62),
  BreakdownRow('Correct Score', 0.31, 22),
];

class MockNotification {
  final String id;
  final String kind;
  final String title;
  final String body;
  final String time;
  final String day;
  final bool unread;
  final String? href;

  const MockNotification({
    required this.id,
    required this.kind,
    required this.title,
    required this.body,
    required this.time,
    required this.day,
    required this.unread,
    this.href,
  });
}

const List<MockNotification> kMockNotifications = [
  MockNotification(
    id: 'n-1',
    kind: 'ticket-ready',
    title: "Today's 10-odds ticket is ready",
    body: '4 legs · 10.17 combined · 14% modelled chance',
    time: '07:12',
    day: 'Today',
    unread: true,
    href: '/ticket/10',
  ),
  MockNotification(
    id: 'n-2',
    kind: 'longshot',
    title: 'Longshot Best Bet of the day',
    body: 'Bayern Munich 3–2 Leverkusen at 19.50 — 7.2% modelled',
    time: '07:10',
    day: 'Today',
    unread: true,
    href: '/longshots',
  ),
  MockNotification(
    id: 'n-3',
    kind: 'ticket-ready',
    title: "Today's 3-odds ticket is ready",
    body: '3 legs · 2.93 combined · 45% modelled chance',
    time: '07:05',
    day: 'Today',
    unread: true,
    href: '/ticket/3',
  ),
  MockNotification(
    id: 'n-4',
    kind: 'odds-movement',
    title: 'Odds movement — Arsenal vs Brighton',
    body: 'Over 2.5 Goals drifted from 1.58 to 1.62. Edge widened to 9.3 points.',
    time: '06:41',
    day: 'Today',
    unread: false,
    href: '/fixture/ars-bha',
  ),
  MockNotification(
    id: 'n-5',
    kind: 'settled-won',
    title: '3-odds ticket settled — Won',
    body: '3 of 3 legs landed at 3.14 combined',
    time: '22:58',
    day: 'Yesterday',
    unread: false,
    href: '/results/r-2026-08-15-3',
  ),
  MockNotification(
    id: 'n-6',
    kind: 'settled-lost',
    title: '5-odds ticket settled — Lost',
    body: '2 of 3 legs landed. Mavericks −3.5 missed.',
    time: '22:44',
    day: 'Yesterday',
    unread: false,
    href: '/results/r-2026-08-15-5',
  ),
  MockNotification(
    id: 'n-7',
    kind: 'settled-lost',
    title: '10-odds ticket settled — Lost',
    body: '2 of 4 legs landed at 10.40 combined',
    time: '21:30',
    day: 'Yesterday',
    unread: false,
    href: '/results/r-2026-08-15-10',
  ),
  MockNotification(
    id: 'n-8',
    kind: 'settled-won',
    title: '10-odds ticket settled — Won',
    body: '4 of 4 legs landed at 9.86 combined',
    time: '23:15',
    day: '13 Aug',
    unread: false,
    href: '/results/r-2026-08-13-10',
  ),
];
