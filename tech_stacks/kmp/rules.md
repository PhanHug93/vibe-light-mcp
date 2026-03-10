# Kotlin Multiplatform — Rules

## Module Architecture

- **`:shared`** (core KMP module) chứa `commonMain`, `androidMain`, `iosMain`
- Feature modules: `:feature:auth`, `:feature:home` — depend on `:shared`
- Platform apps: `:androidApp`, `:iosApp` — chỉ chứa UI layer
- Dependency flow: `platform app` → `feature` → `:shared` (không ngược lại)

## Source Sets

```
shared/src/
├── commonMain/    → Business logic, interfaces, expect declarations
├── commonTest/    → Shared unit tests
├── androidMain/   → Android actual implementations
├── iosMain/       → iOS actual implementations
├── desktopMain/   → Desktop actual (nếu cần)
└── jvmMain/       → JVM-specific (nếu cần)
```

## expect / actual

- `expect` chỉ khai báo **interface/contract** trong `commonMain`
- `actual` implement cho từng platform — đặt đúng source set
- Ưu tiên dùng **interface + DI** thay vì `expect/actual` khi có thể
- `expect/actual` phù hợp cho: platform logger, file system, crypto, UUID

## Shared Domain Layer

- `commonMain` chứa: `UseCase`, `Repository interface`, `Entity`, `Mapper`
- **Zero platform import** trong domain — pure Kotlin only
- Networking: Ktor `HttpClient` + engine inject per platform
- Serialization: `kotlinx.serialization` (không dùng Gson/Moshi)
- Date/time: `kotlinx-datetime` (không dùng `java.time` trực tiếp)

## Concurrency

- Coroutines: `kotlinx.coroutines` cho cả 2 platforms
- iOS: mặc định Kotlin coroutines chạy trên main thread — cẩn thận `Dispatchers.Default`
- Dùng `Flow` cho reactive streams, collect ở platform layer
- iOS collect Flow qua wrapper: `CFlow<T>` hoặc SKIE/KMP-NativeCoroutines

## iOS Interop

- Export framework qua `binaries.framework { baseName = "Shared" }`
- Objective-C/Swift gọi Kotlin class — chú ý name mangling
- Sealed class → Swift enum mapping cần `@ObjCName` hoặc SKIE
- Nullability: Kotlin `T?` → Swift `Optional<T>` (mapping tự động)
- Generic types bị erase trên iOS — dùng wrapper class nếu cần
- Tránh expose `suspend fun` trực tiếp cho Swift — wrap bằng callback/Combine

## Dependency Injection

- `commonMain`: Koin module definitions (hoặc kotlin-inject)
- Mỗi platform có riêng module khai báo `actual` implementations
- Inject `HttpClient` engine: `OkHttp` (Android), `Darwin` (iOS)

## Testing

- `commonTest`: shared test logic, dùng `kotlin.test`
- Mock/fake: tạo manual fakes trong `commonTest` (Mockk chỉ hoạt động JVM)
- Platform tests trong `androidTest/`, `iosTest/`
- Integration test: Ktor `MockEngine` cho network layer

## Naming & Packaging

- Package: `com.company.project.feature.layer`
- Shared classes không prefix platform: `UserRepository` (không `SharedUserRepository`)
- Platform-specific: suffix nếu cần `AndroidDatabaseDriver`, `IosDatabaseDriver`
- File naming: `PascalCase.kt`, 1 class per file (trừ sealed + data classes liên quan)
