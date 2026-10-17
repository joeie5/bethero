import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../core/di.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/Profile.tsx`. Overall performance stats are placeholder values —
/// wire to a real "overall performance" endpoint when available (see
/// bethero-src/data/performance.ts for the shape used by the design).
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  static const _links = [
    (icon: Icons.settings_outlined, label: 'Settings', body: 'Sports, odds format, theme', to: '/settings'),
    (icon: Icons.bookmark_outline, label: 'Saved tickets', body: 'Tickets you bookmarked', to: '/saved'),
    (icon: Icons.memory_outlined, label: 'How our AI works', body: 'The prediction pipeline, in plain language', to: '/how-it-works'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final username = user?.email?.split('@').first ?? 'Guest';

    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
          children: [
            Row(
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white.withOpacity(0.1)),
                    color: Colors.white.withOpacity(0.05),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    username.length >= 2 ? username.substring(0, 2).toUpperCase() : username.toUpperCase(),
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.ink),
                  ),
                ),
                const SizedBox(width: 16),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(username, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AppColors.ink)),
                    const Text('Member since Aug 2026', style: TextStyle(fontSize: 12, color: AppColors.inkMuted)),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 22),
            const Row(
              children: [
                Expanded(child: StatCard(label: 'Tracked', value: '128', caption: 'tickets')),
                SizedBox(width: 10),
                Expanded(child: StatCard(label: 'Hit rate', value: '61.4%', caption: '90 days')),
                SizedBox(width: 10),
                Expanded(child: StatCard(label: 'Saved', value: '3', caption: 'tickets')),
              ],
            ),
            const SizedBox(height: 22),
            ..._links.map((l) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: GlassCard(
                    onTap: () => context.push(l.to),
                    child: Row(
                      children: [
                        Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(color: Colors.white.withOpacity(0.05), borderRadius: BorderRadius.circular(10)),
                          alignment: Alignment.center,
                          child: Icon(l.icon, size: 18, color: AppColors.inkMuted),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(l.label, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                              Text(l.body, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: AppColors.inkMuted)),
                            ],
                          ),
                        ),
                        const Icon(Icons.chevron_right, size: 18, color: AppColors.inkFaint),
                      ],
                    ),
                  ),
                )),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () async {
                await ref.read(authServiceProvider).signOut();
                if (context.mounted) context.go('/onboarding');
              },
              child: const Text('Sign out'),
            ),
            const ResponsibleFooter(),
          ],
        ),
      ),
    );
  }
}
