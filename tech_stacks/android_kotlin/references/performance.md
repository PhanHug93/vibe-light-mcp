# Android / Kotlin — Performance & Testing Reference

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
