import 'package:flutter/material.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/NotificationSettings.tsx`. Toggle state is local-only (no
/// persistence provider exists yet for per-kind notification prefs).
class NotificationSettingsScreen extends StatefulWidget {
  const NotificationSettingsScreen({super.key});

  @override
  State<NotificationSettingsScreen> createState() => _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState extends State<NotificationSettingsScreen> {
  final Map<String, bool> _prefs = {
    'ticket-ready': true,
    'settled-won': true,
    'settled-lost': true,
    'longshot': true,
    'odds-movement': false,
  };

  static const _rows = [
    (kind: 'ticket-ready', title: 'New ticket ready', body: "When the day's 3, 5 and 10-odds tickets are built."),
    (kind: 'settled-won', title: 'Ticket settled — won', body: 'When one of your tracked tickets lands.'),
    (kind: 'settled-lost', title: 'Ticket settled — lost', body: 'The full record, including the misses.'),
    (kind: 'longshot', title: 'Longshot Best Bet', body: 'One alert a day for the standout high-odds pick.'),
    (kind: 'odds-movement', title: 'Odds movement alert', body: 'When a priced market moves enough to change its edge.'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: const ScreenHeader(title: 'Notifications', subtitle: 'Choose what you hear about'),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
        children: [
          GlassCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                for (int i = 0; i < _rows.length; i++)
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      border: Border(
                        bottom: BorderSide(color: i == _rows.length - 1 ? Colors.transparent : Colors.white.withOpacity(0.06)),
                      ),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(_rows[i].title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                              const SizedBox(height: 3),
                              Text(_rows[i].body, style: const TextStyle(fontSize: 12, height: 1.4, color: AppColors.inkMuted)),
                            ],
                          ),
                        ),
                        const SizedBox(width: 12),
                        AppToggle(
                          value: _prefs[_rows[i].kind] ?? false,
                          onChanged: (v) => setState(() => _prefs[_rows[i].kind] = v),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          const Text('We cap alerts at four a day. No promotional messages, ever.',
              style: TextStyle(fontSize: 11, height: 1.5, color: AppColors.inkFaint)),
        ],
      ),
    );
  }
}
