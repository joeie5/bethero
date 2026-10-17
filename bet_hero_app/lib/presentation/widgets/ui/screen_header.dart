import 'dart:ui';
import 'package:flutter/material.dart';
import '../../../core/theme.dart';

/// Ports `ScreenHeader.tsx` — sticky blurred header with back button.
class ScreenHeader extends StatelessWidget implements PreferredSizeWidget {
  final String title;
  final String? subtitle;
  final Widget? action;
  final bool back;

  const ScreenHeader({super.key, required this.title, this.subtitle, this.action, this.back = true});

  @override
  Size get preferredSize => Size.fromHeight(subtitle != null ? 72 : 64);

  @override
  Widget build(BuildContext context) {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          decoration: BoxDecoration(
            color: AppColors.base.withOpacity(0.8),
            border: Border(bottom: BorderSide(color: Colors.white.withOpacity(0.06))),
          ),
          child: Row(
            children: [
              if (back)
                IconButton(
                  onPressed: () => Navigator.of(context).maybePop(),
                  icon: const Icon(Icons.chevron_left, color: AppColors.inkMuted),
                  splashRadius: 20,
                ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.ink, height: 1.15),
                    ),
                    if (subtitle != null)
                      Text(
                        subtitle!,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12, color: AppColors.inkMuted, height: 1.15),
                      ),
                  ],
                ),
              ),
              if (action != null) action!,
            ],
          ),
        ),
      ),
    );
  }
}
