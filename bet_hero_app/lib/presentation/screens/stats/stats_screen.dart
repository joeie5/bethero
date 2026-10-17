import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import '../../../data/mock/bethero_mock_data.dart';
import '../../../data/models/performance_model.dart';
import '../../providers/results_provider.dart';
import '../../widgets/ui/ui_kit.dart';

const Map<String, ({String label, Color accent})> _tierMetaShort = {
  '3odds': (label: '3-Odds', accent: AppColors.tier3),
  '5odds': (label: '5-Odds', accent: AppColors.tier5),
  '10odds': (label: '10-Odds', accent: AppColors.tier10),
};

/// Ports `pages/Performance.tsx` — overall hit-rate hero, by-tier grid,
/// weekly trend bar chart, by-sport / by-market breakdown bars, and a
/// tickets-tracked / win-streak stat row.
///
/// Overall hit rate and by-tier settlement come from the real
/// `performanceStatsProvider` (Supabase-backed). The weekly trend and
/// by-sport / by-market breakdowns use `kMockWeeklyTrend` /
/// `kMockSportPerformance` / `kMockMarketPerformance` — the backend does not
/// yet expose that granularity (see the MOCK comment in bethero_mock_data.dart).
class StatsScreen extends ConsumerWidget {
  const StatsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(performanceStatsProvider);

    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: const ScreenHeader(title: 'Model performance', subtitle: 'Since launch'),
      body: async.when(
        data: (stats) => _buildBody(stats),
        loading: () => const Center(child: CircularProgressIndicator(color: AppColors.tier3)),
        error: (e, _) => _buildBody(PerformanceModel.empty()),
      ),
    );
  }

  Widget _buildBody(PerformanceModel stats) {
    final maxWeek = kMockWeeklyTrend.map((w) => w.hitRate).reduce((a, b) => a > b ? a : b);

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
      children: [
        GlassCard(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('OVERALL HIT RATE',
                  style: TextStyle(fontSize: 11, letterSpacing: 0.6, color: AppColors.inkFaint)),
              const SizedBox(height: 4),
              Text('${stats.winRate.toStringAsFixed(1)}%',
                  style: const TextStyle(fontSize: 52, fontWeight: FontWeight.w800, height: 1, color: AppColors.ink)),
              const SizedBox(height: 10),
              Text('${stats.totalPredictions} tickets settled · model calibration tracked live',
                  style: AppTheme.numStyle(fontSize: 12, color: AppColors.inkMuted)),
              Container(
                margin: const EdgeInsets.only(top: 12),
                padding: const EdgeInsets.only(top: 12),
                decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.white.withOpacity(0.06)))),
                child: const Text(
                  'The model has run slightly hot on its own forecasts this quarter — actual results are a few points below what it predicted. We publish both numbers so you can judge the calibration yourself.',
                  style: TextStyle(fontSize: 12, height: 1.5, color: AppColors.inkMuted),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        const Text('BY TIER', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.8, color: AppColors.inkMuted)),
        const SizedBox(height: 12),
        Row(
          children: ['3odds', '5odds', '10odds'].map((key) {
            final meta = _tierMetaShort[key]!;
            final raw = stats.byType[key];
            final hitRate = raw is Map ? (raw['win_rate'] as num? ?? 0).toDouble() : (raw as num? ?? 0).toDouble();
            final settled = raw is Map ? (raw['settled'] as num? ?? 0).toInt() : 0;
            return Expanded(
              child: Padding(
                padding: EdgeInsets.only(right: key == '10odds' ? 0 : 8),
                child: GlassCard(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      TierBadge(tier: key.replaceAll('odds', '')),
                      const SizedBox(height: 10),
                      Text('${hitRate.toStringAsFixed(1)}%',
                          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: meta.accent)),
                      const SizedBox(height: 4),
                      Text('$settled settled', style: AppTheme.numStyle(fontSize: 10, color: AppColors.inkMuted)),
                    ],
                  ),
                ),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 24),
        const Text('HIT RATE BY WEEK', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.8, color: AppColors.inkMuted)),
        const SizedBox(height: 12),
        GlassCard(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              SizedBox(
                height: 144,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: kMockWeeklyTrend.map((w) {
                    final positive = w.hitRate >= 0.5;
                    return Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 3),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            Text('${(w.hitRate * 100).round()}', style: AppTheme.numStyle(fontSize: 10, color: AppColors.inkMuted)),
                            const SizedBox(height: 6),
                            Container(
                              height: 90 * (w.hitRate / maxWeek),
                              decoration: BoxDecoration(
                                color: (positive ? AppColors.win : AppColors.loss).withOpacity(positive ? 0.55 : 0.5),
                                borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(w.week, style: AppTheme.numStyle(fontSize: 10, color: AppColors.inkFaint)),
                          ],
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ),
              Container(
                margin: const EdgeInsets.only(top: 16),
                padding: const EdgeInsets.only(top: 12),
                decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.white.withOpacity(0.06)))),
                child: const Text(
                  'Two of the last eight weeks finished below break-even. Variance at this sample size is expected.',
                  style: TextStyle(fontSize: 11, color: AppColors.inkMuted),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        const Text('BY SPORT', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.8, color: AppColors.inkMuted)),
        const SizedBox(height: 12),
        GlassCard(padding: EdgeInsets.zero, child: Column(children: kMockSportPerformance.map((r) => _BarRow(row: r)).toList())),
        const SizedBox(height: 24),
        const Text('BY MARKET', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.8, color: AppColors.inkMuted)),
        const SizedBox(height: 12),
        GlassCard(padding: EdgeInsets.zero, child: Column(children: kMockMarketPerformance.map((r) => _BarRow(row: r)).toList())),
        const SizedBox(height: 20),
        Row(
          children: [
            Expanded(child: StatCard(label: 'Tickets tracked', value: '${stats.totalPredictions}', caption: 'Since launch')),
            const SizedBox(width: 12),
            const Expanded(child: StatCard(label: 'Longest win streak', value: '7', caption: '3-odds tier, recently', accent: AppColors.win)),
          ],
        ),
        const ResponsibleFooter(),
      ],
    );
  }
}

class _BarRow extends StatelessWidget {
  final BreakdownRow row;
  const _BarRow({required this.row});

  @override
  Widget build(BuildContext context) {
    final positive = row.hitRate >= 0.5;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          SizedBox(width: 100, child: Text(row.label, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13, color: AppColors.ink))),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: Container(
                height: 8,
                color: Colors.white.withOpacity(0.05),
                alignment: Alignment.centerLeft,
                child: FractionallySizedBox(
                  widthFactor: row.hitRate.clamp(0.0, 1.0),
                  child: Container(color: (positive ? AppColors.win : AppColors.loss).withOpacity(positive ? 0.6 : 0.55)),
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          SizedBox(
            width: 44,
            child: Text('${(row.hitRate * 100).toStringAsFixed(1)}%',
                textAlign: TextAlign.right, style: AppTheme.numStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.ink)),
          ),
          SizedBox(
            width: 48,
            child: Text('${row.legs} legs',
                textAlign: TextAlign.right, style: AppTheme.numStyle(fontSize: 11, color: AppColors.inkFaint)),
          ),
        ],
      ),
    );
  }
}
