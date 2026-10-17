import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/SavedTickets.tsx`. There is no "saved tickets" persistence wired up
/// in this Flutter app yet (bethero-src keeps this in AppContext local state) — this
/// screen currently always renders the empty state.
class SavedTicketsScreen extends StatelessWidget {
  const SavedTicketsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: const ScreenHeader(title: 'Saved tickets', subtitle: '0 saved'),
      body: EmptyState(
        icon: Icons.bookmark_border,
        title: 'No saved tickets yet',
        body: 'Tap the bookmark icon on any ticket to keep it here for the day.',
        actionLabel: "See today's tickets",
        onAction: () => context.go('/home'),
      ),
    );
  }
}
