import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';
import '../../../core/theme.dart';

/// Ports `Skeleton.tsx` using the `shimmer` package already in pubspec.yaml.
class AppSkeleton extends StatelessWidget {
  final double width;
  final double height;
  final double radius;

  const AppSkeleton({super.key, this.width = double.infinity, this.height = 14, this.radius = 8});

  @override
  Widget build(BuildContext context) {
    return Shimmer.fromColors(
      baseColor: Colors.white.withOpacity(0.06),
      highlightColor: Colors.white.withOpacity(0.13),
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.06),
          borderRadius: BorderRadius.circular(radius),
        ),
      ),
    );
  }
}

class SkeletonTierCard extends StatelessWidget {
  const SkeletonTierCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.03),
        borderRadius: BorderRadius.circular(AppRadius.xl2),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: const [
                    AppSkeleton(width: 96, height: 20, radius: 999),
                    SizedBox(height: 12),
                    AppSkeleton(width: 128, height: 40),
                    SizedBox(height: 12),
                    AppSkeleton(width: 160, height: 12),
                  ],
                ),
              ),
              const AppSkeleton(width: 76, height: 76, radius: 76),
            ],
          ),
          const SizedBox(height: 20),
          const AppSkeleton(height: 12),
          const SizedBox(height: 8),
          const AppSkeleton(width: 200, height: 12),
        ],
      ),
    );
  }
}

class SkeletonRow extends StatelessWidget {
  const SkeletonRow({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.03),
        borderRadius: BorderRadius.circular(AppRadius.xl),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: const [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                AppSkeleton(height: 12),
                SizedBox(height: 8),
                AppSkeleton(width: 96, height: 12),
              ],
            ),
          ),
          SizedBox(width: 12),
          AppSkeleton(width: 56, height: 24),
        ],
      ),
    );
  }
}
