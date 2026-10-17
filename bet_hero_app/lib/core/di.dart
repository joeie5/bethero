import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';
import '../data/repositories/accumulator_repository.dart';
import '../data/repositories/fixture_repository.dart';
import '../data/repositories/results_repository.dart';
import '../data/repositories/user_repository.dart';
import '../data/repositories/longshot_repository.dart';
import '../data/repositories/tier_repository.dart';

// Service Providers
final authServiceProvider = Provider<AuthService>((ref) {
  return AuthService();
});

final apiServiceProvider = Provider<ApiService>((ref) {
  return ApiService();
});

// Repository Providers
final accumulatorRepositoryProvider = Provider<AccumulatorRepository>((ref) {
  final api = ref.watch(apiServiceProvider);
  return AccumulatorRepository(api);
});

final fixtureRepositoryProvider = Provider<FixtureRepository>((ref) {
  final api = ref.watch(apiServiceProvider);
  return FixtureRepository(api);
});

final resultsRepositoryProvider = Provider<ResultsRepository>((ref) {
  final api = ref.watch(apiServiceProvider);
  return ResultsRepository(api);
});

final userRepositoryProvider = Provider<UserRepository>((ref) {
  final api = ref.watch(apiServiceProvider);
  return UserRepository(api);
});

final longshotRepositoryProvider = Provider<LongshotRepository>((ref) {
  final api = ref.watch(apiServiceProvider);
  return LongshotRepository(api);
});

final tierRepositoryProvider = Provider<TierRepository>((ref) {
  final api = ref.watch(apiServiceProvider);
  return TierRepository(api);
});
