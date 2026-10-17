import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/NotFound.tsx`.
class NotFoundScreen extends StatelessWidget {
  const NotFoundScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: const ScreenHeader(title: 'Not available'),
      body: EmptyState(
        icon: Icons.event_busy,
        title: 'This fixture is no longer available',
        body: "It was postponed or removed from today's card, so the model pulled its predictions. Everything else is unaffected.",
        actionLabel: "Back to today's tickets",
        onAction: () => context.go('/home'),
      ),
    );
  }
}
