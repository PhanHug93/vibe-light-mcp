# KMP — Platform-Specific Code Reference

## expect/actual Pattern

```kotlin
// commonMain
expect fun platformName(): String

// androidMain
actual fun platformName(): String = "Android ${Build.VERSION.SDK_INT}"

// iosMain
actual fun platformName(): String = UIDevice.currentDevice.systemName
```

## Shared ViewModel

```kotlin
// commonMain
class SharedViewModel : ViewModel() {
    private val _state = MutableStateFlow<UiState>(UiState.Loading)
    val state: StateFlow<UiState> = _state.asStateFlow()
}
```

## Ktor Networking

```kotlin
val client = HttpClient {
    install(ContentNegotiation) { json() }
    install(Logging) { level = LogLevel.BODY }
}
```

## Koin DI (Cross-platform)

```kotlin
// commonMain
val sharedModule = module {
    single<ApiClient> { KtorApiClient(get()) }
    factory { GetUserUseCase(get()) }
}
```
