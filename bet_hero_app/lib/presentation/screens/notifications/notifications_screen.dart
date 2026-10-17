import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../data/mock/bethero_mock_data.dart';
import '../../widgets/ui/ui_kit.dart';

const Map<String, ({IconData icon, Color color})> _kindMeta = {
  'ticket-ready': (icon: Icons.notifications_outlined, color: AppColors.tier3),
  'settled-won': (icon: Icons.emoji_events_outlined, color: AppColors.win),
  'settled-lost': (icon: Icons.cancel_outlined, color: AppColors.loss),
  'longshot': (icon: Icons.bolt_outlined, color: AppColors.gold),
  'odds-movement': (icon: Icons.trending_up, color: AppColors.tier10),
};

/// Ports `pages/Notifications.tsx` — grouped-by-day notification feed with
/// a "mark all read" action and a settings shortcut.
///
/// There is no notifications backend/provider wired up yet, so this screen
/// (like `SavedTicketsScreen`) seeds from `kMockNotifications` with
/// local-only read/unread state, mirroring bethero-src's in-memory
/// AppContext store.
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  late final Set<String> _read = {};

  int get _unreadCount => kMockNotifications.where((n) => n.unread && !_read.contains(n.id)).length;

  @override
  Widget build(BuildContext context) {
    final grouped = <String, List<MockNotification>>{};
    for (final n in kMockNotifications) {
      grouped.putIfAbsent(n.day, () => []).add(n);
    }

    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Notifications',
                        style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: AppColors.ink)),
                    const SizedBox(height: 4),
                    Text('$_unreadCount unread', style: AppTheme.numStyle(fontSize: 14, color: AppColors.inkMuted)),
                  ],
                ),
                Row(
                  children: [
                    if (_unreadCount > 0)
                      TextButton(
                        onPressed: () => setState(() => _read.addAll(kMockNotifications.map((n) => n.id))),
                        child: const Text('Mark all read',
                            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.tier3)),
                      ),
                    IconButton(
                      onPressed: () => context.push('/settings/notifications'),
                      icon: const Icon(Icons.settings_outlined, size: 18, color: AppColors.inkMuted),
                    ),
                  ],
                ),
              ],
            ),
            if (kMockNotifications.isEmpty)
              EmptyState(
                icon: Icons.notifications_none,
                title: 'Nothing yet today',
                body: "You'll hear from us when tickets are built and when they settle.",
                actionLabel: 'Back to home',
                onAction: () => context.go('/home'),
              )
            else
              ...grouped.entries.map((entry) {
                return Padding(
                  padding: const EdgeInsets.only(top: 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(entry.key.toUpperCase(),
                          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, letterSpacing: 0.8, color: AppColors.inkMuted)),
                      const SizedBox(height: 10),
                      ...entry.value.map((n) => _NotificationTile(
                            notification: n,
                            unread: n.unread && !_read.contains(n.id),
                            onTap: () {
                              setState(() => _read.add(n.id));
                              if (n.href != null) context.push(n.href!);
                            },
                          )),
                    ],
                  ),
                );
              }),
            const ResponsibleFooter(),
          ],
        ),
      ),
    );
  }
}

class _NotificationTile extends StatelessWidget {
  final MockNotification notification;
  final bool unread;
  final VoidCallback onTap;
  const _NotificationTile({required this.notification, required this.unread, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final meta = _kindMeta[notification.kind] ?? _kindMeta['ticket-ready']!;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: GlassCard(
        padding: EdgeInsets.zero,
        border: unread ? Border.all(color: Colors.white.withOpacity(0.14)) : null,
        onTap: onTap,
        child: Stack(
          children: [
            if (unread)
              Positioned(
                left: 0,
                top: 0,
                bottom: 0,
                child: Container(width: 2, color: meta.color),
              ),
            Padding(
              padding: const EdgeInsets.all(14),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(color: meta.color.withOpacity(0.12), borderRadius: BorderRadius.circular(10)),
                    child: Icon(meta.icon, size: 17, color: meta.color),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(notification.title,
                            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                        const SizedBox(height: 3),
                        Text(notification.body,
                            style: const TextStyle(fontSize: 12, height: 1.4, color: AppColors.inkMuted)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(notification.time, style: AppTheme.numStyle(fontSize: 11, color: AppColors.inkFaint)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
