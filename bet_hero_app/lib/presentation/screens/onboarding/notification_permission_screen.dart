import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/NotificationPermission.tsx`.
class NotificationPermissionScreen extends StatelessWidget {
  const NotificationPermissionScreen({super.key});

  static const _reasons = [
    (icon: Icons.access_time, title: 'New ticket ready', body: 'Each morning when the three tiers finish building.'),
    (icon: Icons.emoji_events_outlined, title: 'Results settled', body: 'The moment a ticket is graded — won or lost.'),
    (icon: Icons.check_circle_outline, title: 'Longshot Best Bet', body: 'One alert a day for the standout high-odds pick.'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: GlassCard(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 48,
                      height: 48,
                      decoration: BoxDecoration(color: AppColors.tier3.withOpacity(0.12), borderRadius: BorderRadius.circular(14)),
                      alignment: Alignment.center,
                      child: const Icon(Icons.notifications_none, color: AppColors.tier3, size: 22),
                    ),
                    const SizedBox(height: 20),
                    const Text('Know the moment predictions land',
                        style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: AppColors.ink)),
                    const SizedBox(height: 8),
                    const Text(
                      "Three alerts a day at most. No hype, no promotions — just the model's output and the results.",
                      style: TextStyle(fontSize: 13, height: 1.5, color: AppColors.inkMuted),
                    ),
                    const SizedBox(height: 22),
                    ..._reasons.map((r) => Padding(
                          padding: const EdgeInsets.only(bottom: 14),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Icon(r.icon, size: 16, color: AppColors.inkMuted),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(r.title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.ink)),
                                    Text(r.body, style: const TextStyle(fontSize: 11, height: 1.4, color: AppColors.inkMuted)),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        )),
                    const SizedBox(height: 8),
                    AppButton(label: 'Enable notifications', full: true, onPressed: () => context.go('/auth/username')),
                    const SizedBox(height: 8),
                    AppButton(label: 'Maybe later', full: true, variant: AppButtonVariant.ghost, onPressed: () => context.go('/auth/username')),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
