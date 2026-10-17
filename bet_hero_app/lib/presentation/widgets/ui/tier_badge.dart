import 'package:flutter/material.dart';
import '../../../core/theme.dart';

class TierMeta {
  final String label;
  final String risk;
  final Color accent;
  const TierMeta(this.label, this.risk, this.accent);
}

const Map<String, TierMeta> kTierMeta = {
  '3': TierMeta('3-Odds', 'Conservative', AppColors.tier3),
  '5': TierMeta('5-Odds', 'Medium risk', AppColors.tier5),
  '10': TierMeta('10-Odds', 'High risk', AppColors.tier10),
};

/// Ports `TierBadge.tsx`.
class TierBadge extends StatelessWidget {
  final String tier;
  final bool small;
  final bool showRisk;
  const TierBadge({super.key, required this.tier, this.small = true, this.showRisk = false});

  @override
  Widget build(BuildContext context) {
    final meta = kTierMeta[tier] ?? kTierMeta['3']!;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: small ? 10 : 12, vertical: small ? 5 : 7),
      decoration: BoxDecoration(
        color: meta.accent.withOpacity(0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: meta.accent.withOpacity(0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(color: meta.accent, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            meta.label,
            style: TextStyle(color: meta.accent, fontSize: small ? 11 : 12, fontWeight: FontWeight.w700),
          ),
          if (showRisk) ...[
            Text(' · ', style: TextStyle(color: AppColors.inkMuted, fontSize: small ? 11 : 12)),
            Text(meta.risk, style: TextStyle(color: AppColors.inkMuted, fontSize: small ? 11 : 12, fontWeight: FontWeight.w500)),
          ],
        ],
      ),
    );
  }
}
