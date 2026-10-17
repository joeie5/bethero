import 'package:flutter/material.dart';
import '../../../core/theme.dart';

/// Ports `ResponsibleFooter.tsx`.
class ResponsibleFooter extends StatelessWidget {
  const ResponsibleFooter({super.key});

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(left: 20, right: 20, top: 24, bottom: 8),
      child: Text(
        'Predictions are probabilistic, not guarantees. Bet responsibly.',
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: 11, height: 1.5, color: AppColors.inkFaint),
      ),
    );
  }
}
