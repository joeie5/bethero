import 'package:flutter/material.dart';
import '../../../core/theme.dart';

/// Ports `Toggle.tsx`.
class AppToggle extends StatelessWidget {
  final bool value;
  final ValueChanged<bool> onChanged;

  const AppToggle({super.key, required this.value, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => onChanged(!value),
      child: AnimatedContainer(
        duration: kSwiftDuration,
        curve: kSwiftCurve,
        width: 44,
        height: 24,
        padding: const EdgeInsets.all(3),
        decoration: BoxDecoration(
          color: value ? AppColors.tier3.withOpacity(0.3) : Colors.white.withOpacity(0.06),
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: value ? AppColors.tier3.withOpacity(0.5) : Colors.white.withOpacity(0.1)),
        ),
        child: AnimatedAlign(
          duration: kSwiftDuration,
          curve: kSwiftCurve,
          alignment: value ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            width: 18,
            height: 18,
            decoration: BoxDecoration(
              color: value ? AppColors.tier3 : Colors.white.withOpacity(0.4),
              shape: BoxShape.circle,
            ),
          ),
        ),
      ),
    );
  }
}
