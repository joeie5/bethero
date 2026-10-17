import 'package:flutter/material.dart';
import '../../../core/theme.dart';

enum OddsSize { sm, md, lg, hero }

/// Ports `OddsDisplay.tsx`. Currently only supports decimal formatting
/// (fractional-odds toggle from AppContext.oddsFormat is not yet wired to a
/// Riverpod provider in this Flutter app).
class OddsDisplay extends StatelessWidget {
  final double odds;
  final OddsSize size;
  final Color? color;

  const OddsDisplay({super.key, required this.odds, this.size = OddsSize.md, this.color});

  @override
  Widget build(BuildContext context) {
    double fontSize;
    FontWeight weight;
    switch (size) {
      case OddsSize.sm:
        fontSize = 14;
        weight = FontWeight.w600;
        break;
      case OddsSize.md:
        fontSize = 18;
        weight = FontWeight.w700;
        break;
      case OddsSize.lg:
        fontSize = 30;
        weight = FontWeight.w700;
        break;
      case OddsSize.hero:
        fontSize = 52;
        weight = FontWeight.w800;
        break;
    }
    return Text(
      odds.toStringAsFixed(2),
      style: AppTheme.numStyle(fontSize: fontSize, fontWeight: weight, color: color ?? AppColors.ink),
    );
  }
}
