class StatRow {
  final String label;
  final num? home;
  final num? away;

  const StatRow({required this.label, this.home, this.away});

  factory StatRow.fromJson(Map<String, dynamic> json) => StatRow(
        label: json['label']?.toString() ?? '',
        home: json['home'] as num?,
        away: json['away'] as num?,
      );
}

/// Match header + stat-comparison rows for the fixture detail "Stats" view.
/// `statsAvailable` is false whenever the fixture has no matching API-Sports
/// record to pull live statistics from (e.g. a football-data.co.uk-backfilled
/// fixture) — shown as an honest "not available" state, not an error.
class MatchStatsModel {
  final String fixtureId;
  final String? homeTeam;
  final String? awayTeam;
  final String? homeTeamLogo;
  final String? awayTeamLogo;
  final String? status;
  final int? homeGoals;
  final int? awayGoals;
  final bool statsAvailable;
  final List<StatRow> stats;

  const MatchStatsModel({
    required this.fixtureId,
    this.homeTeam,
    this.awayTeam,
    this.homeTeamLogo,
    this.awayTeamLogo,
    this.status,
    this.homeGoals,
    this.awayGoals,
    required this.statsAvailable,
    required this.stats,
  });

  factory MatchStatsModel.fromJson(Map<String, dynamic> json) => MatchStatsModel(
        fixtureId: json['fixture_id']?.toString() ?? '',
        homeTeam: json['home_team']?.toString(),
        awayTeam: json['away_team']?.toString(),
        homeTeamLogo: json['home_team_logo']?.toString(),
        awayTeamLogo: json['away_team_logo']?.toString(),
        status: json['status']?.toString(),
        homeGoals: (json['home_goals'] as num?)?.toInt(),
        awayGoals: (json['away_goals'] as num?)?.toInt(),
        statsAvailable: json['stats_available'] == true,
        stats: (json['stats'] as List<dynamic>? ?? [])
            .map((s) => StatRow.fromJson(s as Map<String, dynamic>))
            .toList(),
      );
}
