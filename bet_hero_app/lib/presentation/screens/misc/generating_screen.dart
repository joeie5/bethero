import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/Generating.tsx` — animated progress while "AI" builds today's tickets.
class GeneratingScreen extends StatefulWidget {
  const GeneratingScreen({super.key});

  @override
  State<GeneratingScreen> createState() => _GeneratingScreenState();
}

class _GeneratingScreenState extends State<GeneratingScreen> {
  static const _steps = [
    "Pulling today's fixtures across 7 sports",
    'Scoring 1X2, BTTS, totals, corners and spreads',
    'Ranking market edge per match',
    'Building the 3, 5 and 10-odds tickets',
  ];

  int _step = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 900), (_) {
      if (!mounted) return;
      setState(() => _step = (_step + 1).clamp(0, _steps.length - 1));
    });
    Future.delayed(const Duration(milliseconds: 4000), () {
      if (mounted) context.go('/home');
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      const LogoMark(size: 32),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Text("Analyzing today's fixtures across 7 sports…",
                            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(999),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 300),
                      curve: kSwiftCurve,
                      height: 4,
                      width: double.infinity,
                      color: Colors.white.withOpacity(0.07),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: FractionallySizedBox(
                          widthFactor: (_step + 1) / _steps.length,
                          child: Container(color: AppColors.tier3),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 28),
                  Column(
                    children: [
                      for (int i = 0; i < _steps.length; i++)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: Row(
                            children: [
                              Container(
                                width: 6,
                                height: 6,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: i < _step
                                      ? AppColors.win
                                      : i == _step
                                          ? AppColors.tier3
                                          : Colors.white.withOpacity(0.15),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Text(_steps[i],
                                    style: TextStyle(fontSize: 14, color: i <= _step ? AppColors.ink : AppColors.inkFaint)),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  const Text(
                    'Predictions are probabilistic, not guarantees. Bet responsibly.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 11, color: AppColors.inkFaint),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
