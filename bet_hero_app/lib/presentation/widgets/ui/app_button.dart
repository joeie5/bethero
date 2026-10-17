import 'package:flutter/material.dart';
import '../../../core/theme.dart';

enum AppButtonVariant { primary, ghost, outline }

/// Ports `Button.tsx` — pill button with primary/outline/ghost variants.
class AppButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final AppButtonVariant variant;
  final bool full;
  final Widget? icon;

  const AppButton({
    super.key,
    required this.label,
    this.onPressed,
    this.variant = AppButtonVariant.primary,
    this.full = false,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final disabled = onPressed == null;
    Widget button;
    final content = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (icon != null) ...[icon!, const SizedBox(width: 8)],
        Text(label, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
      ],
    );

    switch (variant) {
      case AppButtonVariant.primary:
        button = ElevatedButton(
          onPressed: onPressed,
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.ink,
            foregroundColor: AppColors.base,
            disabledBackgroundColor: AppColors.ink.withOpacity(0.4),
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
            shape: const StadiumBorder(),
          ),
          child: content,
        );
        break;
      case AppButtonVariant.outline:
        button = OutlinedButton(
          onPressed: onPressed,
          style: OutlinedButton.styleFrom(
            foregroundColor: AppColors.ink,
            backgroundColor: Colors.white.withOpacity(0.05),
            side: BorderSide(color: Colors.white.withOpacity(0.12)),
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
            shape: const StadiumBorder(),
          ),
          child: content,
        );
        break;
      case AppButtonVariant.ghost:
        button = TextButton(
          onPressed: onPressed,
          style: TextButton.styleFrom(
            foregroundColor: AppColors.inkMuted,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          ),
          child: content,
        );
        break;
    }

    final opacity = disabled ? 0.4 : 1.0;
    final sized = full ? SizedBox(width: double.infinity, child: button) : button;
    return Opacity(opacity: opacity, child: sized);
  }
}
