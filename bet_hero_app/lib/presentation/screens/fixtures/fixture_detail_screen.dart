import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../../core/theme.dart';
import '../../../data/models/prediction_model.dart';
import '../../providers/fixture_provider.dart';
import '../../widgets/common/sport_icon.dart';
import '../../widgets/ui/ui_kit.dart';
import '../misc/not_found_screen.dart';

/// Ports `pages/FixtureDetail.tsx` — match header card (teams + kickoff),
/// a highlighted "selected for tier" market if this fixture is part of one
/// of today's accumulators, then every market the model evaluated grouped
/// by market type, each row showing model probability / odds / edge.
class FixtureDetailScreen extends ConsumerWidget {
  final String id;
  const FixtureDetailScreen({super.key, required this.id});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final fixtureAsync = ref.watch(fixtureDetailProvider(id));

    return Scaffold(
      backgroundColor: AppColors.base,
      body: fixtureAsync.when(
        data: (fixture) {
          if (fixture == null) return const NotFoundScreen();
          final predictions = [...(fixture.predictions ?? <PredictionModel>[])];
          predictions.sort((a, b) => b.edge.compareTo(a.edge));
          final selected = fixture.predictionId != null && predictions.isNotEmpty ? predictions.first : null;
          final rest = selected == null ? predictions : predictions.where((p) => p != selected).toList();
          final groups = <String, List<PredictionModel>>{};
          for (final p in rest) {
            groups.putIfAbsent(p.market, () => []).add(p);
          }

          return ListView(
            children: [
              ScreenHeader(
                title: '${fixture.homeTeam} vs ${fixture.awayTeam}',
                subtitle: '${fixture.league} · ${DateFormat('HH:mm').format(fixture.matchDate)}',
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    GlassCard(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              SportIcon(sportSlug: fixture.sport, size: 14, color: AppColors.inkFaint),
                              const SizedBox(width: 6),
                              Text(fixture.league, style: const TextStyle(fontSize: 11, color: AppColors.inkFaint)),
                              const SizedBox(width: 6),
                              const Text('·', style: TextStyle(fontSize: 11, color: AppColors.inkFaint)),
                              const SizedBox(width: 6),
                              Text('Kick-off ${DateFormat('HH:mm').format(fixture.matchDate)}',
                                  style: AppTheme.numStyle(fontSize: 11, color: AppColors.inkFaint)),
                            ],
                          ),
                          const SizedBox(height: 16),
                          Row(
                            children: [
                              Expanded(child: _TeamBlock(name: fixture.homeTeam, alignRight: false)),
                              const Text('vs', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.inkFaint)),
                              Expanded(child: _TeamBlock(name: fixture.awayTeam, alignRight: true)),
                            ],
                          ),
                          Container(
                            margin: const EdgeInsets.only(top: 16),
                            padding: const EdgeInsets.only(top: 12),
                            decoration: const BoxDecoration(
                              border: Border(top: BorderSide(color: Colors.white12)),
                            ),
                            child: Text(
                              '${predictions.length} markets evaluated by the model for this fixture.',
                              style: const TextStyle(fontSize: 11, color: AppColors.inkMuted),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (selected != null) ...[
                      const SizedBox(height: 20),
                      GlassCard(
                        padding: const EdgeInsets.all(16),
                        border: Border.all(color: AppColors.tier3.withOpacity(0.33)),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                  decoration: BoxDecoration(
                                    color: AppColors.tier3.withOpacity(0.12),
                                    borderRadius: BorderRadius.circular(999),
                                  ),
                                  child: const Text('Selected for ticket',
                                      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.tier3)),
                                ),
                                GestureDetector(
                                  onTap: () => context.push('/ticket/10'),
                                  child: const Text('Open ticket',
                                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.tier3)),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            _MarketRow(prediction: selected, highlight: true, accent: AppColors.tier3),
                          ],
                        ),
                      ),
                    ],
                    const SizedBox(height: 24),
                    const Text('EVERY MARKET EVALUATED',
                        style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
                    const SizedBox(height: 4),
                    const Padding(
                      padding: EdgeInsets.symmetric(horizontal: 4, vertical: 8),
                      child: Row(
                        children: [
                          Expanded(child: Text('Market', style: TextStyle(fontSize: 10, color: AppColors.inkFaint))),
                          SizedBox(width: 48, child: Text('Model', textAlign: TextAlign.right, style: TextStyle(fontSize: 10, color: AppColors.inkFaint))),
                          SizedBox(width: 48, child: Text('Odds', textAlign: TextAlign.right, style: TextStyle(fontSize: 10, color: AppColors.inkFaint))),
                          SizedBox(width: 48, child: Text('Edge', textAlign: TextAlign.right, style: TextStyle(fontSize: 10, color: AppColors.inkFaint))),
                        ],
                      ),
                    ),
                    if (groups.isEmpty && selected == null)
                      const EmptyState(icon: Icons.query_stats, title: 'No markets yet', body: 'The model has not evaluated any markets for this fixture.'),
                    ...groups.entries.map((e) => Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 4),
                                child: Text(e.key.toUpperCase(),
                                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkFaint)),
                              ),
                              const SizedBox(height: 8),
                              GlassCard(
                                padding: EdgeInsets.zero,
                                child: Column(
                                  children: [
                                    for (var i = 0; i < e.value.length; i++) ...[
                                      if (i > 0) const Divider(height: 1, color: Colors.white12),
                                      _MarketRow(prediction: e.value[i]),
                                    ],
                                  ],
                                ),
                              ),
                            ],
                          ),
                        )),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              const ResponsibleFooter(),
              const SizedBox(height: 24),
            ],
          );
        },
        loading: () => const Padding(
          padding: EdgeInsets.all(20),
          child: Column(children: [SkeletonRow(), SizedBox(height: 12), SkeletonRow(), SizedBox(height: 12), SkeletonRow()]),
        ),
        error: (e, _) => const NotFoundScreen(),
      ),
    );
  }
}

