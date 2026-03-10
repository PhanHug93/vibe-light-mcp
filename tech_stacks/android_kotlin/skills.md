# Android / Kotlin — Skills (Terminal Commands)

## Build

```bash
# Debug build
./gradlew assembleDebug

# Release build
./gradlew assembleRelease

# Build specific flavor
./gradlew assemble{Flavor}Debug

# Build bundle (AAB) cho Play Store
./gradlew bundleRelease

# Clean build
./gradlew clean assembleDebug

# Compile-only check (nhanh, không build APK)
./gradlew :app:compileProdDebugKotlin

# Build specific module
./gradlew :feature:wallet:assembleDebug
```

## Install & Run

```bash
# Install APK lên device
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Install + launch
adb install -r app-debug.apk && adb shell am start -n com.example.app/.MainActivity

# Uninstall
adb uninstall com.example.app
```

## Debug & Logs

```bash
# Logcat realtime (filter tag)
adb logcat -s "MyTag"

# Logcat dump rồi thoát
adb logcat -d > logcat.txt

# Clear log buffer
adb logcat -c

# Filter theo priority (E=Error, W=Warning)
adb logcat *:E

# Stack trace crash — filter theo PID của app
adb logcat --pid=$(adb shell pidof com.example.app)

# Enable verbose logging cho component
adb shell setprop log.tag.ESPL VERBOSE

# Filter FCM + Navigation flow
adb logcat | grep -E "FCM|ChallengeDetail|navigateTo|payloadConsumed"

# Timber tag filter (Android Studio Logcat)
# Query: FCM OR ChallengeDetail OR navigateTo OR payloadConsumed
```

## Testing

```bash
# Unit tests (all)
./gradlew test

# Unit test module cụ thể
./gradlew :app:testDebugUnitTest

# Test specific class
./gradlew :app:testProdDebugUnitTest --tests "ClassName"

# Instrumented tests (cần device/emulator)
./gradlew connectedAndroidTest

# Test với coverage
./gradlew testDebugUnitTest jacocoTestReport
```

## Code Quality

```bash
# Lint check
./gradlew lint

# Lint report HTML
open app/build/reports/lint-results-debug.html

# Ktlint format
./gradlew ktlintFormat

# Detekt static analysis
./gradlew detekt

# Dependency vulnerability scan
./gradlew dependencyCheckAnalyze
```

## Performance Profiling

```bash
# Memory profiling
adb shell dumpsys meminfo com.example.app

# Enable GPU rendering profiling
adb shell setprop debug.hwui.profile true

# Frame rendering stats
adb shell dumpsys gfxinfo com.example.app

# StrictMode (enable trong code, check output)
adb logcat -s StrictMode

# Baseline Profile generation (module)
./gradlew :baselineprofile:connectedBenchmarkAndroidTest

# Macrobenchmark
./gradlew :benchmark:connectedBenchmarkAndroidTest
```

## Dependency

```bash
# Dependency tree
./gradlew :app:dependencies

# Outdated dependencies
./gradlew dependencyUpdates

# Dependency insight
./gradlew :app:dependencyInsight --dependency <name>
```

## Gradle Info & Build Performance

```bash
# List tasks
./gradlew tasks --all

# Build scan
./gradlew assembleDebug --scan

# Gradle version
./gradlew --version

# Build cache stats
./gradlew assembleDebug --build-cache --info

# Enable build optimization (gradle.properties)
# org.gradle.configuration-cache=true
# org.gradle.caching=true
# org.gradle.parallel=true
```

## ADB Utilities

```bash
# List devices
adb devices

# Device info
adb shell getprop ro.build.version.sdk

# Screenshot
adb exec-out screencap -p > screenshot.png

# Screen record
adb shell screenrecord /sdcard/demo.mp4

# Push/pull files
adb push local.txt /sdcard/
adb pull /sdcard/remote.txt ./

# Clear app data
adb shell pm clear com.example.app

# Reverse port (localhost tunnel)
adb reverse tcp:8080 tcp:8080

# Force stop app
adb shell am force-stop com.example.app
```

## FCM Debug

```bash
# Lấy FCM Token
adb logcat | grep "FCM Token"

# Gửi test FCM payload via adb
adb shell am broadcast \
  -a com.google.android.c2dm.intent.RECEIVE \
  -p com.example.app \
  --es "href" "12345" \
  --es "type" "1"
```

## Signing

```bash
# Generate keystore
keytool -genkey -v -keystore release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias release

# Verify APK signature
apksigner verify --verbose app-release.apk

# Print signing cert
keytool -printcert -jarfile app-release.apk
```

## Debug Workflow

```bash
# 1. Reproduce issue
# 2. Enable StrictMode (trong code)
# 3. Capture logs
adb logcat -c && adb logcat > debug_log.txt
# 4. Profile memory & CPU (Android Studio Profiler)
# 5. Write regression test
```

## Optimization Workflow

```bash
# 1. Establish baseline (P50, P95 metrics)
# 2. Profile bottleneck
adb shell dumpsys meminfo com.example.app
adb shell dumpsys gfxinfo com.example.app
# 3. Apply focused fix
# 4. Re-measure (same device, same build type)
# 5. If < 5% improvement → revert
```
