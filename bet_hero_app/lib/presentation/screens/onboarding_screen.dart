import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../core/theme.dart';
import '../widgets/ui/ui_kit.dart';

/// Ports `pages/Onboarding.tsx` — 3-slide swipeable intro (AI predictions,
/// smart accumulators, track results) with a progress-dot indicator.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingSlide {
  final String title;
  final String body;
  final Widget illustration;
  const _OnboardingSlide({required this.title, required this.body, required this.illustration});
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final PageController _pageController = PageController();
  int _index = 0;

  late final List<_OnboardingSlide> _slides = [
    _OnboardingSlide(
      title: 'AI-powered predictions',
      body:
          'Our models are trained on a decade of historical fixtures across seven sports, re-scoring every market as odds and team news move.',
      illustration: const _NeuralPitch(),
    ),
    _OnboardingSlide(
      title: 'Smart accumulators',
      body:
          'Three tickets a day — 3, 5 and 10 odds. Each leg is the single best-value market for that match, with a modelled win probability attached.',
      illustration: const _TierFan(),
    ),
    _OnboardingSlide(
      title: 'Track every result',
      body:
          'Every past ticket stays on the record, won or lost. You see the hit rate by tier, sport and market — not just the good days.',
      illustration: const _ResultsPreview(),
    ),
  ];

  bool get _isLast => _index == _slides.length - 1;

  void _next() {
    if (_isLast) {
      context.go('/onboarding/notifications');
    } else {
      _pageController.nextPage(duration: const Duration(milliseconds: 260), curve: Curves.easeOutCubic);
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      TextButton(
                        onPressed: () => context.go('/onboarding/notifications'),
                        child: const Text('Skip', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.inkMuted)),
                      ),
                    ],
                  ),
                  Expanded(
                    child: PageView.builder(
                      controller: _pageController,
                      itemCount: _slides.length,
                      onPageChanged: (i) => setState(() => _index = i),
                      itemBuilder: (context, i) {
                        final s = _slides[i];
                        return Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SizedBox(height: 208, child: Center(child: s.illustration)),
                            const SizedBox(height: 36),
                            Text(s.title,
                                style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, height: 1.15, color: AppColors.ink)),
                            const SizedBox(height: 12),
                            Text(s.body, style: const TextStyle(fontSize: 15, height: 1.5, color: AppColors.inkMuted)),
                          ],
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 20),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(_slides.length, (i) {
                      final active = i == _index;
                      return AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        curve: Curves.easeOut,
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        width: active ? 24 : 6,
                        height: 6,
                        decoration: BoxDecoration(
                          color: active ? AppColors.tier3 : Colors.white.withOpacity(0.2),
                          borderRadius: BorderRadius.circular(3),
                        ),
                      );
                    }),
                  ),
                  const SizedBox(height: 24),
                  AppButton(label: _isLast ? 'Get started' : 'Continue', full: true, onPressed: _next),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _NeuralPitch extends StatelessWidget {
  const _NeuralPitch();

  static const _nodes = [
    Offset(0.18, 0.30),
    Offset(0.18, 0.70),
    Offset(0.50, 0.20),
    Offset(0.50, 0.50),
    Offset(0.50, 0.80),
    Offset(0.82, 0.40),
    Offset(0.82, 0.62),
  ];

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      radius: AppRadius.xl2,
      padding: EdgeInsets.zero,
      child: SizedBox(
        height: 208,
        width: double.infinity,
        child: Stack(
          children: [
            Positioned.fill(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.white.withOpacity(0.1)),
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
            Positioned.fill(
              child: CustomPaint(painter: _NeuralPainter()),
            ),
          ],
        ),
      ),
    );
  }
}

class _NeuralPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final linePaint = Paint()
      ..color = const Color(0xFF3FC7D8).withOpacity(0.28)
      ..strokeWidth = 1;
    final nodes = _NeuralPitch._nodes.map((n) => Offset(n.dx * size.width, n.dy * size.height)).toList();
    for (var a = 0; a < 2; a++) {
      for (var b = 2; b < 5; b++) {
        canvas.drawLine(nodes[a], nodes[b], linePaint);
      }
    }
    for (var a = 2; a < 5; a++) {
      for (var b = 5; b < nodes.length; b++) {
        canvas.drawLine(nodes[a], nodes[b], linePaint);
      }
    }
    final dotPaint = Paint()..color = AppColors.tier3;
    for (final n in nodes) {
      canvas.drawCircle(n, 5, dotPaint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _TierFan extends StatelessWidget {
  const _TierFan();

  @override
  Widget build(BuildContext context) {
    final cards = [
      (label: '3-Odds', value: '2.98', color: const Color(0xFF3FC7D8), rotate: -0.14, x: -64.0),
      (label: '5-Odds', value: '5.04', color: const Color(0xFFF0B24B), rotate: 0.0, x: 0.0),
      (label: '10-Odds', value: '10.15', color: const Color(0xFFB47CFF), rotate: 0.14, x: 64.0),
    ];
    return SizedBox(
      height: 208,
      width: double.infinity,
      child: Stack(
        alignment: Alignment.center,
        children: cards.map((c) {
          return Transform.translate(
            offset: Offset(c.x, 0),
            child: Transform.rotate(
              angle: c.rotate,
              child: Container(
                width: 112,
                height: 144,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.03),
                  borderRadius: BorderRadius.circular(AppRadius.xl2),
                  border: Border.all(color: c.color.withOpacity(0.27)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(c.label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: c.color)),
                    Text(c.value, style: AppTheme.numStyle(fontSize: 24, fontWeight: FontWeight.w800, color: AppColors.ink)),
                    Container(width: 32, height: 4, decoration: BoxDecoration(color: c.color, borderRadius: BorderRadius.circular(2))),
                  ],
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _ResultsPreview extends StatelessWidget {
  const _ResultsPreview();

  @override
  Widget build(BuildContext context) {
    final rows = [
      (tier: '3-Odds', odds: '3.14', won: true),
      (tier: '5-Odds', odds: '5.22', won: false),
      (tier: '10-Odds', odds: '9.86', won: true),
    ];
    return Column(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: rows.map((r) {
        return Padding(
          padding: EdgeInsets.zero,
          child: GlassCard(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(r.tier, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                    Text('15 Aug · 3 legs', style: AppTheme.numStyle(fontSize: 11, color: AppColors.inkFaint)),
                  ],
                ),
                Row(
                  children: [
                    Text(r.odds, style: AppTheme.numStyle(fontSize: 18, fontWeight: FontWeight.w700, color: AppColors.ink)),
                    const SizedBox(width: 12),
                    Container(
                      width: 28,
                      height: 28,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: (r.won ? AppColors.win : AppColors.loss).withOpacity(0.15),
                      ),
                      child: Icon(r.won ? Icons.check : Icons.close, size: 16, color: r.won ? AppColors.win : AppColors.loss),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}
