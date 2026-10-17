import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../data/models/accumulator_model.dart';
import '../../providers/accumulator_provider.dart';
import '../../providers/fixture_provider.dart';
import '../../widgets/common/sport_icon.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/Home.tsx` — greeting header, tier cards grid, upcoming fixtures.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final accasAsync = ref.watch(todayAccumulatorsProvider);
    final fixturesAsync = ref.watch(upcomingFixturesProvider);
    final selectedSport = ref.watch(selectedSportProvider);

    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: CustomScrollView(
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: const [
                        LogoMark(size: 30),
                        SizedBox(width: 10),
                        Wordmark(fontSize: 20),
                      ],
                    ),
                    Row(
                      children: [
                        IconButton(
                          onPressed: () => context.push('/notifications'),
                          icon: const Icon(Icons.notifications_none, color: AppColors.inkMuted),
                        ),
                        IconButton(
                          onPressed: () => context.push('/settings'),
                          icon: const Icon(Icons.person_outline, color: AppColors.inkMuted),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      "Today's AI Tickets",
                      style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AppColors.ink),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Ranked by risk. Updated pre-kickoff.',
                      style: TextStyle(fontSize: 13, color: AppColors.inkMuted),
                    ),
                    const SizedBox(height: 20),
                    _buildTierCards(accasAsync),
                    const SizedBox(height: 28),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Upcoming Fixtures',
                            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: AppColors.ink)),
                        GestureDetector(
                          onTap: () => context.push('/sports'),
                          child: const Text('See all',
                              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.tier3)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                  ],
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(left: 20),
                child: _buildSportFilters(ref),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
                child: _buildFixturesPreview(fixturesAsync, selectedSport),
              ),
            ),
            const SliverToBoxAdapter(child: ResponsibleFooter()),
            const SliverToBoxAdapter(child: SizedBox(height: 90)),
          ],
        ),
      ),
    );
  }

  Widget _buildTierCards(AsyncValue<List<AccumulatorModel>> accasAsync) {
    return accasAsync.when(
      data: (accas) {
        AccumulatorModel findOrEmpty(AccaType t) =>
            accas.firstWhere((a) => a.type == t, orElse: () => _emptyAcca(t));
        return Column(
          children: [
            TierCard(ticket: findOrEmpty(AccaType.three), tierId: '3'),
            const SizedBox(height: 14),
            TierCard(ticket: findOrEmpty(AccaType.five), tierId: '5'),
            const SizedBox(height: 14),
            TierCard(ticket: findOrEmpty(AccaType.ten), tierId: '10'),
          ],
        );
      },
      loading: () => const Column(
        children: [SkeletonTierCard(), SizedBox(height: 14), SkeletonTierCard(), SizedBox(height: 14), SkeletonTierCard()],
      ),
      error: (e, _) => EmptyState(
        icon: Icons.error_outline,
        title: "Couldn't load tickets",
        body: 'Pull to refresh or check your connection.',
      ),
    );
  }

  Widget _buildSportFilters(WidgetRef ref) {
    final sports = ['all', 'football', 'basketball', 'nfl', 'mlb', 'nhl', 'tennis', 'cricket'];
    final selected = ref.watch(selectedSportProvider);
    return FilterChips(
      options: sports
          .map((s) => ChipOption(id: s, label: s == 'all' ? 'All' : s[0].toUpperCase() + s.substring(1)))
          .toList(),
      value: selected,
      accent: AppColors.tier3,
      onChanged: (v) => ref.read(selectedSportProvider.notifier).state = v,
    );
  }

  Widget _buildFixturesPreview(AsyncValue<List> fixturesAsync, String selectedSport) {
    return fixturesAsync.when(
      data: (fixtures) {
        final filtered = selectedSport == 'all'
            ? fixtures
            : fixtures.where((f) => f.sport.toLowerCase() == selectedSport).toList();
        if (filtered.isEmpty) {
          return const EmptyState(
            icon: Icons.event_busy,
            title: 'No fixtures',
            body: 'No upcoming fixtures for this sport right now.',
          );
        }
        return SizedBox(
          height: 128,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: filtered.length,
            separatorBuilder: (_, __) => const SizedBox(width: 10),
            itemBuilder: (context, index) {
              final fixture = filtered[index];
              return GlassCard(
                padding: const EdgeInsets.all(14),
                onTap: () => context.push('/fixture/${fixture.id}'),
                child: SizedBox(
                  width: 168,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          SportIcon(sportSlug: fixture.sport, size: 13, color: AppColors.inkFaint),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(fixture.league,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 10, color: AppColors.inkFaint)),
                          ),
                        ],
                      ),
                      const Spacer(),
                      Text(fixture.homeTeam,
                          maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: AppColors.ink)),
                      const Text('vs', style: TextStyle(color: AppColors.inkFaint, fontSize: 10)),
                      Text(fixture.awayTeam,
                          maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: AppColors.ink)),
                      const SizedBox(height: 8),
                      Text(fixture.matchDate.toString().substring(11, 16),
                          style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.gold)),
                    ],
                  ),
                ),
              );
            },
          ),
        );
      },
      loading: () => const SizedBox(
        height: 128,
        child: Row(children: [Expanded(child: SkeletonRow()), SizedBox(width: 10), Expanded(child: SkeletonRow())]),
      ),
      error: (e, _) => const Text('Fixtures unavailable', style: TextStyle(color: AppColors.inkMuted)),
    );
  }

  AccumulatorModel _emptyAcca(AccaType type) {
    return AccumulatorModel(
      id: '0',
      type: type,
      totalOdds: 0.0,
      status: AccaStatus.pending,
      confidenceScore: 0.0,
      createdAt: DateTime.now(),
      legs: [],
    );
  }
}
