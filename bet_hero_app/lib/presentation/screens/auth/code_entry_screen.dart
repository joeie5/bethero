import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/CodeEntry.tsx`. No real OTP backend is wired (phone auth is
/// disabled on the Supabase project) — the verification code is hardcoded
/// to "000000" as a placeholder gate until real OTP/backend auth is added.
class CodeEntryScreen extends StatefulWidget {
  const CodeEntryScreen({super.key});

  @override
  State<CodeEntryScreen> createState() => _CodeEntryScreenState();
}

class _CodeEntryScreenState extends State<CodeEntryScreen> {
  static const _length = 6;
  static const _placeholderCode = '000000';
  final _digits = List<String>.filled(_length, '0');
  late final _controllers = List.generate(_length, (i) => TextEditingController(text: '0'));
  final _focusNodes = List.generate(_length, (_) => FocusNode());
  int _seconds = 42;
  Timer? _timer;
  String? _error;

  @override
  void initState() {
    super.initState();
    _startTimer();
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      if (_seconds <= 0) return;
      setState(() => _seconds--);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    for (final c in _controllers) {
      c.dispose();
    }
    for (final f in _focusNodes) {
      f.dispose();
    }
    super.dispose();
  }

  bool get _complete => _digits.every((d) => d.isNotEmpty);
  String get _entered => _digits.join();

  void _onVerify() {
    if (_entered == _placeholderCode) {
      context.push('/auth/success');
    } else {
      setState(() => _error = 'Incorrect code. Use 000000 (placeholder — real OTP not wired yet).');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Enter your code',
                      style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: AppColors.ink)),
                  const SizedBox(height: 8),
                  const Text(
                    'Enter the code we sent to keep your account secure. It expires in 10 minutes.\n(Placeholder auth: use 000000 — real OTP delivery is not wired up yet.)',
                    style: TextStyle(fontSize: 13, height: 1.5, color: AppColors.inkMuted),
                  ),
                  const SizedBox(height: 28),
                  Row(
                    children: List.generate(_length, (i) {
                      return Expanded(
                        child: Padding(
                          padding: EdgeInsets.only(right: i == _length - 1 ? 0 : 8),
                          child: SizedBox(
                            height: 56,
                            child: TextField(
                              controller: _controllers[i],
                              focusNode: _focusNodes[i],
                              autofocus: i == 0,
                              textAlign: TextAlign.center,
                              keyboardType: TextInputType.number,
                              maxLength: 1,
                              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                              style: AppTheme.numStyle(fontSize: 22, fontWeight: FontWeight.w700),
                              decoration: InputDecoration(
                                counterText: '',
                                filled: true,
                                fillColor: Colors.white.withOpacity(0.03),
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(AppRadius.xl),
                                  borderSide: BorderSide(color: _digits[i].isNotEmpty ? AppColors.tier3.withOpacity(0.6) : Colors.white24),
                                ),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(AppRadius.xl),
                                  borderSide: BorderSide(color: _digits[i].isNotEmpty ? AppColors.tier3.withOpacity(0.6) : Colors.white24),
                                ),
                              ),
                              onChanged: (v) {
                                setState(() {
                                  _digits[i] = v;
                                  _error = null;
                                });
                                if (v.isNotEmpty && i < _length - 1) {
                                  _focusNodes[i + 1].requestFocus();
                                } else if (v.isEmpty && i > 0) {
                                  _focusNodes[i - 1].requestFocus();
                                }
                              },
                            ),
                          ),
                        ),
                      );
                    }),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        _seconds > 0 ? 'Resend available in 0:${_seconds.toString().padLeft(2, '0')}' : 'Code expired',
                        style: AppTheme.numStyle(fontSize: 12, fontWeight: FontWeight.w500, color: AppColors.inkFaint),
                      ),
                      GestureDetector(
                        onTap: _seconds > 0
                            ? null
                            : () {
                                setState(() => _seconds = 42);
                                _startTimer();
                              },
                        child: Opacity(
                          opacity: _seconds > 0 ? 0.4 : 1,
                          child: const Text('Resend code', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.tier3)),
                        ),
                      ),
                    ],
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: const TextStyle(fontSize: 12, color: AppColors.loss)),
                  ],
                  const SizedBox(height: 24),
                  AppButton(label: 'Verify', full: true, onPressed: _complete ? _onVerify : null),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
