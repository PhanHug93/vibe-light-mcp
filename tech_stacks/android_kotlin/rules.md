# Android / Kotlin — Rules

## Clean Architecture

- **Modular Clean Architecture**: `:app`, `:core:*` (common, network, database, datastore, ui, designsystem, domain), `:feature:*`
- `feature` modules depend chỉ trên `core` — **No feature-to-feature dependency**
- Flow: `UI → ViewModel → UseCase → Repository → DataSource (Remote/Local)`
- `UseCase` là pure Kotlin — **zero Android import**
- Repository implement domain interface, DataSource encapsulate API/DB
- Mapping layer tách biệt: `DTO ↔ Domain ↔ UI models`
- Inject dependency qua constructor (Hilt `@Inject`), không dùng service locator

## DI Scoping (Hilt)

- `@Singleton` → network, database
- `@ViewModelScoped` → UseCase
- `@ActivityRetainedScoped` → session manager
- Tránh overuse `@Singleton` — chỉ dùng khi truly global

## State Modeling (UDF / MVI-Ready)

- Ưu tiên `sealed interface UiState` thay vì multiple LiveData / boolean flags:
  ```kotlin
  sealed interface UiState {
      object Loading : UiState
      data class Success(val data: List<Item>) : UiState
      data class Error(val message: String) : UiState
  }
  ```
- **Không** dùng multiple LiveData cho loading/error/data
- **Không** dùng boolean flags rải rác trong ViewModel

## Event Channel (One-shot Events)

- Dùng `Channel<UiEvent>(Channel.BUFFERED)` + `receiveAsFlow()`:
  ```kotlin
  private val _event = Channel<UiEvent>(Channel.BUFFERED)
  val event = _event.receiveAsFlow()
  ```
- Tránh `SingleLiveEvent` anti-pattern
- Prevents re-emission khi configuration change

## Coroutines & Flow

- `viewModelScope` cho ViewModel, `lifecycleScope` cho UI
- `StateFlow` cho UI state, dùng `stateIn()` với `WhileSubscribed(5000)`:
  ```kotlin
  val uiState: StateFlow<UiState> = repository.stream()
      .map { UiState.Success(it) }
      .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), UiState.Loading)
  ```
- Fragment collect Flow phải dùng `repeatOnLifecycle`:
  ```kotlin
  viewLifecycleOwner.lifecycleScope.launch {
      repeatOnLifecycle(Lifecycle.State.STARTED) {
          flow.collect { }
      }
  }
  ```
- **Cấm**: `GlobalScope`, `runBlocking` trong production code
- Dùng `Mutex` tránh race condition (đặc biệt khi refresh token)

## Error Boundary

- Repository trả `sealed class Result<T>` — không ném exception thô ra UI:
  ```kotlin
  sealed class Result<out T> {
      data class Success<T>(val data: T) : Result<T>()
      data class NetworkError(val code: Int?) : Result<Nothing>()
      data class UnknownError(val throwable: Throwable) : Result<Nothing>()
  }
  ```
- ViewModel map `Result` → `UiState` — **never expose raw exceptions**

## Lifecycle Safety (ViewBinding)

- Fragment ViewBinding pattern bắt buộc:
  ```kotlin
  private var _binding: FragmentXBinding? = null
  private val binding get() = _binding!!
  override fun onDestroyView() { super.onDestroyView(); _binding = null }
  ```
- **Không** store Context trong Singleton
- **Không** store View trong companion object

## Jetpack Compose (Interop / Migration)

- Compose dùng khi được yêu cầu, ViewBinding là mặc định
- ComposeView phải set `DisposeOnViewTreeLifecycleDestroyed` strategy
- `@Immutable` / `@Stable` data class cho Compose state
- `key()` cho LazyColumn items, `derivedStateOf` cho computed values
- Tránh: mutable lists, inline object creation, heavy remember blocks

## Navigation

- Action ID khi navigate trong nested graph — **không dùng Fragment ID**:
  ```kotlin
  // ❌ navController.navigate(R.id.challengeDetailFragment, args)
  // ✅ navController.navigate(R.id.open_nav_detail_challenge, args)
  ```
- Không truyền complex object qua nav args — chỉ ID, sau đó fetch
- Deep link khai báo trong `AndroidManifest.xml` + nav graph

## Network Layer (Enterprise Hardened)

- OkHttp interceptors order: Logging (DEBUG only) → Auth → Retry → Cache
- Token refresh: single-flight safe với `Mutex`, prevent duplicate 401 refresh
- HTTPS-only, certificate pinning per flavor
- Không log: Authorization header, PII, raw JSON response

## Offline-First

- Repository: emit local → fetch remote → update local
- UI observe Room `Flow` trực tiếp
- Survives process death, fast cold start, resilient to network loss

## Security

- `EncryptedSharedPreferences` (AES-256-GCM) cho tokens — never plain SharedPreferences
- Android Keystore cho signing, encryption, biometric-bound crypto
- Zeroize sensitive `ByteArray` after use — không dùng `String` cho private key
- `FLAG_SECURE` cho sensitive screens (screenshot/recording protection)
- Clipboard TTL — clear sau X giây
- R8/ProGuard: obfuscate release, remove debug logs
- `android:allowBackup="false"`, `android:usesCleartextTraffic="false"`

## Performance

- Cold start < 2s — lazy init non-critical SDKs, use App Startup wisely
- RecyclerView: `ListAdapter` + `DiffUtil`, `setHasStableIds(true)`, **never** `notifyDataSetChanged()`
- Baseline Profiles: mandatory cho production
- LeakCanary: debug builds, detect Context/Activity leaks
- StrictMode: enabled in debug — `detectAll()` + `penaltyLog()`
- Coil/Glide với memory policy cho bitmap — avoid large decode in ViewModel

## Background Work

- `WorkManager` cho token refresh sync, upload queue, periodic sync
- **Never**: `IntentService` (deprecated), `AlarmManager` for sync

## Testing Architecture

- ViewModel: Turbine cho Flow testing + `StandardTestDispatcher`
- Network: MockWebServer, test 401 refresh path
- Database: In-memory Room, migration test
- Health Connect: Fake client pattern, controllable clock

## Anti-patterns ❌

- Multiple LiveData for state
- Business logic inside Fragment
- Direct Retrofit call from ViewModel
- Storing Context in Singleton
- `GlobalScope` / `runBlocking` in production
- Blocking I/O on Main thread
- Catching `Exception` and ignoring
- `if (x != null) { x!!.doSomething() }` → dùng `x?.doSomething()`

## Logic Correctness

- De Morgan's Law: `neither/nor` dùng `&&`, `either/or` dùng `||`
- Sealed class/enum: dùng `when` exhaustive — **không** dùng if/else chain
- Null safety: `?.let {}`, `?: return`, `?: default` — **không** `!!`
