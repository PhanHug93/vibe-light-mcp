# Android / Kotlin — Code Examples

## UiState Pattern

```kotlin
sealed interface UiState {
    object Loading : UiState
    data class Success(val data: List<Item>) : UiState
    data class Error(val message: String) : UiState
}
```

## Event Channel (One-shot Events)

```kotlin
private val _event = Channel<UiEvent>(Channel.BUFFERED)
val event = _event.receiveAsFlow()
```

## StateFlow with stateIn

```kotlin
val uiState: StateFlow<UiState> = repository.stream()
    .map { UiState.Success(it) }
    .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), UiState.Loading)
```

## Flow Collection in Fragment

```kotlin
viewLifecycleOwner.lifecycleScope.launch {
    repeatOnLifecycle(Lifecycle.State.STARTED) {
        flow.collect { }
    }
}
```

## Error Boundary — Result Pattern

```kotlin
sealed class Result<out T> {
    data class Success<T>(val data: T) : Result<T>()
    data class NetworkError(val code: Int?) : Result<Nothing>()
    data class UnknownError(val throwable: Throwable) : Result<Nothing>()
}
```

## ViewBinding Safety

```kotlin
private var _binding: FragmentXBinding? = null
private val binding get() = _binding!!
override fun onDestroyView() { super.onDestroyView(); _binding = null }
```

## Navigation — Action ID Pattern

```kotlin
// ❌ navController.navigate(R.id.challengeDetailFragment, args)
// ✅ navController.navigate(R.id.open_nav_detail_challenge, args)
```
