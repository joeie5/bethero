import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Bet Hero design tokens, ported from the bethero-src Tailwind config / index.css.
class AppColors {
  AppColors._();

  // base
  static const Color base = Color(0xFF0B0E14);
  static const Color baseDeep = Color(0xFF080A10);
  static const Color baseRaised = Color(0xFF12151C);
  static const Color baseSunken = Color(0xFF0E1118);

  // ink
  static const Color ink = Color(0xFFEDF1F7);
  static const Color inkMuted = Color(0xFF98A3B4);
  static const Color inkFaint = Color(0xFF68727F);

  // tiers
  static const Color tier3 = Color(0xFF3FC7D8);
  static const Color tier5 = Color(0xFFF0B24B);
  static const Color tier10 = Color(0xFFB47CFF);

  static const Color gold = Color(0xFFE5C07B);
  static const Color win = Color(0xFF3ED598);
  static const Color loss = Color(0xFFCF6A73);

  static Color forTier(String tier) {
    switch (tier) {
      case '3':
        return tier3;
      case '5':
        return tier5;
      case '10':
        return tier10;
      default:
        return tier3;
    }
  }
}

class AppRadius {
  AppRadius._();
  static const double xl = 14;
  static const double xl2 = 18;
  static const double xl3 = 24;
}

/// Easing that approximates the CSS `cubic-bezier(0.23, 1, 0.32, 1)` "swift" curve.
const Curve kSwiftCurve = Cubic(0.23, 1, 0.32, 1);
const Duration kSwiftDuration = Duration(milliseconds: 220);

/// Kept for backwards-compat with older screens written against the previous theme.
class AppTheme {
  static const Color primaryGold = AppColors.gold;
  static const Color background = AppColors.base;
  static const Color secondaryBackground = AppColors.baseRaised;
  static const Color cardBackground = AppColors.baseRaised;
  static const Color successGreen = AppColors.win;
  static const Color dangerRed = AppColors.loss;
  static const Color textPrimary = AppColors.ink;
  static const Color textSecondary = AppColors.inkMuted;

  /// Tabular-figure numeric style ported from the `.num` CSS class.
  static TextStyle numStyle({
    double fontSize = 16,
    FontWeight fontWeight = FontWeight.w700,
    Color color = AppColors.ink,
  }) {
    return GoogleFonts.inter(
      fontSize: fontSize,
      fontWeight: fontWeight,
      color: color,
      letterSpacing: -0.02 * fontSize,
      fontFeatures: const [FontFeature.tabularFigures()],
    );
  }

  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: AppColors.base,
      primaryColor: AppColors.gold,
      fontFamily: GoogleFonts.inter().fontFamily,

      colorScheme: const ColorScheme.dark(
        primary: AppColors.gold,
        secondary: AppColors.tier3,
        surface: AppColors.baseRaised,
        error: AppColors.loss,
        onPrimary: AppColors.base,
        onSecondary: AppColors.base,
        onSurface: AppColors.ink,
      ),

      textTheme: TextTheme(
        displayLarge: GoogleFonts.inter(
          fontSize: 32,
          fontWeight: FontWeight.w800,
          color: AppColors.ink,
          letterSpacing: -0.5,
        ),
        displayMedium: GoogleFonts.inter(
          fontSize: 28,
          fontWeight: FontWeight.w800,
          color: AppColors.ink,
        ),
        displaySmall: GoogleFonts.inter(
          fontSize: 24,
          fontWeight: FontWeight.w700,
          color: AppColors.ink,
        ),
        headlineMedium: GoogleFonts.inter(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: AppColors.ink,
        ),
        titleLarge: GoogleFonts.inter(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: AppColors.ink,
        ),
        bodyLarge: GoogleFonts.inter(
          fontSize: 16,
          color: AppColors.ink,
        ),
        bodyMedium: GoogleFonts.inter(
          fontSize: 14,
          color: AppColors.inkMuted,
        ),
        labelLarge: GoogleFonts.inter(
          fontSize: 14,
          fontWeight: FontWeight.w700,
          color: AppColors.gold,
        ),
      ),

      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        iconTheme: const IconThemeData(color: AppColors.ink),
        titleTextStyle: GoogleFonts.inter(
          color: AppColors.ink,
          fontSize: 18,
          fontWeight: FontWeight.w700,
        ),
      ),

      cardTheme: CardThemeData(
        color: AppColors.baseRaised,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.xl2),
          side: BorderSide(color: Colors.white.withOpacity(0.08)),
        ),
      ),

      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.ink,
          foregroundColor: AppColors.base,
          textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 15),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: const StadiumBorder(),
        ),
      ),

      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.ink,
          backgroundColor: Colors.white.withOpacity(0.05),
          side: BorderSide(color: Colors.white.withOpacity(0.12)),
          textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600),
          shape: const StadiumBorder(),
        ),
      ),

      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.baseRaised,
        hintStyle: GoogleFonts.inter(color: AppColors.inkFaint),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.xl),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.xl),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.xl),
          borderSide: const BorderSide(color: AppColors.gold, width: 1),
        ),
      ),

      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: AppColors.base,
        selectedItemColor: AppColors.ink,
        unselectedItemColor: AppColors.inkFaint,
        type: BottomNavigationBarType.fixed,
        elevation: 0,
      ),

      chipTheme: ChipThemeData(
        backgroundColor: Colors.white.withOpacity(0.04),
        selectedColor: AppColors.ink,
        labelStyle: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.inkMuted),
        secondaryLabelStyle: GoogleFonts.inter(fontSize: 12, color: AppColors.base),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        shape: const StadiumBorder(side: BorderSide(color: Colors.white10)),
      ),
    );
  }
}
