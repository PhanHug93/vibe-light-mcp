# iOS / Swift — Rules

## Architecture (MVVM + Clean)

- **MVVM**: View → ViewModel → Model/Service — strict separation
- **Coordinator pattern**: Navigation logic outside ViewControllers
- **Protocol-oriented**: Define contracts via protocols, inject dependencies
- **Modular**: SPM packages for features — `Feature/`, `Core/`, `Networking/`
- **Unidirectional data flow**: ViewModel publishes state, View observes

## SwiftUI

- **@State**: Private view-scoped state (toggle, input)
- **@Binding**: Two-way connection to parent's @State
- **@StateObject**: View owns the observable object lifecycle
- **@ObservedObject**: Injected observable, parent owns lifecycle
- **@EnvironmentObject**: Shared data across view hierarchy
- **View composition**: Extract subviews, keep `body` lean (<30 lines)
- **`@ViewBuilder`**: For conditional/composed views
- **Previews**: Always provide `#Preview` for design iteration

## Concurrency (async/await)

- **async/await**: Prefer over completion handlers
- **Actors**: Use `actor` for mutable shared state isolation
- **@MainActor**: Annotate all UI updates (ViewModel, View properties)
- **Task groups**: `withTaskGroup` for parallel work
- **Cancellation**: Check `Task.isCancelled`, use `withTaskCancellationHandler`
- **No GCD in new code**: Prefer structured concurrency over `DispatchQueue`

## State Management (Combine / Observation)

- **@Published**: For ViewModel state properties
- **PassthroughSubject**: For one-time events (navigation, alerts)
- **@Observable** (iOS 17+): Prefer over ObservableObject — automatic tracking
- **AnyCancellable**: Store in `Set<AnyCancellable>`, clear on deinit

## Navigation

- **NavigationStack** (SwiftUI): Type-safe, value-based navigation
- **NavigationPath**: Programmatic navigation with path manipulation
- **Coordinator**: For complex flows (UIKit or hybrid)
- **Deep links**: Handle via `onOpenURL` modifier

## Networking

- **URLSession**: Async/await native APIs (`data(from:)`)
- **Codable**: All DTOs conform to `Codable` with `CodingKeys`
- **Error types**: Typed errors with `enum NetworkError: Error`
- **No force unwrap**: Always handle optional responses safely

## Security

- **Keychain**: Store tokens/secrets via Keychain Services — never UserDefaults
- **App Transport Security**: HTTPS-only, no arbitrary loads in production
- **Biometrics**: LAContext for Face ID / Touch ID gating
- **Data protection**: `FileProtectionType.complete` for sensitive files
- **Certificate pinning**: Via `URLSessionDelegate` or Alamofire

## Performance

- **Instruments**: Profile with Time Profiler, Allocations, Leaks
- **Lazy loading**: `LazyVStack` / `LazyHStack` for large lists
- **Image caching**: Kingfisher or SDWebImage
- **Memory**: Avoid retain cycles — use `[weak self]` in closures

## Anti-Patterns ❌

- Force unwrap (`!`) without guard
- Massive ViewControllers / Views
- GCD for new async code
- Storing secrets in UserDefaults
- Retain cycles (missing `[weak self]`)
- `ObservableObject` without `@Published`
