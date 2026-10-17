import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:firebase_core/firebase_core.dart';
import 'firebase_options.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'app.dart';
import 'core/config.dart';
import 'services/notification_service.dart';
import 'services/api_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // firebase_options.dart only has Android/iOS config — no web Firebase
  // project has been set up (would need `flutterfire configure` to add
  // one), so skip Firebase (and the push-notification service that
  // depends on it) entirely on web rather than crash at startup.
  if (!kIsWeb) {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  }

  // Load environment variables
  await dotenv.load(fileName: ".env");

  // Initialize Supabase
  await Supabase.initialize(
    url: AppConfig.supabaseUrl,
    anonKey: AppConfig.supabaseAnonKey,
  );

  // Initialize Notification Service (Firebase-dependent — mobile only)
  if (!kIsWeb) {
    final notificationService = NotificationService();
    await notificationService.initialize();
  }

  // Test Backend Connection
  final apiService = ApiService();
  await apiService.testConnection();

  runApp(
    const ProviderScope(
      child: BetHeroApp(),
    ),
  );
}
