# Flutter / Dart — Architecture & State Reference

## Clean Architecture Layers

```
lib/
├── core/           # Shared utilities, constants, extensions
├── data/           # Repository implementations, DTOs, data sources
├── domain/         # Entities, use cases, repository interfaces
└── presentation/   # Screens, widgets, BLoC/Cubit, ViewModels
```

## BLoC Pattern

```dart
class AuthBloc extends Bloc<AuthEvent, AuthState> {
  AuthBloc(this._repository) : super(AuthInitial()) {
    on<LoginRequested>(_onLogin);
  }
  final AuthRepository _repository;  
  Future<void> _onLogin(LoginRequested event, Emitter<AuthState> emit) async {
    emit(AuthLoading());
    final result = await _repository.login(event.email, event.password);
    result.fold(
      (failure) => emit(AuthError(failure.message)),
      (user) => emit(AuthSuccess(user)),
    );
  }
}
```

## Riverpod Provider

```dart
final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  return AuthNotifier(ref.watch(authRepositoryProvider));
});
```

## Error Handling — Either Pattern

```dart
typedef ResultFuture<T> = Future<Either<Failure, T>>;

abstract class Failure {
  final String message;
  final int? statusCode;
  Failure({required this.message, this.statusCode});
}
```

## Navigation — GoRouter

```dart
final router = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
    GoRoute(path: '/detail/:id', builder: (_, state) => DetailScreen(id: state.pathParameters['id']!)),
  ],
);
```
