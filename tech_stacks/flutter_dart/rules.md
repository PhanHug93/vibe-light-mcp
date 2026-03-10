# Flutter / Dart — Rules

## Clean Architecture

- **Modular Clean Architecture**: `core/` (common, network, database, theme, domain), `features/` (auth, home, wallet, ...)
- `features/` depend chỉ trên `core/` — **No feature-to-feature dependency**
- Flow: `UI (Screen) → BLoC/Cubit → UseCase → Repository → DataSource (Remote/Local)`
- `UseCase` là pure Dart — **zero Flutter import**
- Repository implement domain interface, DataSource encapsulate API/DB
- Mapping layer tách biệt: `DTO ↔ Domain Entity ↔ UI Model`
- DI qua `get_it` + `injectable`, tập trung trong `injection.dart`

## DI Scoping (get_it)

- `@Singleton` → network client, database, shared preferences wrapper
- `@LazySingleton` → repositories, data sources
- `@Injectable` → UseCase (transient, mới mỗi lần resolve)
- `@Environment('dev')` / `@Environment('prod')` → flavor-specific bindings
- Tránh overuse `@Singleton` — chỉ dùng khi truly global

## State Modeling (Sealed / Freezed)

- Ưu tiên `sealed class` hoặc `freezed` cho UI state — không dùng boolean flags:
  ```dart
  @freezed
  class HomeState with _$HomeState {
    const factory HomeState.initial() = _Initial;
    const factory HomeState.loading() = _Loading;
    const factory HomeState.loaded(List<Item> items) = _Loaded;
    const factory HomeState.error(String message) = _Error;
  }
  ```
- **Không** dùng multiple biến `isLoading`, `hasError`, `data` rời rạc
- State phải `@immutable` — dùng `freezed` hoặc `Equatable`

## BLoC Pattern (Enterprise)

- `Bloc` cho complex event-driven logic, `Cubit` cho simple state changes
- Event naming: `VerbNoun` → `LoadUsers`, `DeleteUser`, `SubmitForm`
- State naming: `FeatureInitial`, `FeatureLoading`, `FeatureLoaded`, `FeatureError`
- `BlocListener` cho side effects (navigate, snackbar), `BlocBuilder` cho UI
- Không gọi business logic trong Widget — mọi thứ đi qua Bloc
- `transformEvents` / `EventTransformer` cho debounce, throttle, sequential

## Event Channel (One-shot Events)

- Dùng `BlocListener` cho navigation, dialog, snackbar — **không dùng** `BlocBuilder`
- Hoặc separate `Stream<UiEvent>` trong Cubit khi cần:
  ```dart
  final _events = StreamController<UiEvent>.broadcast();
  Stream<UiEvent> get events => _events.stream;
  ```
- Tránh: trigger one-shot action trong `BlocBuilder` — sẽ re-trigger khi rebuild

## Riverpod (Alternative)

- `ref.watch()` trong `build()`, `ref.read()` trong callbacks
- `StateNotifierProvider` cho mutable state, `FutureProvider` cho async one-shot
- `autoDispose` mặc định — chỉ bỏ khi cần cache
- **Không** `ref.read()` trong `build()` — gây miss rebuild
- `AsyncValue` pattern: `when(data: ..., error: ..., loading: ...)`

## Error Boundary

- Repository trả `Either<Failure, T>` (dartz/fpdart) hoặc sealed Result:
  ```dart
  sealed class Result<T> {
    const factory Result.success(T data) = Success;
    const factory Result.networkError(int? code, String message) = NetworkError;
    const factory Result.unknownError(Object error) = UnknownError;
  }
  ```
- Bloc/Cubit map `Result` → State — **never expose raw exceptions to UI**
- Catch tại DataSource level, wrap thành domain failure

## Null Safety (Cực ngặt)

- **Không bao giờ** dùng `!` (bang operator) — xử lý null explicitly
- Dùng `?.`, `??`, `??=` thay cho force unwrap
- `late` chỉ khi 100% chắc chắn init trước access — prefer nullable + null check
- Model fields bắt buộc: `required` keyword, không để nullable khi không cần
- Collection luôn non-null: `List<T>` default `const []`, không dùng `List<T>?`
- Dart 3+ pattern matching: `if (value case final v?)`, `switch` expressions
- Safe casting: `if (obj case MyType t)` thay vì `obj as MyType`

## Widget Tree Optimization

