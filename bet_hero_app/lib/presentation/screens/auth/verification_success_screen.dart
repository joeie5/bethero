import 'dart:async';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/VerificationSuccess.tsx`.
class VerificationSuccessScreen extends StatefulWidget {
  const VerificationSuccessScreen({super.key});

  @override
  State<VerificationSuccessScreen> createState() => _VerificationSuccessScreenState();
}

class _VerificationSuccessScreenState extends State<VerificationSuccessScreen> {
  @override
  void initState() {
    super.initState();
    Future.delayed(const Duration(milliseconds: 2400), () {
      if (mounted) context.go('/generating');
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(shape: BoxShape.circle, color: AppColors.win.withOpacity(0.12)),
              alignment: Alignment.center,
              child: const Icon(Icons.check, size: 36, color: AppColors.win),
            ),
            const SizedBox(height: 28),
            const Text("You're all set", style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: AppColors.ink)),
            const SizedBox(height: 8),
            const Text('Your account is verified.', style: TextStyle(fontSize: 13, color: AppColors.inkMuted)),
            const SizedBox(height: 32),
            AppButton(label: 'Start predicting', onPressed: () => context.go('/generating')),
          ],
        ),
      ),
    );
  }
}
