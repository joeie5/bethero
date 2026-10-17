import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../data/models/accumulator_model.dart';
import '../common/sport_icon.dart';
import 'glass_card.dart';
import 'odds_display.dart';
import 'probability_ring.dart';
import 'tier_badge.dart';

/// Ports `TierCard.tsx` — the accumulator tier summary card shown on Home.
class TierCard extends StatelessWidget {
  final AccumulatorModel ticket;
  final String tierId; // '3' | '5' | '10'

  const TierCard({super.key, required this.ticket, required this.tierId});

  @override
  Widget build(BuildContext context) {
    final meta = kTierMeta[tierId] ?? kTierMeta['3']!;
    final sports = ticket.legs.map((l) => l.sport).toSet().toList();
    final probability = ticket.confidenceScore > 1 ? ticket.confidenceScore / 100 : ticket.confidenceScore;

    return GlassCard(
      padding: EdgeInsets.zero,
      onTap: () => context.push('/ticket/$tierId'),
      child: Stack(
        children: [
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: Container(height: 1, color: meta.accent.withOpacity(0.4)),
          ),
          Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Container(
                                width: 6,
                                height: 6,
                                decoration: BoxDecoration(color: meta.accent, shape: BoxShape.circle),
                              ),
                              const SizedBox(width: 8),
                              Text(
                                meta.label,
                                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: meta.accent),
                              ),
                              const SizedBox(width: 6),
                              Text(meta.risk, style: const TextStyle(fontSize: 11, color: AppColors.inkFaint)),
                            ],
                          ),
                          const SizedBox(height: 12),
                          OddsDisplay(odds: ticket.totalOdds, size: OddsSize.lg),
                          const SizedBox(height: 4),
                          const Text(
                            'COMBINED ODDS',
                            style: TextStyle(fontSize: 11, letterSpacing: 0.6, color: AppColors.inkFaint),
                          ),
                        ],
                      ),
                    ),
                    ProbabilityRing(value: probability, color: meta.accent, label: 'Model', size: 68),
                  ],
                ),
                const SizedBox(height: 18),
                Container(
                  padding: const EdgeInsets.only(top: 14),
                  decoration: BoxDecoration(
                    border: Border(top: BorderSide(color: Colors.white.withOpacity(0.06))),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          Text(
                            '${ticket.legs.length} legs',
                            style: AppTheme.numStyle(fontSize: 12, fontWeight: FontWeight.w500, color: AppColors.inkMuted),
                          ),
                          const SizedBox(width: 10),
                          ...sports.take(5).map(
                                (s) => Padding(
                                  padding: const EdgeInsets.only(right: 4),
                                  child: SportIcon(sportSlug: s, size: 14, color: AppColors.inkFaint),
                                ),
                              ),
                        ],
                      ),
                      Row(
                        children: [
                          Text(
                            'View ticket',
                            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: meta.accent),
                          ),
                          const SizedBox(width: 4),
                          Icon(Icons.north_east, size: 14, color: meta.accent),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
