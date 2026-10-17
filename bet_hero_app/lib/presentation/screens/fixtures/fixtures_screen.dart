import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import '../../../core/theme.dart';
import '../../../data/mock/bethero_mock_data.dart';
import '../../../data/models/fixture_model.dart';
import '../../providers/fixture_provider.dart';
import '../../widgets/common/sport_icon.dart';
import '../../widgets/ui/ui_kit.dart';

enum _SortKey { time, edge }

/// Ports `pages/Fixtures.tsx` — header with fixture count, "By kickoff" /
/// "Model picks first" sort toggle, fixtures grouped into collapsible
/// LeagueSections, each row showing kickoff time, teams, best-market badge.
class FixturesScreen extends ConsumerStatefulWidget {
  final String? initialSport;
  const FixturesScreen({super.key, this.initialSport});

  @override
  ConsumerState<FixturesScreen> createState() => _FixturesScreenState();
}

class _FixturesScreenState extends ConsumerState<FixturesScreen> {
  _SortKey _sort = _SortKey.time;

  @override
  void initState() {
    super.initState();
    if (widget.initialSport != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(selectedSportProvider.notifier).state = widget.initialSport!;
      });
    }
  }

  String _sportName(String id) {
    final match = kMockSports.where((s) => s.id == id);
    if (match.isNotEmpty) return match.first.name;
    if (id.isEmpty) return 'Fixtures';
    return id[0].toUpperCase() + id.substring(1);
  }

  @override
  Widget build(BuildContext context) {
    final selectedSport = ref.watch(selectedSportProvider);
    final fixturesAsync = ref.watch(fixturesBySportProvider(selectedSport));

    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: ScreenHeader(title: _sportName(selectedSport), subtitle: fixturesAsync.maybeWhen(data: (f) => '${f.length} fixtures priced today', orElse: () => null)),
      body: fixturesAsync.when(
        data: (fixtures) => _buildBody(fixtures, selectedSport),
        loading: () => const Padding(
          padding: EdgeInsets.all(20),
          child: Column(children: [SkeletonRow(), SizedBox(height: 12), SkeletonRow(), SizedBox(height: 12), SkeletonRow()]),
        ),
        error: (e, _) => EmptyState(
          icon: Icons.schedule,
          title: 'Fixtures coming soon',
          body: '${_sportName(selectedSport)} fixtures for this date haven\'t been loaded yet. They\'re added automatically once the data source picks them up — check back soon.',
          actionLabel: 'Browse other sports',
          onAction: () => context.push('/sports'),
        ),
      ),
    );
  }

  Widget _buildBody(List<FixtureModel> fixtures, String sport) {
    final sorted = [...fixtures];
    if (_sort == _SortKey.time) {
      sorted.sort((a, b) => a.matchDate.compareTo(b.matchDate));
    } else {
      sorted.sort((a, b) => (b.predictions?.isNotEmpty == true ? 1 : 0) - (a.predictions?.isNotEmpty == true ? 1 : 0));
    }
    final grouped = <String, List<FixtureModel>>{};
    for (final f in sorted) {
      grouped.putIfAbsent(f.league, () => []).add(f);
    }

    return ListView(
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
          child: Row(
            children: [
              _SortChip(label: 'By kickoff', selected: _sort == _SortKey.time, onTap: () => setState(() => _sort = _SortKey.time)),
              const SizedBox(width: 8),
              _SortChip(label: 'Model picks first', selected: _sort == _SortKey.edge, onTap: () => setState(() => _sort = _SortKey.edge)),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
          child: fixtures.isEmpty
              ? EmptyState(
                  icon: Icons.schedule,
                  title: 'Fixtures coming soon',
                  body: '${_sportName(sport)} fixtures for this date haven\'t been loaded yet. They\'re added automatically once the data source picks them up — check back soon.',
                  actionLabel: 'Browse other sports',
                  onAction: () => context.push('/sports'),
                )
              : Column(
                  children: grouped.entries.map((e) {
                    return LeagueSection(
                      league: e.key,
                      count: e.value.length,
                      child: Column(
                        children: e.value.map((f) => _FixtureRow(fixture: f)).toList(),
                      ),
                    );
                  }).toList(),
                ),
        ),
        const ResponsibleFooter(),
      ],
    );
  }
}

class _SortChip extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _SortChip({required this.label, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? AppColors.ink : Colors.white.withOpacity(0.04),
          border: Border.all(color: selected ? Colors.transparent : Colors.white.withOpacity(0.1)),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(label,
            style: TextStyle(
                fontSize: 12, fontWeight: FontWeight.w600, color: selected ? AppColors.base : AppColors.inkMuted)),
      ),
    );
  }
}

class _FixtureRow extends StatelessWidget {
  final FixtureModel fixture;
  const _FixtureRow({required this.fixture});

  @override
  Widget build(BuildContext context) {
    final best = fixture.predictions != null && fixture.predictions!.isNotEmpty ? fixture.predictions!.first : null;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: GlassCard(
        padding: const EdgeInsets.all(14),
        onTap: () => context.push('/fixture/${fixture.id}'),
        child: Row(
          children: [
            SizedBox(
              width: 44,
              child: Text(DateFormat('HH:mm').format(fixture.matchDate),
                  style: AppTheme.numStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.inkMuted)),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(fixture.homeTeam,
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                  Text(fixture.awayTeam,
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14, color: AppColors.inkMuted)),
                ],
              ),
            ),
            if (best != null) ...[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.tier3.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(best.predictedOutcome,
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.tier3)),
              ),
              const SizedBox(width: 8),
            ] else
              SportIcon(sportSlug: fixture.sport, size: 16, color: AppColors.inkFaint),
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right, size: 16, color: AppColors.inkFaint),
          ],
        ),
      ),
    );
  }
}
