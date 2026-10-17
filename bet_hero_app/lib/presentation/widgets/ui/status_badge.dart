import 'package:flutter/material.dart';
import '../../../core/theme.dart';

enum AppStatus { won, lost, hit, miss, pending }

/// Ports `StatusBadge.tsx`.
class StatusBadge extends StatelessWidget {
  final AppStatus status;
  const StatusBadge({super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    late String label;
    late Color color;
    bool positive = false;
    switch (status) {
      case AppStatus.won:
        label = 'Won';
        color = AppColors.win;
        positive = true;
        break;
      case AppStatus.hit:
        label = 'Hit';
        color = AppColors.win;
        positive = true;
        break;
      case AppStatus.lost:
        label = 'Lost';
        color = AppColors.loss;
        break;
      case AppStatus.miss:
        label = 'Miss';
        color = AppColors.loss;
        break;
      case AppStatus.pending:
        label = 'Pending';
        color = AppColors.inkMuted;
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(status == AppStatus.pending ? 0.06 : 0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withOpacity(status == AppStatus.pending ? 0.14 : 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (status != AppStatus.pending) ...[
            Icon(positive ? Icons.check : Icons.close, size: 11, color: color),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}
