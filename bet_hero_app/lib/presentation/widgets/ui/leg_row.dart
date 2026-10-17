import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../data/models/accumulator_leg_model.dart';
import '../common/sport_icon.dart';
import 'glass_card.dart';
import 'odds_display.dart';
import 'status_badge.dart';

/// Ports `LegRow.tsx` — a single accumulator leg card.
class LegRow extends StatelessWidget {
  final AccumulatorLegModel leg;
  final Color accent;
  final int index;

  const LegRow({super.key, required this.leg, required this.accent, required this.index});

  AppStatus? get _settledStatus {
    final s = leg.status.toLowerCase();
    if (s == 'won' || s == 'hit') return AppStatus.won;
    if (s == 'lost' || s == 'miss') return AppStatus.lost;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.xl2),
        onTap: leg.matchId != null ? () => context.push('/fixture/${leg.matchId}') : null,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 24,
                height: 24,
                margin: const EdgeInsets.only(top: 2),
                decoration: BoxDecoration(
                  color: accent.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                alignment: Alignment.center,
                child: Text(
                  '${index + 1}',
                  style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w700, color: accent),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        SportIcon(sportSlug: leg.sport, size: 13, color: AppColors.inkFaint),
                        const SizedBox(width: 5),
                        Expanded(
                          child: Text(
                            leg.league,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 11, color: AppColors.inkFaint),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${leg.homeTeam} vs ${leg.awayTeam}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppColors.ink),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 4,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: accent.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            leg.predictedOutcome,
                            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: accent),
                          ),
                        ),
                        Text(leg.market, style: const TextStyle(fontSize: 11, color: AppColors.inkFaint)),
                      ],
                    ),
                    if (leg.actualOutcome != null) ...[
                      const SizedBox(height: 6),
                      Text(
                        'Actual: ${leg.actualOutcome}',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: _settledStatus == AppStatus.won ? AppColors.win : AppColors.loss,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  OddsDisplay(odds: leg.odds, size: OddsSize.md),
                  const SizedBox(height: 4),
                  Text(
                    '${(leg.confidence * (leg.confidence <= 1 ? 100 : 1)).round()}% model',
                    style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.inkMuted),
                  ),
                  if (_settledStatus != null) ...[
                    const SizedBox(height: 6),
                    StatusBadge(status: _settledStatus!),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
