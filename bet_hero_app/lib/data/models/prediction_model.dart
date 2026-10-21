class PredictionModel {
  final int id;
  final int matchId;
  final String market;
  final String predictedOutcome;
  final double modelProbability;
  final double impliedProbability;
  final double edge;
  final double odds;
  final double confidenceScore;
  final String status;
  final String? actualOutcome;
  final String? result; // Alias for actualOutcome/status in UI
  final String? aiReasoning;
  final DateTime matchDate;
  final DateTime createdAt;

  PredictionModel({
    required this.id,
    required this.matchId,
    required this.market,
    required this.predictedOutcome,
    required this.modelProbability,
    required this.impliedProbability,
    required this.edge,
    required this.odds,
    required this.confidenceScore,
    required this.status,
    this.actualOutcome,
    this.result,
    this.aiReasoning,
    required this.matchDate,
    required this.createdAt,
  });

  factory PredictionModel.fromJson(Map<String, dynamic> json) {
    return PredictionModel(
      id: json['id'] ?? 0,
      // predictions.match_id doesn't exist either (the table uses
      // fixture_id, a string, not an int match_id) — same unconditional
      // null->non-nullable-int crash as created_at above. Unused anywhere
      // in the UI (only the separate AccumulatorLegModel.matchId is), so a
      // 0 fallback has no functional effect.
      matchId: json['match_id'] ?? 0,
      market: json['market'] ?? '',
      predictedOutcome: json['predicted_outcome'] ?? '',
      modelProbability: (json['model_probability'] as num? ?? 0.0).toDouble(),
      impliedProbability: (json['implied_probability'] as num? ?? 0.0).toDouble(),
      edge: (json['edge'] as num? ?? 0.0).toDouble(),
      odds: (json['odds'] as num? ?? 0.0).toDouble(),
      confidenceScore: (json['confidence_score'] as num? ?? 0.0).toDouble(),
      status: json['status'] ?? 'pending',
      actualOutcome: json['actual_outcome'],
      result: json['result'] ?? json['actual_outcome'],
      aiReasoning: json['ai_reasoning'],
      matchDate: json['match_date'] != null
          ? DateTime.parse(json['match_date'])
          : DateTime.now(), // Fallback to now if missing
      // predictions.created_at doesn't exist (the table only has
      // generated_at) — DateTime.parse(null) threw unconditionally for
      // every prediction, which silently failed the whole fixture parse
      // and sent every match detail tap to the "Not available" screen.
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'])
          : (json['generated_at'] != null ? DateTime.parse(json['generated_at']) : DateTime.now()),
    );
  }
}
