import 'package:dio/dio.dart';
import '../../services/api_service.dart';

class LongshotPick {
  final String fixtureId;
  final String homeTeam;
  final String awayTeam;
  final String league;
  final String matchDate;
  final String market;
  final String selection;
  final double modelProbability;
  final double? odds;
  final String? actualOutcome;
  final bool wasCorrect;

  LongshotPick({
    required this.fixtureId,
    required this.homeTeam,
    required this.awayTeam,
    required this.league,
    required this.matchDate,
    required this.market,
    required this.selection,
    required this.modelProbability,
    required this.odds,
    required this.actualOutcome,
    required this.wasCorrect,
  });

  factory LongshotPick.fromJson(Map<String, dynamic> json) => LongshotPick(
        fixtureId: json['fixture_id']?.toString() ?? '',
        homeTeam: json['home_team']?.toString() ?? 'Unknown',
        awayTeam: json['away_team']?.toString() ?? 'Unknown',
        league: json['league']?.toString() ?? '',
        matchDate: json['match_date']?.toString() ?? '',
        market: json['market']?.toString() ?? '',
        selection: json['selection']?.toString() ?? '',
        modelProbability: (json['model_probability'] as num?)?.toDouble() ?? 0.0,
        odds: (json['odds'] as num?)?.toDouble(),
        actualOutcome: json['actual_outcome']?.toString(),
        wasCorrect: json['was_correct'] as bool? ?? false,
      );
}

class LongshotsResult {
  final LongshotPick? bestBet;
  final List<LongshotPick> picks;

  LongshotsResult({required this.bestBet, required this.picks});

  static LongshotsResult empty() => LongshotsResult(bestBet: null, picks: []);
}

class LongshotRepository {
  final ApiService _api;

  LongshotRepository(this._api);

  /// Real longshot picks from completed matches, paired with the actual
  /// outcome — football only, since that's the only sport with trained
  /// models. Other sports return an empty result (not an error) so the UI
  /// can show a "coming soon" state instead of a broken screen.
  Future<LongshotsResult> getLongshots(String sport) async {
    if (sport != 'football' && sport != 'all') {
      return LongshotsResult.empty();
    }
    try {
      final response = await _api.dio.get(
        '/predictions/longshots',
        queryParameters: {'sport': sport},
      );
      final data = response.data as Map<String, dynamic>;
      final bestBetJson = data['best_bet'] as Map<String, dynamic>?;
      final picksJson = (data['data'] as List<dynamic>?) ?? [];
      return LongshotsResult(
        bestBet: bestBetJson != null ? LongshotPick.fromJson(bestBetJson) : null,
        picks: picksJson.map((p) => LongshotPick.fromJson(p as Map<String, dynamic>)).toList(),
      );
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) return LongshotsResult.empty();
      rethrow;
    } catch (e) {
      print('getLongshots error: $e');
      return LongshotsResult.empty();
    }
  }
}
