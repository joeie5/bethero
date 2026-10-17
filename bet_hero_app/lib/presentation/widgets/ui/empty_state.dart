import 'package:flutter/material.dart';
import '../../../core/theme.dart';
import 'glass_card.dart';
import 'app_button.dart';

/// Ports `EmptyState.tsx`.
class EmptyState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String body;
  final String? actionLabel;
  final VoidCallback? onAction;

  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.body,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 56),
      child: Column(
        children: [
          GlassCard(
            radius: AppRadius.xl2,
            padding: EdgeInsets.zero,
            child: SizedBox(
              width: 64,
              height: 64,
              child: Icon(icon, color: AppColors.inkMuted, size: 26),
            ),
          ),
          const SizedBox(height: 20),
          Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.ink)),
          const SizedBox(height: 8),
          Text(
            body,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 13, height: 1.5, color: AppColors.inkMuted),
          ),
          if (actionLabel != null) ...[
            const SizedBox(height: 24),
            AppButton(label: actionLabel!, variant: AppButtonVariant.outline, onPressed: onAction),
          ],
        ],
      ),
    );
  }
}
