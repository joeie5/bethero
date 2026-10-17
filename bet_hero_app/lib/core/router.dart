import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../presentation/screens/splash_screen.dart';
import '../presentation/screens/onboarding_screen.dart';
import '../presentation/screens/onboarding/notification_permission_screen.dart';
import '../presentation/screens/auth/username_entry_screen.dart';
import '../presentation/screens/auth/code_entry_screen.dart';
import '../presentation/screens/auth/verification_success_screen.dart';
import '../presentation/screens/misc/generating_screen.dart';
import '../presentation/screens/misc/offline_error_screen.dart';
import '../presentation/screens/misc/not_found_screen.dart';
import '../presentation/screens/main_shell.dart';
import '../presentation/screens/home/dashboard_screen.dart';
import '../presentation/screens/sports/sport_hub_screen.dart';
import '../presentation/screens/accumulators/accumulator_detail_screen.dart';
import '../presentation/screens/longshots/longshots_screen.dart';
import '../presentation/screens/tiers/tier_picks_screen.dart';
import '../presentation/screens/results/results_screen.dart';
import '../presentation/screens/results/ticket_result_screen.dart';
import '../presentation/screens/stats/stats_screen.dart';
import '../presentation/screens/fixtures/fixtures_screen.dart';
import '../presentation/screens/fixtures/fixture_detail_screen.dart';
import '../presentation/screens/notifications/notifications_screen.dart';
import '../presentation/screens/settings/settings_screen.dart';
import '../presentation/screens/settings/notification_settings_screen.dart';
import '../presentation/screens/profile/profile_screen.dart';
import '../presentation/screens/saved/saved_tickets_screen.dart';
import '../presentation/screens/how_it_works/how_ai_works_screen.dart';

final GlobalKey<NavigatorState> _rootNavigatorKey = GlobalKey<NavigatorState>();
final GlobalKey<NavigatorState> _shellNavigatorKey = GlobalKey<NavigatorState>();

/// Route map ported from bethero-src/App.tsx (26 screens). Standalone routes
/// (splash / onboarding / auth / generating) live outside the AppShell; the
/// rest are nested under the bottom-tab ShellRoute.
final AppRouter = GoRouter(
  initialLocation: '/',
  navigatorKey: _rootNavigatorKey,
  routes: [
    GoRoute(path: '/', builder: (context, state) => const SplashScreen()),
    // Legacy alias kept for any existing deep links / bookmarks.
    GoRoute(path: '/splash', builder: (context, state) => const SplashScreen()),

    GoRoute(path: '/onboarding', builder: (context, state) => const OnboardingScreen()),
    GoRoute(
      path: '/onboarding/notifications',
      builder: (context, state) => const NotificationPermissionScreen(),
    ),

    GoRoute(path: '/auth/username', builder: (context, state) => const UsernameEntryScreen()),
    GoRoute(path: '/auth/code', builder: (context, state) => const CodeEntryScreen()),
    GoRoute(path: '/auth/success', builder: (context, state) => const VerificationSuccessScreen()),

    GoRoute(path: '/generating', builder: (context, state) => const GeneratingScreen()),
    GoRoute(path: '/offline', builder: (context, state) => const OfflineErrorScreen()),

    ShellRoute(
      navigatorKey: _shellNavigatorKey,
      builder: (context, state, child) => MainShell(child: child),
      routes: [
        GoRoute(path: '/home', builder: (context, state) => const DashboardScreen()),
        GoRoute(path: '/sports', builder: (context, state) => const SportHubScreen()),
        GoRoute(
          path: '/sports/:sportId',
          builder: (context, state) => FixturesScreen(initialSport: state.pathParameters['sportId']),
        ),
        GoRoute(
          path: '/fixture/:fixtureId',
          builder: (context, state) => FixtureDetailScreen(id: state.pathParameters['fixtureId'] ?? ''),
        ),
        GoRoute(
          path: '/ticket/:tier',
          builder: (context, state) {
            final tier = state.pathParameters['tier'] ?? '10';
            final type = tier.endsWith('odds') ? tier : '${tier}odds';
            return AccumulatorDetailScreen(type: type);
          },
        ),
        GoRoute(path: '/longshots', builder: (context, state) => const LongshotsScreen()),
        GoRoute(path: '/tiers', builder: (context, state) => const TierPicksScreen()),
        GoRoute(path: '/results', builder: (context, state) => const ResultsScreen()),
        GoRoute(
          path: '/results/:ticketId',
          builder: (context, state) => TicketResultScreen(ticketId: state.pathParameters['ticketId'] ?? ''),
        ),
        GoRoute(path: '/performance', builder: (context, state) => const StatsScreen()),
        GoRoute(path: '/notifications', builder: (context, state) => const NotificationsScreen()),
        GoRoute(path: '/settings', builder: (context, state) => const SettingsScreen()),
        // /settings/alerts reuses Notifications, matching bethero-src/App.tsx.
        GoRoute(path: '/settings/alerts', builder: (context, state) => const NotificationsScreen()),
        GoRoute(path: '/settings/notifications', builder: (context, state) => const NotificationSettingsScreen()),
        GoRoute(path: '/profile', builder: (context, state) => const ProfileScreen()),
        GoRoute(path: '/saved', builder: (context, state) => const SavedTicketsScreen()),
        GoRoute(path: '/how-it-works', builder: (context, state) => const HowAIWorksScreen()),
        GoRoute(path: '/404', builder: (context, state) => const NotFoundScreen()),

        // Legacy aliases kept so any existing bookmarks/deep links to the
        // pre-redesign paths keep working.
        GoRoute(path: '/home/accumulators', builder: (context, state) => const DashboardScreen()),
        GoRoute(path: '/home/fixtures', builder: (context, state) => const FixturesScreen()),
        GoRoute(path: '/home/results', builder: (context, state) => const ResultsScreen()),
        GoRoute(path: '/home/stats', builder: (context, state) => const StatsScreen()),
      ],
    ),
  ],
  errorBuilder: (context, state) => const NotFoundScreen(),
);
