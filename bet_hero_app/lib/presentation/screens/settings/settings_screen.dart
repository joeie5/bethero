import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:go_router/go_router.dart';
import '../../../core/di.dart';
import '../../../core/theme.dart';
import '../../../data/mock/bethero_mock_data.dart';
import '../../widgets/ui/ui_kit.dart';

final _oddsFormatProvider = StateProvider<String>((ref) => 'decimal');
final _preferredSportsProvider = StateProvider<Set<String>>((ref) => {'football'});

/// Ports `pages/Settings.tsx` — Notifications / Preferred sports / Display /
/// About / Prototype-states sections. Odds format + preferred sports are
/// local UI state only (mirrors bethero-src's in-memory AppContext — there is
/// no per-user preferences table to persist these to yet).
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final oddsFormat = ref.watch(_oddsFormatProvider);
    final preferredSports = ref.watch(_preferredSportsProvider);
    final unreadCount = kMockNotifications.where((n) => n.unread).length;

    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: const ScreenHeader(title: 'Settings', back: false),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
        children: [
          _Section(
            title: 'Notifications',
            child: GlassCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  _NavRow(
                    icon: Icons.notifications_none,
                    iconColor: AppColors.tier3,
                    title: 'Alerts',
                    subtitle: unreadCount > 0 ? '$unreadCount unread updates' : 'View your latest updates',
                    onTap: () => context.push('/settings/alerts'),
                  ),
                  const Divider(height: 1, color: Colors.white12),
                  _NavRow(
                    title: 'Notification preferences',
                    subtitle: 'Choose which alerts you receive',
                    onTap: () => context.push('/settings/notifications'),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          _Section(
            title: 'Preferred sports',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: kMockSports.map((s) {
                    final active = preferredSports.contains(s.id);
                    return GestureDetector(
                      onTap: () {
                        final next = {...preferredSports};
                        active ? next.remove(s.id) : next.add(s.id);
                        ref.read(_preferredSportsProvider.notifier).state = next;
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                        decoration: BoxDecoration(
                          color: active ? AppColors.tier3.withOpacity(0.12) : Colors.white.withOpacity(0.04),
                          border: Border.all(color: active ? AppColors.tier3.withOpacity(0.5) : Colors.white.withOpacity(0.1)),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(s.name,
                            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: active ? AppColors.tier3 : AppColors.inkMuted)),
                      ),
                    );
                  }).toList(),
                ),
                const SizedBox(height: 8),
                const Text('Preferred sports are surfaced first on Home and in Longshot Daily.',
                    style: TextStyle(fontSize: 11, color: AppColors.inkFaint)),
              ],
            ),
          ),
          const SizedBox(height: 24),
          _Section(
            title: 'Display',
            child: GlassCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Odds format', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                            Text(oddsFormat == 'decimal' ? '1.85' : '17/20',
                                style: AppTheme.numStyle(fontSize: 12, color: AppColors.inkMuted)),
                          ],
                        ),
                        Container(
                          padding: const EdgeInsets.all(2),
                          decoration: BoxDecoration(
                            border: Border.all(color: Colors.white.withOpacity(0.1)),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Row(
                            children: ['decimal', 'fractional'].map((f) {
                              final active = oddsFormat == f;
                              return GestureDetector(
                                onTap: () => ref.read(_oddsFormatProvider.notifier).state = f,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                  decoration: BoxDecoration(
                                    color: active ? AppColors.ink : Colors.transparent,
                                    borderRadius: BorderRadius.circular(999),
                                  ),
                                  child: Text(f[0].toUpperCase() + f.substring(1),
                                      style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: active ? AppColors.base : AppColors.inkMuted)),
                                ),
                              );
                            }).toList(),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Divider(height: 1, color: Colors.white12),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Dark theme', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                            Text("Light mode isn't available yet", style: TextStyle(fontSize: 12, color: AppColors.inkMuted)),
                          ],
                        ),
                        AppToggle(
                          value: true,
                          onChanged: (_) => ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('BetHero is dark-only for now')),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          _Section(
            title: 'About',
            child: GlassCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  _NavRow(title: 'How our AI works', onTap: () => context.push('/how-it-works')),
                  const Divider(height: 1, color: Colors.white12),
                  _NavRow(
                    title: 'Responsible gambling resources',
                    subtitle: 'Support, limits and self-exclusion tools',
                    external: true,
                    onTap: () => ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Opens begambleaware.org')),
                    ),
                  ),
                  const Divider(height: 1, color: Colors.white12),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: const [
                        Text('App version', style: TextStyle(fontSize: 14, color: AppColors.inkMuted)),
                        Text('2.4.1 (build 318)', style: TextStyle(fontSize: 14, color: AppColors.inkFaint)),
                      ],
                    ),
                  ),
                  const Divider(height: 1, color: Colors.white12),
                  _NavRow(
                    title: 'Sign out',
                    destructive: true,
                    onTap: () async {
                      await ref.read(authServiceProvider).signOut();
                      if (context.mounted) context.go('/onboarding');
                    },
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          _Section(
            title: 'Prototype states',
            child: GlassCard(
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  _NavRow(title: 'Generating predictions', subtitle: 'Full-screen build state', onTap: () => context.push('/generating')),
                  const Divider(height: 1, color: Colors.white12),
                  _NavRow(title: 'Connection lost', subtitle: 'Error / offline state', onTap: () => context.push('/offline')),
                  const Divider(height: 1, color: Colors.white12),
                  _NavRow(title: 'Removed fixture', subtitle: 'Postponed or unavailable', onTap: () => context.push('/404')),
                  const Divider(height: 1, color: Colors.white12),
                  _NavRow(title: 'Splash & onboarding', subtitle: 'Replay the first-run flow', onTap: () => context.go('/')),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          const ResponsibleFooter(),
        ],
      ),
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final Widget child;
  const _Section({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title.toUpperCase(),
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted)),
        const SizedBox(height: 12),
        child,
      ],
    );
  }
}

class _NavRow extends StatelessWidget {
  final IconData? icon;
  final Color? iconColor;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;
  final bool external;
  final bool destructive;

  const _NavRow({
    this.icon,
    this.iconColor,
    required this.title,
    this.subtitle,
    required this.onTap,
    this.external = false,
    this.destructive = false,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            if (icon != null) ...[
              Container(
                width: 36,
                height: 36,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: (iconColor ?? AppColors.tier3).withOpacity(0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, size: 16, color: iconColor ?? AppColors.tier3),
              ),
              const SizedBox(width: 12),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: TextStyle(
                          fontSize: 14, fontWeight: FontWeight.w600, color: destructive ? AppColors.loss : AppColors.ink)),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(subtitle!, style: const TextStyle(fontSize: 12, color: AppColors.inkMuted)),
                  ],
                ],
              ),
            ),
            Icon(external ? Icons.open_in_new : Icons.chevron_right, size: 16, color: AppColors.inkFaint),
          ],
        ),
      ),
    );
  }
}
