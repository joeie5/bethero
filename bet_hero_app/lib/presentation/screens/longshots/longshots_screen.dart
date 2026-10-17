import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/di.dart';
import '../../../core/theme.dart';
import '../../../data/mock/bethero_mock_data.dart';
import '../../../data/repositories/longshot_repository.dart';
import '../../widgets/common/sport_icon.dart';
import '../../widgets/ui/ui_kit.dart';

final _longshotsProvider = FutureProvider.family<LongshotsResult, String>((ref, sport) {
  return ref.watch(longshotRepositoryProvider).getLongshots(sport);
});

/// Real long-shot picks from completed matches this season, paired with
/// what actually happened — football only for now (the only sport with
/// trained models); other sports show a "coming soon" state.
class LongshotsScreen extends ConsumerStatefulWidget {
  const LongshotsScreen({super.key});

  @override
  ConsumerState<LongshotsScreen> createState() => _LongshotsScreenState();
}

class _LongshotsScreenState extends ConsumerState<LongshotsScreen> {
  String _sport = 'all';

  static const _liveSports = {'football'};

  @override
  Widget build(BuildContext context) {
    final asyncResult = ref.watch(_longshotsProvider(_sport == 'all' ? 'football' : _sport));

    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
          children: [
            const Text('Longshot Daily', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: AppColors.ink)),
            const SizedBox(height: 6),
            const Text(
              'Real picks the model made on completed matches this season, shown against what actually happened.',
              style: TextStyle(fontSize: 13, height: 1.5, color: AppColors.inkMuted),
            ),
            const SizedBox(height: 18),
            FilterChips(
              accent: AppColors.gold,
              value: _sport,
              options: [
                const ChipOption(id: 'all', label: 'All'),
                ...kMockSports.map((s) => ChipOption(id: s.id, label: s.name)),
              ],
              onChanged: (v) => setState(() => _sport = v),
            ),
            const SizedBox(height: 18),
            if (_sport != 'all' && !_liveSports.contains(_sport))
              EmptyState(
                icon: Icons.hourglass_top,
                title: 'Coming soon',
                body: 'Only football has trained models right now. Other sports are on the way.',
                actionLabel: 'Show football',
                onAction: () => setState(() => _sport = 'football'),
              )
            else
              asyncResult.when(
                loading: () => const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (err, _) => EmptyState(
                  icon: Icons.error_outline,
                  title: 'Couldn\'t load longshots',
                  body: '$err',
                  actionLabel: 'Retry',
                  onAction: () => ref.invalidate(_longshotsProvider),
                ),
                data: (result) => _buildContent(result),
              ),
            const ResponsibleFooter(),
          ],
        ),
      ),
    );
  }

  Widget _buildContent(LongshotsResult result) {
    if (result.bestBet == null && result.picks.isEmpty) {
      return EmptyState(
        icon: Icons.search_off,
        title: 'No longshots yet',
        body: 'The model hasn\'t surfaced any high-odds picks from completed matches yet.',
        actionLabel: 'Refresh',
        onAction: () => ref.invalidate(_longshotsProvider),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (result.bestBet != null) ...[
          _bestBetCard(result.bestBet!),
          const SizedBox(height: 20),
        ],
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text('ALL LONGSHOTS',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
            const Text('Sorted by odds', style: TextStyle(fontSize: 11, color: AppColors.inkFaint)),
          ],
        ),
        const SizedBox(height: 10),
        ...result.picks.map(_pickRow),
      ],
    );
  }

  Widget _bestBetCard(LongshotPick bet) {
    final resultColor = bet.wasCorrect ? AppColors.win : AppColors.loss;
    return GlassCard(
      border: Border.all(color: AppColors.gold.withOpacity(0.35)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: AppColors.gold.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: AppColors.gold.withOpacity(0.35)),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.bolt, size: 12, color: AppColors.gold),
                    SizedBox(width: 5),
                    Text('Best Bet', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.gold)),
                  ],
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: resultColor.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  bet.wasCorrect ? 'Hit' : 'Missed',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: resultColor),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: GestureDetector(
                  onTap: () => context.push('/fixture/${bet.fixtureId}'),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('${bet.homeTeam} vs ${bet.awayTeam}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: AppColors.ink)),
                      const SizedBox(height: 4),
                      Text('${bet.league} · ${bet.matchDate}',
                          style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.inkFaint)),
                      const SizedBox(height: 10),
                      Text(bet.selection,
                          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppColors.gold)),
                      Text(bet.market, style: const TextStyle(fontSize: 11, color: AppColors.inkMuted)),
                    ],
                  ),
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  if (bet.odds != null) OddsDisplay(odds: bet.odds!, size: OddsSize.lg, color: AppColors.gold),
                  const SizedBox(height: 4),
                  Text('${(bet.modelProbability * 100).toStringAsFixed(1)}% modelled',
                      style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.inkMuted)),
                ],
              ),
            ],
          ),
          Container(
            margin: const EdgeInsets.only(top: 14),
            padding: const EdgeInsets.only(top: 12),
            decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.white.withOpacity(0.06)))),
            child: Text('Actual result: ${bet.actualOutcome ?? "unresolved"}',
                style: const TextStyle(fontSize: 12, height: 1.5, color: AppColors.inkMuted)),
          ),
        ],
      ),
    );
  }

  Widget _pickRow(LongshotPick l) {
    final resultColor = l.wasCorrect ? AppColors.win : AppColors.loss;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: GlassCard(
        onTap: () => context.push('/fixture/${l.fixtureId}'),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(color: Colors.white.withOpacity(0.05), borderRadius: BorderRadius.circular(10)),
              alignment: Alignment.center,
              child: const SportIcon(sportSlug: 'football', size: 16, color: AppColors.inkMuted),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${l.homeTeam} vs ${l.awayTeam}',
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                  Text('Predicted: ${l.selection}', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: AppColors.inkMuted)),
                  Text('Actual: ${l.actualOutcome ?? "unresolved"}',
                      maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: resultColor)),
                  Text(l.market, style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.inkFaint)),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (l.odds != null) OddsDisplay(odds: l.odds!, size: OddsSize.md),
                Text('${(l.modelProbability * 100).toStringAsFixed(1)}% model',
                    style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.inkFaint)),
                Text(l.wasCorrect ? 'Hit' : 'Missed',
                    style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: resultColor)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
