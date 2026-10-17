import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../../data/mock/bethero_mock_data.dart';
import '../../widgets/common/sport_icon.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/SportHub.tsx`. Fixture counts are mock data (bethero-src/data/sports.ts) —
/// there is no backend endpoint yet for per-sport fixture counts.
class SportHubScreen extends StatelessWidget {
  const SportHubScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: const ScreenHeader(title: 'Sports', subtitle: 'Fixtures priced by the model today'),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
        children: [
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: kMockSports.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              childAspectRatio: 1.4,
            ),
            itemBuilder: (context, i) {
              final s = kMockSports[i];
              return GlassCard(
                onTap: () => context.push('/sports/${s.id}'),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.05),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      alignment: Alignment.center,
                      child: SportIcon(sportSlug: s.id, size: 20, color: AppColors.tier3),
                    ),
                    const Spacer(),
                    Text(s.name, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                    const SizedBox(height: 2),
                    Text('${s.fixtureCount} fixtures',
                        style: AppTheme.numStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.inkFaint)),
                  ],
                ),
              );
            },
          ),
          const ResponsibleFooter(),
        ],
      ),
    );
  }
}
