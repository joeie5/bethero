import 'package:flutter/material.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/HowAIWorks.tsx` — static explainer copy, no data dependency.
class HowAIWorksScreen extends StatelessWidget {
  const HowAIWorksScreen({super.key});

  static const _steps = [
    (
      title: 'Historical data',
      body:
          'Ten seasons of fixtures across seven sports — results, shot and possession data, line-ups, travel, rest days, injuries and closing prices. Roughly 1.4 million matches.'
    ),
    (
      title: 'The model',
      body:
          'A gradient-boosted ensemble produces a probability for every outcome in every market we cover: 1X2, BTTS, goal and corner totals, spreads, moneylines and match winners. It is retrained weekly and recalibrated nightly against how its own past forecasts performed.'
    ),
    (
      title: 'Market selection',
      body:
          'For each fixture we compare the model probability against the probability implied by the market price. The difference is the edge. Only one market per match — the one with the highest calibrated edge — can enter a ticket.'
    ),
    (
      title: 'Tier building',
      body:
          'Legs are combined so the product of their odds lands near 3, 5 or 10. The aggregate win probability shown on each ticket is the product of the individual leg probabilities, which is why a 10-odds ticket reads far lower than a 3-odds one.'
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: const ScreenHeader(title: 'How our AI works', subtitle: 'Transparency, not marketing'),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
        children: [
          const Text(
            'BetHero does not know what will happen. It estimates how likely things are, and shows you where those estimates disagree with the market. Here is the whole pipeline.',
            style: TextStyle(fontSize: 15, height: 1.5, color: AppColors.inkMuted),
          ),
          const SizedBox(height: 20),
          for (int i = 0; i < _steps.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: GlassCard(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 28,
                      height: 28,
                      decoration: BoxDecoration(color: AppColors.tier3.withOpacity(0.12), borderRadius: BorderRadius.circular(8)),
                      alignment: Alignment.center,
                      child: Text('${i + 1}', style: AppTheme.numStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.tier3)),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(_steps[i].title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                          const SizedBox(height: 6),
                          Text(_steps[i].body, style: const TextStyle(fontSize: 13, height: 1.5, color: AppColors.inkMuted)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          GlassCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                Text('What the numbers mean', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                SizedBox(height: 10),
                _DefEntry('Model probability', 'Our estimated chance that a single outcome happens.'),
                SizedBox(height: 10),
                _DefEntry('Edge',
                    'Model probability minus the probability implied by the price, in percentage points. Positive edge means we think the market is too long — it does not mean the bet will win.'),
                SizedBox(height: 10),
                _DefEntry('Aggregate win probability', "The product of every leg's probability. Adding legs always lowers it."),
              ],
            ),
          ),
          const SizedBox(height: 10),
          GlassCard(
            border: Border.all(color: AppColors.loss.withOpacity(0.25)),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Where we get it wrong', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                SizedBox(height: 8),
                Text(
                  'The model is weakest on low-sample competitions, in-season roster upheaval, and cricket, where our hit rate sits at 44%. We publish every settled ticket, including the losing ones, on the Performance screen.',
                  style: TextStyle(fontSize: 13, height: 1.5, color: AppColors.inkMuted),
                ),
              ],
            ),
          ),
          const ResponsibleFooter(),
        ],
      ),
    );
  }
}

class _DefEntry extends StatelessWidget {
  final String term;
  final String def;
  const _DefEntry(this.term, this.def);

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(term, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.inkMuted)),
        Text(def, style: const TextStyle(fontSize: 13, height: 1.4, color: AppColors.inkMuted)),
      ],
    );
  }
}
