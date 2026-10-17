import 'package:flutter/material.dart';
import '../../../core/theme.dart';

/// Ports `Logo.tsx` LogoMark (simplified diamond) + Wordmark.
class LogoMark extends StatelessWidget {
  final double size;
  const LogoMark({super.key, this.size = 40});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(painter: _LogoPainter()),
    );
  }
}

class _LogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final outer = Path()
      ..moveTo(w * 0.5, h * 0.02)
      ..lineTo(w * 0.9, h * 0.24)
      ..lineTo(w * 0.9, h * 0.71)
      ..lineTo(w * 0.5, h * 0.95)
      ..lineTo(w * 0.1, h * 0.71)
      ..lineTo(w * 0.1, h * 0.24)
      ..close();
    canvas.drawPath(
      outer,
      Paint()
        ..color = Colors.white.withOpacity(0.03)
        ..style = PaintingStyle.fill,
    );
    canvas.drawPath(
      outer,
      Paint()
        ..color = Colors.white.withOpacity(0.18)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );
    final bolt = Path()
      ..moveTo(w * 0.55, h * 0.25)
      ..lineTo(w * 0.33, h * 0.54)
      ..lineTo(w * 0.48, h * 0.54)
      ..lineTo(w * 0.44, h * 0.75)
      ..lineTo(w * 0.67, h * 0.46)
      ..lineTo(w * 0.52, h * 0.46)
      ..close();
    canvas.drawPath(bolt, Paint()..color = AppColors.tier3);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class Wordmark extends StatelessWidget {
  final double fontSize;
  const Wordmark({super.key, this.fontSize = 24});

  @override
  Widget build(BuildContext context) {
    return RichText(
      text: TextSpan(
        style: TextStyle(fontSize: fontSize, fontWeight: FontWeight.w800, color: AppColors.ink, letterSpacing: -0.5),
        children: const [
          TextSpan(text: 'Bet'),
          TextSpan(text: 'Hero', style: TextStyle(color: AppColors.tier3)),
        ],
      ),
    );
  }
}
