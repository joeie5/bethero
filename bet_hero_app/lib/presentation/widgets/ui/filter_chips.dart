import 'package:flutter/material.dart';
import '../../../core/theme.dart';

class ChipOption {
  final String id;
  final String label;
  final IconData? icon;
  const ChipOption({required this.id, required this.label, this.icon});
}

/// Ports `FilterChips.tsx`.
class FilterChips extends StatelessWidget {
  final List<ChipOption> options;
  final String value;
  final ValueChanged<String> onChanged;
  final Color? accent;

  const FilterChips({
    super.key,
    required this.options,
    required this.value,
    required this.onChanged,
    this.accent,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 36,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: options.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final opt = options[i];
          final active = opt.id == value;
          final activeColor = accent ?? AppColors.ink;
          return GestureDetector(
            onTap: () => onChanged(opt.id),
            child: AnimatedContainer(
              duration: kSwiftDuration,
              curve: kSwiftCurve,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: active ? activeColor : Colors.white.withOpacity(0.04),
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: active ? Colors.transparent : Colors.white.withOpacity(0.1)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (opt.icon != null) ...[
                    Icon(opt.icon, size: 14, color: active ? AppColors.base : AppColors.inkMuted),
                    const SizedBox(width: 6),
                  ],
                  Text(
                    opt.label,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: active ? AppColors.base : AppColors.inkMuted,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
