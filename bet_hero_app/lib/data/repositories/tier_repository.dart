import '../../services/api_service.dart';

class TierLeague {
  final String leagueKey;
  final String leagueName;

  TierLeague({required this.leagueKey, required this.leagueName});

  factory TierLeague.fromJson(Map<String, dynamic> json) => TierLeague(
        leagueKey: json['league_key']?.toString() ?? '',
        leagueName: json['league_name']?.toString() ?? '',
      );
}

class TierGroup {
  final int tier;
  final List<TierLeague> leagues;

  TierGroup({required this.tier, required this.leagues});

  factory TierGroup.fromJson(Map<String, dynamic> json) => TierGroup(
        tier: (json['tier'] as num).toInt(),
        leagues: (json['leagues'] as List<dynamic>? ?? [])
            .map((l) => TierLeague.fromJson(l as Map<String, dynamic>))
            .toList(),
      );
}

class MarketOption {
  final String market;
  final String? selection; // specific line (e.g. "Over 2.5"), null = whole market
  final String label;

  MarketOption({required this.market, required this.selection, required this.label});

  factory MarketOption.fromJson(Map<String, dynamic> json) => MarketOption(
        market: json['market']?.toString() ?? '',
        selection: json['selection']?.toString(),
        label: json['label']?.toString() ?? '',
      );

  /// Unique key for selection-set bookkeeping (market alone isn't unique
  /// once a market has multiple line options).
  String get id => selection == null ? market : '$market::$selection';
}

class MlModelOption {
  final String id;
  final String label;

  MlModelOption({required this.id, required this.label});

  factory MlModelOption.fromJson(Map<String, dynamic> json) => MlModelOption(
        id: json['id']?.toString() ?? '',
        label: json['label']?.toString() ?? '',
      );
}

class AvailableDay {
  final String date; // "YYYY-MM-DD"
  final int fixtureCount;

  AvailableDay({required this.date, required this.fixtureCount});

  factory AvailableDay.fromJson(Map<String, dynamic> json) => AvailableDay(
        date: json['date']?.toString() ?? '',
        fixtureCount: (json['fixture_count'] as num?)?.toInt() ?? 0,
      );

  String get label => '$date · $fixtureCount fixtures';
}

class TierPredictResult {
  final List<TierPick> picks;
  final String? message;
  const TierPredictResult({required this.picks, this.message});
}

class TierPick {
  final String fixtureId;
  final String homeTeam;
  final String awayTeam;
  final String matchDate;
  final String leagueKey;
  final String leagueName;
  final int tier;
  final String market;
  final String selection;
  final double modelProbability;
  final double? odds;
  final double? edge;
  final double? confidence;
  final String? actualOutcome;
  final String status; // won | lost | pending

  TierPick({
    required this.fixtureId,
    required this.homeTeam,
    required this.awayTeam,
    required this.matchDate,
    required this.leagueKey,
    required this.leagueName,
    required this.tier,
    required this.market,
    required this.selection,
    required this.modelProbability,
    required this.odds,
    required this.edge,
    required this.confidence,
    required this.actualOutcome,
    required this.status,
  });

  factory TierPick.fromJson(Map<String, dynamic> json) => TierPick(
        fixtureId: json['fixture_id']?.toString() ?? '',
        homeTeam: json['home_team']?.toString() ?? 'Unknown',
        awayTeam: json['away_team']?.toString() ?? 'Unknown',
        matchDate: json['match_date']?.toString() ?? '',
        leagueKey: json['league_key']?.toString() ?? '',
        leagueName: json['league_name']?.toString() ?? '',
        tier: (json['tier'] as num?)?.toInt() ?? 5,
        market: json['market']?.toString() ?? '',
        selection: json['selection']?.toString() ?? '',
        modelProbability: (json['model_probability'] as num?)?.toDouble() ?? 0.0,
        odds: (json['odds'] as num?)?.toDouble(),
        edge: (json['edge'] as num?)?.toDouble(),
        confidence: (json['confidence'] as num?)?.toDouble(),
        actualOutcome: json['actual_outcome']?.toString(),
        status: json['status']?.toString() ?? 'pending',
      );
}

class TierRepository {
  final ApiService _api;

  TierRepository(this._api);

  Future<List<TierGroup>> getTierLeagues() async {
    final response = await _api.dio.get('/tiers/leagues');
    final data = response.data as Map<String, dynamic>;
    final tiers = (data['tiers'] as List<dynamic>? ?? []);
    return tiers.map((t) => TierGroup.fromJson(t as Map<String, dynamic>)).toList();
  }

  Future<List<MarketOption>> getMarkets() async {
    final response = await _api.dio.get('/tiers/markets');
    final data = response.data as Map<String, dynamic>;
    final markets = (data['markets'] as List<dynamic>? ?? []);
    return markets.map((m) => MarketOption.fromJson(m as Map<String, dynamic>)).toList();
  }

  Future<List<MlModelOption>> getMlModels() async {
    final response = await _api.dio.get('/tiers/ml-models');
    final data = response.data as Map<String, dynamic>;
    final models = (data['models'] as List<dynamic>? ?? []);
    return models.map((m) => MlModelOption.fromJson(m as Map<String, dynamic>)).toList();
  }

  Future<List<AvailableDay>> getAvailableDays({String sport = 'football'}) async {
    final response = await _api.dio.get('/tiers/days', queryParameters: {'sport': sport});
    final data = response.data as Map<String, dynamic>;
    final days = (data['days'] as List<dynamic>? ?? []);
    return days.map((d) => AvailableDay.fromJson(d as Map<String, dynamic>)).toList();
  }

  Future<TierPredictResult> predictForTiers({
    required String date,
    required List<int> tiers,
    required int matchCount,
    List<MarketOption>? marketOptions,
    String? mlModel,
    String sport = 'football',
  }) async {
    final markets = marketOptions?.map((m) => m.market).toSet().toList();
    final selections = marketOptions
        ?.where((m) => m.selection != null)
        .map((m) => m.selection!)
        .toList();
    final response = await _api.dio.post('/tiers/predict', data: {
      'sport': sport,
      'date': date,
      'tiers': tiers,
      if (markets != null && markets.isNotEmpty) 'markets': markets,
      if (selections != null && selections.isNotEmpty) 'selections': selections,
      if (mlModel != null && mlModel != 'ensemble') 'ml_model': mlModel,
      'match_count': matchCount,
    });
    final data = response.data as Map<String, dynamic>;
    final preds = (data['predictions'] as List<dynamic>? ?? []);
    return TierPredictResult(
      picks: preds.map((p) => TierPick.fromJson(p as Map<String, dynamic>)).toList(),
      message: data['message'] as String?,
    );
  }
}
