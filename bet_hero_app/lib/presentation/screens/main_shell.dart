import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme.dart';

/// Ports `components/AppShell.tsx` + `components/BottomTabBar.tsx` — 4-tab bar
/// (Home / Longshots / Results / Profile) matching the new design's route map.
class MainShell extends StatelessWidget {
  final Widget child;

  const MainShell({super.key, required this.child});

  static const _tabs = [
    (path: '/home', label: 'Home', icon: Icons.home_outlined, activeIcon: Icons.home),
    (path: '/longshots', label: 'Longshots', icon: Icons.bolt_outlined, activeIcon: Icons.bolt),
    (path: '/tiers', label: 'Tiers', icon: Icons.layers_outlined, activeIcon: Icons.layers),
    (path: '/results', label: 'Results', icon: Icons.trending_up_outlined, activeIcon: Icons.trending_up),
    (path: '/profile', label: 'Profile', icon: Icons.person_outline, activeIcon: Icons.person),
  ];

  int _indexFor(String location) {
    for (int i = 0; i < _tabs.length; i++) {
      if (location.startsWith(_tabs[i].path)) return i;
    }
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).uri.toString();
    final currentIndex = _indexFor(location);

    return Scaffold(
      backgroundColor: AppColors.base,
      body: child,
      bottomNavigationBar: ClipRect(
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
          child: Container(
            decoration: BoxDecoration(
              color: AppColors.base.withOpacity(0.85),
              border: Border(top: BorderSide(color: Colors.white.withOpacity(0.07))),
            ),
            child: SafeArea(
              top: false,
              child: Row(
                children: List.generate(_tabs.length, (i) {
                  final active = i == currentIndex;
                  final tab = _tabs[i];
                  return Expanded(
                    child: InkWell(
                      onTap: () => context.go(tab.path),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              height: 2,
                              width: 32,
                              margin: const EdgeInsets.only(bottom: 6),
                              color: active ? AppColors.tier3 : Colors.transparent,
                            ),
                            Icon(
                              active ? tab.activeIcon : tab.icon,
                              size: 22,
                              color: active ? AppColors.ink : AppColors.inkFaint,
                            ),
                            const SizedBox(height: 4),
                            Text(
                              tab.label,
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.w500,
                                color: active ? AppColors.ink : AppColors.inkFaint,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                }),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
