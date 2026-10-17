import 'package:flutter/material.dart';
import '../../../core/theme.dart';

/// Ports `LeagueSection.tsx` — collapsible section header + animated content.
class LeagueSection extends StatefulWidget {
  final String league;
  final int count;
  final Widget child;
  final bool defaultOpen;

  const LeagueSection({
    super.key,
    required this.league,
    required this.count,
    required this.child,
    this.defaultOpen = true,
  });

  @override
  State<LeagueSection> createState() => _LeagueSectionState();
}

class _LeagueSectionState extends State<LeagueSection> {
  late bool _open = widget.defaultOpen;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => setState(() => _open = !_open),
            borderRadius: BorderRadius.circular(8),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    widget.league.toUpperCase(),
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: AppColors.inkMuted),
                  ),
                  Row(
                    children: [
                      Text('${widget.count}', style: const TextStyle(fontSize: 11, color: AppColors.inkFaint)),
                      const SizedBox(width: 6),
                      AnimatedRotation(
                        turns: _open ? 0 : -0.25,
                        duration: kSwiftDuration,
                        curve: kSwiftCurve,
                        child: const Icon(Icons.keyboard_arrow_down, size: 18, color: AppColors.inkFaint),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          AnimatedCrossFade(
            firstChild: Padding(padding: const EdgeInsets.only(top: 8), child: widget.child),
            secondChild: const SizedBox(width: double.infinity, height: 0),
            crossFadeState: _open ? CrossFadeState.showFirst : CrossFadeState.showSecond,
            duration: kSwiftDuration,
            sizeCurve: kSwiftCurve,
          ),
        ],
      ),
    );
  }
}
