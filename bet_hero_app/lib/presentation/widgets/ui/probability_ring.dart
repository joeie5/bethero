import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../../../core/theme.dart';

/// Ports `ProbabilityRing.tsx` with an implicit tween animation.
class ProbabilityRing extends StatelessWidget {
  final double value; // 0-1
  final double size;
  final double stroke;
  final Color color;
  final String? label;

  const ProbabilityRing({
    super.key,
    required this.value,
    this.size = 76,
    this.stroke = 6,
    this.color = AppColors.tier3,
    this.label,
  });

  @override
  Widget build(BuildContext context) {
    final pct = value.clamp(0.0, 1.0);
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: pct),
            duration: const Duration(milliseconds: 800),
            curve: kSwiftCurve,
            builder: (context, animated, _) {
              return CustomPaint(
                size: Size(size, size),
                painter: _RingPainter(progress: animated, stroke: stroke, color: color),
              );
            },
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '${(pct * 100).round()}%',
                style: AppTheme.numStyle(fontSize: 16, fontWeight: FontWeight.w700, color: color),
              ),
              if (label != null) ...[
                const SizedBox(height: 2),
                Text(
                  label!.toUpperCase(),
                  style: const TextStyle(fontSize: 9, color: AppColors.inkFaint, letterSpacing: 0.6),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  final double progress;
  final double stroke;
  final Color color;
  _RingPainter({required this.progress, required this.stroke, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = (size.width - stroke) / 2;
    final bgPaint = Paint()
      ..color = Colors.white.withOpacity(0.09)
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke;
    canvas.drawCircle(center, radius, bgPaint);

    final fgPaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      2 * math.pi * progress,
      false,
      fgPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _RingPainter old) => old.progress != progress || old.color != color;
}
