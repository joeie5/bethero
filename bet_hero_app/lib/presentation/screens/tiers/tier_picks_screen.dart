import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/di.dart';
import '../../../core/theme.dart';
import '../../../data/repositories/tier_repository.dart';
import '../../widgets/ui/ui_kit.dart';

final _tierLeaguesProvider = FutureProvider<List<TierGroup>>((ref) {
  return ref.watch(tierRepositoryProvider).getTierLeagues();
});

final _availableDaysProvider = FutureProvider<List<AvailableDay>>((ref) {
  return ref.watch(tierRepositoryProvider).getAvailableDays();
});

final _marketsProvider = FutureProvider<List<MarketOption>>((ref) {
  return ref.watch(tierRepositoryProvider).getMarkets();
});

final _mlModelsProvider = FutureProvider<List<MlModelOption>>((ref) {
  return ref.watch(tierRepositoryProvider).getMlModels();
});

class _TierPredictArgs {
  final String date;
  final List<int> tiers;
  final List<MarketOption> marketOptions;
  final String mlModel;
  final int matchCount;
  const _TierPredictArgs(this.date, this.tiers, this.marketOptions, this.mlModel, this.matchCount);

  @override
  bool operator ==(Object other) {
    if (other is! _TierPredictArgs) return false;
    final otherIds = other.marketOptions.map((m) => m.id).toSet();
    final ids = marketOptions.map((m) => m.id).toSet();
    return other.date == date &&
        other.matchCount == matchCount &&
        other.mlModel == mlModel &&
        other.tiers.length == tiers.length &&
        other.tiers.every(tiers.contains) &&
        otherIds.length == ids.length &&
        otherIds.containsAll(ids);
  }

  @override
  int get hashCode => Object.hash(
        date,
        matchCount,
        mlModel,
        Object.hashAll(tiers.toList()..sort()),
        Object.hashAll(marketOptions.map((m) => m.id).toList()..sort()),
      );
}

final _tierPredictProvider = FutureProvider.family<TierPredictResult, _TierPredictArgs>((ref, args) {
  return ref.watch(tierRepositoryProvider).predictForTiers(
        date: args.date,
        tiers: args.tiers,
        marketOptions: args.marketOptions,
        mlModel: args.mlModel,
        matchCount: args.matchCount,
      );
});

/// Tier Picks — lets the user pick a season week, one or more league
/// quality-tiers, and how many matches they want; the model returns its
/// best-probability selections from that week's fixtures in those tiers.
class TierPicksScreen extends ConsumerStatefulWidget {
  const TierPicksScreen({super.key});

  @override
  ConsumerState<TierPicksScreen> createState() => _TierPicksScreenState();
}

class _TierPicksScreenState extends ConsumerState<TierPicksScreen> {
  String? _selectedDate;
  final Set<int> _selectedTiers = {1};
  final Set<String> _selectedMarketIds = {};
  String _selectedMlModel = 'ensemble';
  int _matchCount = 10;
  bool _searched = false;

  // XGBoost/LightGBM's raw 1X2 output can collapse to near-certain Draw on
  // some fixtures (confirmed live: 95-98% Draw where the Ensemble — which
  // also blends in NeuralNetwork/LSTM — gives a much more even spread).
  // These two overfit specifically on 1X2, not the other markets.
  static const _treeModelsProneToOverconfidence = {'XGBoostBetModel', 'LightGBMBetModel'};
  bool get _showsTreeModelWarning =>
      _treeModelsProneToOverconfidence.contains(_selectedMlModel) &&
      _selectedMarketIds.contains('1X2');

