import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/OfflineError.tsx`.
class OfflineErrorScreen extends StatefulWidget {
  const OfflineErrorScreen({super.key});

  @override
  State<OfflineErrorScreen> createState() => _OfflineErrorScreenState();
}

class _OfflineErrorScreenState extends State<OfflineErrorScreen> {
  bool _retrying = false;

  void _retry() {
    setState(() => _retrying = true);
    Future.delayed(const Duration(milliseconds: 900), () {
      if (!mounted) return;
      setState(() => _retrying = false);
      context.go('/home');
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      appBar: const ScreenHeader(title: 'Connection lost'),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: GlassCard(
          padding: const EdgeInsets.symmetric(vertical: 48, horizontal: 24),
          child: Column(
            children: [
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(color: Colors.white.withOpacity(0.05), borderRadius: BorderRadius.circular(18)),
                alignment: Alignment.center,
                child: const Icon(Icons.wifi_off, color: AppColors.inkMuted, size: 26),
              ),
              const SizedBox(height: 20),
              const Text("We can't reach the model right now",
                  textAlign: TextAlign.center, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppColors.ink)),
              const SizedBox(height: 8),
              const Text(
                'Your connection dropped or our prediction service is briefly unavailable. Nothing you saved is lost.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, height: 1.5, color: AppColors.inkMuted),
              ),
              const SizedBox(height: 24),
              AppButton(label: _retrying ? 'Retrying…' : 'Retry', onPressed: _retrying ? null : _retry),
            ],
          ),
        ),
      ),
    );
  }
}