- **const constructor** mọi nơi có thể → `const MyWidget()`, `const SizedBox()`
- Tách widget nhỏ thành **class riêng** — không dùng helper method `_buildXyz()`
- `ListView.builder` / `GridView.builder` cho lists — **không** `Column` + `map()`
- `RepaintBoundary` cho widget animate phức tạp
- Tránh `setState()` ở widget cha — chỉ rebuild widget con cần thiết
- `ValueListenableBuilder` / `AnimatedBuilder` cho granular rebuild
- `key()`: `ValueKey` cho list items, `GlobalKey` chỉ khi thật sự cần access state
- `BlocSelector` để chỉ rebuild khi field cụ thể thay đổi

## Routing (go_router)

- Khai báo routes tập trung, type-safe routes
- Deep linking: khai báo path pattern, parse params
- Shell route cho persistent bottom nav / drawer
- Redirect guards cho auth check
- Nested navigation cho feature flows

## Network Layer (Enterprise Hardened)

- Dio interceptors order: Logging (DEBUG only) → Auth → Retry → Cache
- Token refresh: single-flight safe pattern — prevent duplicate 401 refresh:
  ```dart
  final _refreshLock = Lock(); // from synchronized package
  Future<void> refreshToken() => _refreshLock.synchronized(() async { ... });
  ```
- HTTPS-only, certificate pinning via `SecurityContext`
- Không log: Authorization header, PII, raw JSON response
- Retry với exponential backoff cho transient errors

## Offline-First

- Repository: emit local (Hive/Isar/SQLite) → fetch remote → update local
- UI observe local stream trực tiếp
- Sync strategy: one-shot backfill + delta sync từ `lastSyncTimestamp`
- Conflict resolution: timestamp-based — newer data wins

## Security

- `flutter_secure_storage` cho tokens — never plain `SharedPreferences`
- Sensitive screens: disable screenshots via platform channel + `FLAG_SECURE`
- Obfuscation: `flutter build apk --obfuscate --split-debug-info=./debug-info/`
- API keys trong `--dart-define` hoặc `.env` — never hardcode
- Clear clipboard sau TTL cho sensitive data
- Certificate pinning cho fintech/healthcare apps
- `android:allowBackup="false"` trong `AndroidManifest.xml`

## Performance

- Cold start tối ưu: lazy init non-critical services
- `ListView.builder` + `key` cho smooth scroll — target 60fps
- Image: `cached_network_image` với placeholder + error widget
- Isolate (`compute()`) cho heavy JSON parsing, crypto operations
- Tree shaking: remove unused packages, analyze bundle size
- Deferred loading: `deferred as` cho code splitting (web)
- Memory profiling: DevTools Memory tab, detect widget leaks

## Background Work

- `workmanager` package cho periodic background tasks
- `flutter_background_service` cho foreground services
- Platform channels cho platform-specific background logic

## Testing Architecture

- **Unit test**: Bloc/Cubit với `blocTest()` (bloc_test package)
- **Widget test**: `pumpWidget()` + `find.byType()` + interaction
- **Integration test**: `integration_test` package, full flow
- Mock: `mockito` / `mocktail` — prefer `mocktail` (no codegen)
- Network mock: `http_mock_adapter` cho Dio
- Golden tests: `matchesGoldenFile()` cho visual regression
- Coverage gate: > 80% cho domain & data layer

## Anti-patterns ❌

- Business logic inside Widget
- Direct API call from Widget
- `setState()` khi có thể dùng BLoC/Cubit
- Deep widget nesting thay vì composition
- Storing `BuildContext` in async gap
- `!` (bang operator) thay vì null handling
- `notifyListeners()` storm trong ChangeNotifier
- Catching `Exception` and ignoring
- Mutable state classes không dùng `freezed` / `Equatable`

## Logic Correctness

- Pattern matching (Dart 3): `switch` expression thay vì if/else chain
- Sealed class exhaustive check — compiler báo lỗi khi thiếu case
- Null safety: `?.let` equivalent = `value?.also((v) => ...)` hoặc `if-case`
- Collection null: `list?.isNotEmpty == true` thay vì `list!.isNotEmpty`

## Project Structure

```
lib/
├── core/
│   ├── common/        → constants, extensions, utils
│   ├── network/       → dio client, interceptors, API config
│   ├── database/      → local DB setup, DAOs
│   ├── theme/         → colors, typography, app theme
│   └── domain/        → base failure, base use case
├── features/
│   ├── auth/
│   │   ├── data/      → repo impl, data sources, DTOs
│   │   ├── domain/    → entities, use cases, repo interface
│   │   └── presentation/ → screens, blocs, widgets
│   ├── home/
│   └── wallet/
├── injection.dart     → DI setup
└── main.dart
```

- File naming: `snake_case.dart`
- Class: `PascalCase`, private: `_prefix`
- Barrel exports: 1 file `feature.dart` export all public APIs