  @override
  Widget build(BuildContext context) {
    final daysAsync = ref.watch(_availableDaysProvider);
    final tierGroupsAsync = ref.watch(_tierLeaguesProvider);
    final marketsAsync = ref.watch(_marketsProvider);
    final mlModelsAsync = ref.watch(_mlModelsProvider);

    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
          children: [
            const Text('Tier Picks', style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: AppColors.ink)),
            const SizedBox(height: 6),
            const Text(
              'Pick a day and league tiers — the model returns its best picks from that day\'s fixtures.',
              style: TextStyle(fontSize: 13, height: 1.5, color: AppColors.inkMuted),
            ),
            const SizedBox(height: 20),

            const Text('DAY', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
            const SizedBox(height: 8),
            daysAsync.when(
              loading: () => const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: LinearProgressIndicator()),
              error: (e, _) => Text('Couldn\'t load days: $e', style: const TextStyle(color: AppColors.loss, fontSize: 12)),
              data: (days) => _dayPicker(days),
            ),
            const SizedBox(height: 20),

            const Text('LEAGUE TIER', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
            const SizedBox(height: 8),
            tierGroupsAsync.when(
              loading: () => const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: LinearProgressIndicator()),
              error: (e, _) => Text('Couldn\'t load tiers: $e', style: const TextStyle(color: AppColors.loss, fontSize: 12)),
              data: (groups) => _tierPicker(groups),
            ),
            const SizedBox(height: 20),

            const Text('MARKET', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
            const SizedBox(height: 8),
            marketsAsync.when(
              loading: () => const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: LinearProgressIndicator()),
              error: (e, _) => Text('Couldn\'t load markets: $e', style: const TextStyle(color: AppColors.loss, fontSize: 12)),
              data: (markets) => _marketPicker(markets),
            ),
            const SizedBox(height: 20),

            const Text('ML MODEL', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
            const SizedBox(height: 4),
            const Text(
              'Ensemble combines all 5 models. Picking one shows that algorithm\'s own raw prediction instead.',
              style: TextStyle(fontSize: 11, height: 1.4, color: AppColors.inkFaint),
            ),
            const SizedBox(height: 8),
            mlModelsAsync.when(
              loading: () => const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: LinearProgressIndicator()),
              error: (e, _) => Text('Couldn\'t load models: $e', style: const TextStyle(color: AppColors.loss, fontSize: 12)),
              data: (models) => _mlModelPicker(models),
            ),
            if (_showsTreeModelWarning)
              const Padding(
                padding: EdgeInsets.only(top: 10),
                child: Text(
                  'XGBoost and LightGBM can be overconfident on Match Result (1X2) — they '
                  'sometimes call a near-certain Draw when the Ensemble sees a much more '
                  'even spread. The Ensemble already corrects for this; treat this raw '
                  'model\'s number as a data point, not a call to trust on its own.',
                  style: TextStyle(fontSize: 11, height: 1.4, color: AppColors.tier5),
                ),
              ),
            const SizedBox(height: 20),

            const Text('NUMBER OF MATCHES', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
            const SizedBox(height: 8),
            _matchCountPicker(),
            const SizedBox(height: 20),

            if (_selectedMlModel != 'ensemble' && _selectedMarketIds.isEmpty)
              const Padding(
                padding: EdgeInsets.only(bottom: 10),
                child: Text(
                  'Select at least one market above to use a specific ML model.',
                  style: TextStyle(fontSize: 12, color: AppColors.loss),
                ),
              ),
            AppButton(
              label: 'Get predictions',
              full: true,
              onPressed: _selectedDate == null ||
                      _selectedTiers.isEmpty ||
                      (_selectedMlModel != 'ensemble' && _selectedMarketIds.isEmpty)
                  ? null
                  : () => setState(() => _searched = true),
            ),
            const SizedBox(height: 20),

            if (_searched && _selectedDate != null && _selectedTiers.isNotEmpty)
              marketsAsync.when(
                loading: () => const SizedBox.shrink(),
                error: (e, _) => const SizedBox.shrink(),
                data: (allMarkets) => _resultsSection(_TierPredictArgs(
                  _selectedDate!,
                  _selectedTiers.toList(),
                  allMarkets.where((m) => _selectedMarketIds.contains(m.id)).toList(),
                  _selectedMlModel,
                  _matchCount,
                )),
              ),

            const ResponsibleFooter(),
          ],
        ),
      ),
    );
  }

  Widget _dayPicker(List<AvailableDay> days) {
    if (days.isEmpty) {
      return const Text('No fixture days available yet.', style: TextStyle(fontSize: 12, color: AppColors.inkFaint));
    }
    // Most recent/soonest date first — the season's opening day is rarely
    // what anyone wants to see by default now that selection is per-day
    // rather than per-week.
    final ordered = days.reversed.toList();
    _selectedDate ??= ordered.first.date;
    return SizedBox(
      height: 40,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: ordered.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final d = ordered[i];
          final active = d.date == _selectedDate;
          return ChoiceChip(
            label: Text('${d.date} (${d.fixtureCount})'),
            selected: active,
            onSelected: (_) => setState(() {
              _selectedDate = d.date;
              _searched = false;
            }),
            labelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: active ? AppColors.base : AppColors.inkMuted),
            selectedColor: AppColors.tier3,
            backgroundColor: Colors.white.withOpacity(0.05),
            side: BorderSide(color: Colors.white.withOpacity(0.08)),
          );
        },
      ),
    );
  }

  Widget _tierPicker(List<TierGroup> groups) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: groups.map((g) {
        final active = _selectedTiers.contains(g.tier);
        return FilterChip(
          label: Text('Tier ${g.tier} (${g.leagues.length})'),
          selected: active,
          onSelected: (sel) => setState(() {
            if (sel) {
              _selectedTiers.add(g.tier);
            } else {
              _selectedTiers.remove(g.tier);
            }
            _searched = false;
          }),
          labelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: active ? AppColors.base : AppColors.inkMuted),
          selectedColor: AppColors.gold,
          backgroundColor: Colors.white.withOpacity(0.05),
          side: BorderSide(color: Colors.white.withOpacity(0.08)),
        );
      }).toList(),
    );
  }

  Widget _marketPicker(List<MarketOption> markets) {
    // Group by market so Goals/Corners show their individual lines under one
    // heading instead of one flat "Goals" chip that hides which line it means.
    final byMarket = <String, List<MarketOption>>{};
    for (final m in markets) {
      byMarket.putIfAbsent(m.market, () => []).add(m);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilterChip(
              label: const Text('All'),
              selected: _selectedMarketIds.isEmpty,
              onSelected: (_) => setState(() {
                _selectedMarketIds.clear();
                _searched = false;
              }),
              labelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: _selectedMarketIds.isEmpty ? AppColors.base : AppColors.inkMuted),
              selectedColor: AppColors.gold,
              backgroundColor: Colors.white.withOpacity(0.05),
              side: BorderSide(color: Colors.white.withOpacity(0.08)),
            ),
          ],
        ),
        for (final entry in byMarket.entries) ...[
          const SizedBox(height: 10),
          if (entry.value.length > 1)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Text(
                entry.value.first.label.split(':').first.toUpperCase(),
                style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkFaint),
              ),
            ),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: entry.value.map((m) {
              final active = _selectedMarketIds.contains(m.id);
              return FilterChip(
                label: Text(m.selection ?? m.label),
                selected: active,
                onSelected: (sel) => setState(() {
                  if (sel) {
                    _selectedMarketIds.add(m.id);
                  } else {
                    _selectedMarketIds.remove(m.id);
                  }
                  _searched = false;
                }),
                labelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: active ? AppColors.base : AppColors.inkMuted),
                selectedColor: AppColors.gold,
                backgroundColor: Colors.white.withOpacity(0.05),
                side: BorderSide(color: Colors.white.withOpacity(0.08)),
              );
            }).toList(),
          ),
        ],
      ],
    );
  }

  Widget _mlModelPicker(List<MlModelOption> models) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: models.map((m) {
        final active = m.id == _selectedMlModel;
        return ChoiceChip(
          label: Text(m.label),
          selected: active,
          onSelected: (_) => setState(() {
            _selectedMlModel = m.id;
            _searched = false;
          }),
          labelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: active ? AppColors.base : AppColors.inkMuted),
          selectedColor: AppColors.tier3,
          backgroundColor: Colors.white.withOpacity(0.05),
          side: BorderSide(color: Colors.white.withOpacity(0.08)),
        );
      }).toList(),
    );
  }

  Widget _matchCountPicker() {
    const options = [1, 2, 3, 5, 10, 15, 20];
    return SizedBox(
      height: 40,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: options.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final n = options[i];
          final active = n == _matchCount;
          return ChoiceChip(
            label: Text('$n'),
            selected: active,
            onSelected: (_) => setState(() {
              _matchCount = n;
              _searched = false;
            }),
            labelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: active ? AppColors.base : AppColors.inkMuted),
            selectedColor: AppColors.tier3,
            backgroundColor: Colors.white.withOpacity(0.05),
            side: BorderSide(color: Colors.white.withOpacity(0.08)),
          );
        },
      ),
    );
  }

  Widget _resultsSection(_TierPredictArgs args) {
    final picksAsync = ref.watch(_tierPredictProvider(args));
    return picksAsync.when(
      loading: () => const Padding(
        padding: EdgeInsets.symmetric(vertical: 40),
        child: Center(child: CircularProgressIndicator()),
      ),
      error: (err, _) => EmptyState(
        icon: Icons.error_outline,
        title: 'Couldn\'t load predictions',
        body: '$err',
        actionLabel: 'Retry',
        onAction: () => ref.invalidate(_tierPredictProvider),
      ),
      data: (result) {
        final picks = result.picks;
        if (picks.isEmpty) {
          final addingSoon = result.message != null;
          return EmptyState(
            icon: addingSoon ? Icons.schedule : Icons.search_off,
            title: addingSoon ? 'Fixtures coming soon' : 'No fixtures found',
            body: result.message ?? 'No matches in this week for the selected tiers.',
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${picks.length} PICKS',
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
            const SizedBox(height: 10),
            ...picks.map(_pickRow),
          ],
        );
      },
    );
  }

  Widget _pickRow(TierPick p) {
    final resultColor = p.status == 'won' ? AppColors.win : (p.status == 'lost' ? AppColors.loss : AppColors.inkFaint);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: GlassCard(
        onTap: () => context.push('/fixture/${p.fixtureId}'),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(color: Colors.white.withOpacity(0.05), borderRadius: BorderRadius.circular(10)),
              alignment: Alignment.center,
              child: Text('T${p.tier}', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.inkMuted)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${p.homeTeam} vs ${p.awayTeam}',
                      maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                  Text('${p.leagueName} · ${p.matchDate}',
                      maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.inkFaint)),
                  Row(
                    children: [
                      Text(p.selection, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.gold)),
                      if (p.edge != null && p.edge! > 0.05) ...[
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: AppColors.win.withOpacity(0.12),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            '+${(p.edge! * 100).toStringAsFixed(0)}% edge',
                            style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: AppColors.win),
                          ),
                        ),
                      ],
                    ],
                  ),
                  if (p.actualOutcome != null)
                    Text('Actual: ${p.actualOutcome}',
                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: resultColor)),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (p.odds != null) OddsDisplay(odds: p.odds!, size: OddsSize.md),
                Text('${(p.modelProbability * 100).toStringAsFixed(1)}% model',
                    style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.inkFaint)),
                if (p.status != 'pending')
                  Text(p.status == 'won' ? 'Won' : 'Lost',
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: resultColor)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
