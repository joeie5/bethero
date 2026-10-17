import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../../core/theme.dart';
import '../../../data/models/accumulator_model.dart';
import '../../providers/results_provider.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/Results.tsx` — settled-tickets list with tier + date-range
/// filters, each row showing tier badge, date, legs-hit fraction, combined
/// odds and status.
class ResultsScreen extends ConsumerStatefulWidget {
  const ResultsScreen({super.key});

  @override
  ConsumerState<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends ConsumerState<ResultsScreen> {
  String _tier = 'all';
  String _range = '7';

  static const _tierOptions = [
    ChipOption(id: 'all', label: 'All tiers'),
    ChipOption(id: '3', label: '3-Odds'),
    ChipOption(id: '5', label: '5-Odds'),
    ChipOption(id: '10', label: '10-Odds'),
  ];

  static const _rangeOptions = [
    (id: '7', label: 'Last 7 days'),
    (id: '30', label: 'Last 30 days'),
    (id: '90', label: 'Last 90 days'),
  ];

  String _tierOf(AccumulatorModel a) {
    switch (a.type) {
      case AccaType.three:
        return '3';
      case AccaType.five:
        return '5';
      case AccaType.ten:
        return '10';
    }
  }

  AppStatus _statusOf(AccumulatorModel a) {
    switch (a.status) {
      case AccaStatus.won:
        return AppStatus.won;
      case AccaStatus.lost:
        return AppStatus.lost;
      case AccaStatus.pending:
        return AppStatus.pending;
    }
  }

  @override
  Widget build(BuildContext context) {
    final historyAsync = ref.watch(accumulatorHistoryProvider);

    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: historyAsync.when(
          data: (history) {
            final cutoff = DateTime.now().subtract(Duration(days: int.parse(_range)));
            final settled = history.where((a) => a.status != AccaStatus.pending && a.createdAt.isAfter(cutoff)).toList();
            final rows = _tier == 'all' ? settled : settled.where((a) => _tierOf(a) == _tier).toList();
            final won = rows.where((a) => a.status == AccaStatus.won).length;

            return ListView(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Results', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: AppColors.ink)),
                        const SizedBox(height: 4),
                        Text('$won of ${rows.length} settled tickets won',
                            style: AppTheme.numStyle(fontSize: 14, color: AppColors.inkMuted)),
                      ],
                    ),
                    GestureDetector(
                      onTap: () => context.push('/performance'),
                      child: GlassCard(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        child: const Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.trending_up, size: 14, color: AppColors.win),
                            SizedBox(width: 6),
                            Text('Performance', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.ink)),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                FilterChips(options: _tierOptions, value: _tier, onChanged: (v) => setState(() => _tier = v)),
                const SizedBox(height: 12),
                Row(
                  children: _rangeOptions.map((o) {
                    final active = _range == o.id;
                    return Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: GestureDetector(
                        onTap: () => setState(() => _range = o.id),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                          decoration: BoxDecoration(
                            color: active ? Colors.white.withOpacity(0.08) : Colors.transparent,
                            border: Border.all(color: active ? Colors.white.withOpacity(0.2) : Colors.white.withOpacity(0.08)),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(o.label,
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: active ? AppColors.ink : AppColors.inkFaint)),
                        ),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 20),
                if (rows.isEmpty)
                  EmptyState(
                    icon: Icons.filter_alt_off,
                    title: 'Nothing matches that filter',
                    body: 'No settled tickets in this tier for the selected range.',
                    actionLabel: 'Clear filters',
                    onAction: () => setState(() => _tier = 'all'),
                  )
                else
                  ..._buildWeekGroups(rows),
                const SizedBox(height: 16),
                const ResponsibleFooter(),
              ],
            );
          },
          loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Column(children: [SkeletonRow(), SizedBox(height: 12), SkeletonRow(), SizedBox(height: 12), SkeletonRow()]),
          ),
          error: (e, _) => const EmptyState(icon: Icons.error_outline, title: "Couldn't load results", body: 'Pull to refresh or check your connection.'),
        ),
      ),
    );
  }

  List<Widget> _buildWeekGroups(List<AccumulatorModel> rows) {
    final byWeek = <int, List<AccumulatorModel>>{};
    final noWeek = <AccumulatorModel>[];
    for (final r in rows) {
      if (r.seasonWeek != null) {
        byWeek.putIfAbsent(r.seasonWeek!, () => []).add(r);
      } else {
        noWeek.add(r);
      }
    }
    final weeks = byWeek.keys.toList()..sort((a, b) => b.compareTo(a));

    final widgets = <Widget>[];
    for (final wk in weeks) {
      widgets.add(Padding(
        padding: const EdgeInsets.only(top: 8, bottom: 10),
        child: Text('WEEK $wk',
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
      ));
      widgets.addAll(byWeek[wk]!.map(_ticketRow));
    }
    if (noWeek.isNotEmpty) {
      widgets.add(Padding(
        padding: const EdgeInsets.only(top: 8, bottom: 10),
        child: Text('OTHER',
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
      ));
      widgets.addAll(noWeek.map(_ticketRow));
    }
    return widgets;
  }

  Widget _ticketRow(AccumulatorModel r) {
    final hit = r.legs.where((l) => l.status.toLowerCase() == 'won' || l.status.toLowerCase() == 'hit').length;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: GlassCard(
        padding: const EdgeInsets.all(16),
        onTap: () => context.push('/results/${r.id}'),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      TierBadge(tier: _tierOf(r)),
                      const SizedBox(width: 8),
                      Text(DateFormat('d MMM').format(r.createdAt),
                          style: AppTheme.numStyle(fontSize: 11, color: AppColors.inkFaint)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text('$hit/${r.legs.length} legs hit',
                      style: AppTheme.numStyle(fontSize: 11, color: AppColors.inkMuted)),
                ],
              ),
            ),
            OddsDisplay(odds: r.totalOdds, size: OddsSize.md),
            const SizedBox(width: 10),
            StatusBadge(status: _statusOf(r)),
            const SizedBox(width: 6),
            const Icon(Icons.chevron_right, size: 16, color: AppColors.inkFaint),
          ],
        ),
      ),
    );
  }
}
