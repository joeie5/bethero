import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme.dart';
import '../../../data/models/accumulator_leg_model.dart';
import '../../../data/models/accumulator_model.dart';
import '../../providers/accumulator_provider.dart';
import '../../widgets/ui/ui_kit.dart';
import '../misc/not_found_screen.dart';

const Map<AccaType, ({String label, String risk, Color accent})> _tierMeta = {
  AccaType.three: (label: '3-Odds', risk: 'Conservative', accent: AppColors.tier3),
  AccaType.five: (label: '5-Odds', risk: 'Medium risk', accent: AppColors.tier5),
  AccaType.ten: (label: '10-Odds', risk: 'High risk', accent: AppColors.tier10),
};

/// Ports `pages/AccumulatorTier.tsx` — hero combined-odds card with a
/// probability ring, then the ticket's legs as a LegList. Save/bookmark is
/// local-only UI state (bethero-src keeps this in AppContext memory; there's
/// no "saved tickets" persistence wired up in this app yet, matching
/// saved_tickets_screen.dart's documented limitation).
class AccumulatorDetailScreen extends ConsumerStatefulWidget {
  final String type;
  const AccumulatorDetailScreen({super.key, required this.type});

  @override
  ConsumerState<AccumulatorDetailScreen> createState() => _AccumulatorDetailScreenState();
}

class _AccumulatorDetailScreenState extends ConsumerState<AccumulatorDetailScreen> {
  bool _saved = false;

  @override
  Widget build(BuildContext context) {
    final accaType = AccaType.fromString(widget.type);
    final async = ref.watch(accumulatorByTypeProvider(accaType));
    final meta = _tierMeta[accaType]!;

    return async.when(
      data: (acca) {
        if (acca == null) return const NotFoundScreen();
        return _buildBody(context, acca, meta);
      },
      loading: () => Scaffold(
        backgroundColor: AppColors.base,
        appBar: ScreenHeader(title: '${meta.label} ticket'),
        body: const Center(child: CircularProgressIndicator(color: AppColors.tier3)),
      ),
      error: (e, _) => const NotFoundScreen(),
    );
  }

  Widget _buildBody(BuildContext context, AccumulatorModel acca, ({String label, String risk, Color accent}) meta) {
    // Market-implied probability from the combined decimal odds.
    final marketImplied = acca.totalOdds > 0 ? 1 / acca.totalOdds : 0.0;
    final probability = (acca.confidenceScore > 1 ? acca.confidenceScore / 100 : acca.confidenceScore);

    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: ScreenHeader(
        title: '${meta.label} ticket',
        subtitle: '${meta.risk} · ${acca.legs.length} legs',
        action: IconButton(
          onPressed: () {
            setState(() => _saved = !_saved);
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text(_saved ? '${meta.label} ticket saved' : 'Removed from saved tickets')),
            );
          },
          icon: Icon(_saved ? Icons.bookmark : Icons.bookmark_border, color: _saved ? AppColors.gold : AppColors.inkMuted),
        ),
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
                        OddsDisplay(odds: acca.totalOdds, size: OddsSize.hero),
                        const SizedBox(height: 8),
                        Text('${meta.label} · ${meta.risk}',
                            style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: meta.accent)),
                      ],
                    ),
                    ProbabilityRing(value: probability, color: meta.accent, size: 92, stroke: 7, label: 'Model'),
                  ],
                ),
                Container(
                  margin: const EdgeInsets.only(top: 18),
                  padding: const EdgeInsets.only(top: 14),
                  decoration: BoxDecoration(border: Border(top: BorderSide(color: Colors.white.withOpacity(0.06)))),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      RichText(
                        text: TextSpan(
                          style: const TextStyle(fontSize: 14, color: AppColors.ink),
                          children: [
                            TextSpan(
                              text: '${(probability * 100).toStringAsFixed(0)}% ',
                              style: AppTheme.numStyle(fontSize: 14, fontWeight: FontWeight.w800, color: AppColors.ink),
                            ),
                            const TextSpan(text: 'modelled chance of winning'),
                          ],
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text('Market-implied from the combined price: ${(marketImplied * 100).toStringAsFixed(1)}%',
                          style: AppTheme.numStyle(fontSize: 12, color: AppColors.inkMuted)),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          Text('${acca.legs.length} LEGS',
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.8, color: AppColors.inkMuted)),
          const SizedBox(height: 12),
          ...acca.legs.asMap().entries.map((e) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: LegRow(leg: e.value, accent: meta.accent, index: e.key),
              )),
          const ResponsibleFooter(),
        ],
      ),
    );
  }
}
