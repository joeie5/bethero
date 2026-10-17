import 'package:flutter/material.dart';
import '../../../core/theme.dart';
import 'glass_card.dart';

/// Ports `StatCard.tsx`.
class StatCard extends StatelessWidget {
  final String label;
  final String value;
  final String? caption;
  final Color? accent;

  const StatCard({super.key, required this.label, required this.value, this.caption, this.accent});

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label.toUpperCase(),
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.6,
              color: AppColors.inkFaint,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: AppTheme.numStyle(fontSize: 24, fontWeight: FontWeight.w800, color: accent ?? AppColors.ink),
          ),
          if (caption != null) ...[
            const SizedBox(height: 4),
            Text(caption!, style: const TextStyle(fontSize: 12, color: AppColors.inkMuted)),
          ],
        ],
      ),
    );
  }
}