class _TeamBlock extends StatelessWidget {
  final String name;
  final bool alignRight;
  const _TeamBlock({required this.name, required this.alignRight});

  String get _initials {
    final parts = name.trim().split(RegExp(r'\s+')).take(2);
    return parts.map((w) => w.isNotEmpty ? w[0] : '').join().toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final avatar = Container(
      width: 40,
      height: 40,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: Colors.white.withOpacity(0.05),
        border: Border.all(color: Colors.white24),
      ),
      child: Text(_initials, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.inkMuted)),
    );
    final label = Expanded(
      child: Text(
        name,
        textAlign: alignRight ? TextAlign.right : TextAlign.left,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppColors.ink),
      ),
    );
    final children = alignRight ? [label, const SizedBox(width: 10), avatar] : [avatar, const SizedBox(width: 10), label];
    return Row(children: children);
  }
}

class _MarketRow extends StatelessWidget {
  final PredictionModel prediction;
  final bool highlight;
  final Color? accent;
  const _MarketRow({required this.prediction, this.highlight = false, this.accent});

  @override
  Widget build(BuildContext context) {
    final edgeVal = (prediction.modelProbability - prediction.impliedProbability) * 100;
    final edgePositive = edgeVal >= 0;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: highlight ? 12 : 16, vertical: 12),
      decoration: highlight
          ? BoxDecoration(color: Colors.white.withOpacity(0.03), borderRadius: BorderRadius.circular(AppRadius.xl))
          : null,
      child: Row(
        children: [
          Expanded(
            child: Text(
              prediction.predictedOutcome,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 14,
                fontWeight: highlight ? FontWeight.w700 : FontWeight.w500,
                color: highlight ? (accent ?? AppColors.ink) : AppColors.ink,
              ),
            ),
          ),
          SizedBox(
            width: 48,
            child: Text('${(prediction.modelProbability * 100).toStringAsFixed(0)}%',
                textAlign: TextAlign.right, style: AppTheme.numStyle(fontSize: 12, color: AppColors.inkMuted)),
          ),
          SizedBox(width: 48, child: Align(alignment: Alignment.centerRight, child: OddsDisplay(odds: prediction.odds, size: OddsSize.sm))),
          SizedBox(
            width: 48,
            child: Text(
              '${edgePositive ? '+' : ''}${edgeVal.toStringAsFixed(1)}',
              textAlign: TextAlign.right,
              style: AppTheme.numStyle(fontSize: 12, fontWeight: FontWeight.w600, color: edgePositive ? AppColors.win : AppColors.loss),
            ),
          ),
        ],
      ),
    );
  }
}
