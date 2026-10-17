import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/theme.dart';
import '../../widgets/ui/ui_kit.dart';

/// Ports `pages/UsernameEntry.tsx` — the app's one and only auth entry point
/// (the legacy Supabase email/password login_screen.dart / register_screen.dart
/// have been removed from routing). bethero-src's flow is passwordless: pick a
/// username, get sent a verification code, done. Phone auth is disabled on the
/// live Supabase project (confirmed via /auth/v1/settings), so this is
/// deliberately NOT wired to signInWithOtp/verifyOTP — the paired
/// code_entry_screen.dart gates on a hardcoded placeholder code ("000000")
/// instead of a real OTP until phone auth is enabled and wired up.
class UsernameEntryScreen extends StatefulWidget {
  const UsernameEntryScreen({super.key});

  @override
  State<UsernameEntryScreen> createState() => _UsernameEntryScreenState();
}

class _UsernameEntryScreenState extends State<UsernameEntryScreen> {
  final _controller = TextEditingController();
  String? _error;

  void _submit() {
    final value = _controller.text.trim();
    if (value.length < 3) {
      setState(() => _error = 'Usernames need at least 3 characters.');
      return;
    }
    context.push('/auth/code');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.base,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const LogoMark(size: 36),
              Expanded(
                child: Center(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text('Choose a username',
                          style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: AppColors.ink)),
                      const SizedBox(height: 8),
                      const Text(
                        "This is how you'll be identified in the app. There's no password and no login wall — you can start using BetHero straight away.",
                        style: TextStyle(fontSize: 13, height: 1.5, color: AppColors.inkMuted),
                      ),
                      const SizedBox(height: 32),
                      TextField(
                        controller: _controller,
                        autofocus: true,
                        onChanged: (_) => setState(() => _error = null),
                        style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w600, color: AppColors.ink),
                        decoration: InputDecoration(
                          hintText: 'e.g. marcus',
                          filled: false,
                          contentPadding: const EdgeInsets.only(bottom: 12),
                          border: const UnderlineInputBorder(borderSide: BorderSide(color: Colors.white24)),
                          enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: Colors.white24)),
                          focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppColors.tier3)),
                        ),
                      ),
                      const SizedBox(height: 12),
                      SizedBox(
                        height: 16,
                        child: Text(_error ?? '', style: const TextStyle(fontSize: 12, color: AppColors.loss)),
                      ),
                      const SizedBox(height: 12),
                      AppButton(label: 'Continue', full: true, onPressed: _controller.text.trim().isEmpty ? null : _submit),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
