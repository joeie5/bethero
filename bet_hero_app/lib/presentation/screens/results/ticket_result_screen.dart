import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import '../../../data/models/accumulator_model.dart';
import '../../providers/results_provider.dart';
import '../../widgets/ui/ui_kit.dart';
import '../misc/not_found_screen.dart';

/// Ports `pages/TicketResult.tsx` — a single settled ticket's hero card
/// (combined odds, model probability ring, legs-hit summary) plus its full
/// leg-by-leg breakdown. Looks the ticket up out of `accumulatorHistoryProvider`
/// (already-loaded real backend history) by id.
class TicketResultScreen extends ConsumerWidget {
  final String ticketId;
  const TicketResultScreen({super.key, required this.ticketId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final historyAsync = ref.watch(accumulatorHistoryProvider);

    return historyAsync.when(
      data: (list) {
        final matches = list.where((t) => t.id == ticketId);
        if (matches.isEmpty) return const NotFoundScreen();
        final ticket = matches.first;
        final tierId = ticket.type.value.replaceAll('odds', '');
        final meta = kTierMeta[tierId] ?? kTierMeta['3']!;
        final won = ticket.status == AccaStatus.won;
        final hits = ticket.legs
            .where((l) => l.status.toLowerCase() == 'won' || l.status.toLowerCase() == 'hit')
            .length;
        final probability = ticket.confidenceScore > 1 ? ticket.confidenceScore / 100 : ticket.confidenceScore;

        return Scaffold(
          backgroundColor: AppColors.base,
          appBar: ScreenHeader(
            title: '${meta.label} ticket',
            subtitle: _formatDate(ticket.createdAt),
            action: StatusBadge(status: won ? AppStatus.won : AppStatus.lost),
          ),
          body: ListView(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
            children: [
              GlassCard(
                padding: const EdgeInsets.all(20),
                border: Border.all(color: meta.accent.withOpacity(0.27)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('COMBINED ODDS',
                                style: TextStyle(fontSize: 11, letterSpacing: 0.6, color: AppColors.inkFaint)),
                            const SizedBox(height: 4),
                            OddsDisplay(odds: ticket.totalOdds, size: OddsSize.hero),
                            const SizedBox(height: 8),
                            Text('$hits of ${ticket.legs.length} legs hit',
                                style: AppTheme.numStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.ink)),
                          ],
                        ),
                        ProbabilityRing(value: probability, color: meta.accent, size: 92, stroke: 7, label: 'Model'),
                      ],
                    ),
                    Container(
                      margin: const EdgeInsets.only(top: 18),
                      padding: const EdgeInsets.only(top: 14),
                      decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.white.withOpacity(0.06)))),
                      child: Text(
                        'Modelled at ${(probability * 100).toStringAsFixed(0)}% before kick-off. Settled ${_formatDate(ticket.createdAt)}.',
                        style: AppTheme.numStyle(fontSize: 12, color: AppColors.inkMuted),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              const Text('LEGS',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.8, color: AppColors.inkMuted)),
              const SizedBox(height: 12),
              for (int i = 0; i < ticket.legs.length; i++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: LegRow(leg: ticket.legs[i], accent: meta.accent, index: i),
                ),
              const ResponsibleFooter(),
            ],
          ),
        );
      },
      loading: () => Scaffold(
        backgroundColor: AppColors.base,
        appBar: const ScreenHeader(title: 'Ticket result'),
        body: const Center(child: CircularProgressIndicator(color: AppColors.tier3)),
      ),
      error: (e, _) => const NotFoundScreen(),
    );
  }

  String _formatDate(DateTime d) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${d.day} ${months[d.month - 1]}';
  }
}
