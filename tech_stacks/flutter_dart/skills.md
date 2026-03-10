# Flutter / Dart — Skills (Terminal Commands)

## Dependencies

```bash
# Install packages
flutter pub get

# Upgrade packages (minor versions)
flutter pub upgrade

# Upgrade packages (major versions)
flutter pub upgrade --major-versions

# Outdated check
flutter pub outdated

# Add package
flutter pub add <package_name>

# Add dev dependency
flutter pub add --dev <package_name>

# Remove package
flutter pub remove <package_name>

# Dependency tree (resolve conflicts)
flutter pub deps
```

## Code Generation

```bash
# Build runner (freezed, json_serializable, injectable, etc.)
dart run build_runner build --delete-conflicting-outputs

# Watch mode
dart run build_runner watch --delete-conflicting-outputs

# Clean generated files
dart run build_runner clean

# Generate DI (injectable)
dart run build_runner build --delete-conflicting-outputs --filter "injectable_generator"
```

## Analysis & Format

```bash
# Static analysis
flutter analyze

# Auto-fix lint issues
dart fix --apply

# Format code
dart format .

# Format + check only (CI gate)
dart format --set-exit-if-changed .

# Custom analysis — check analysis_options.yaml
# Recommended: very_good_analysis or flutter_lints
```

## Testing

```bash
# Run all tests
flutter test

# Test với coverage
flutter test --coverage

# View coverage report
genhtml coverage/lcov.info -o coverage/html && open coverage/html/index.html

# Test file cụ thể
flutter test test/unit/auth_bloc_test.dart

# Test với filter (tên test)
flutter test --name "should emit loaded state"

# Integration test
flutter test integration_test/

# Test với verbose output
flutter test --reporter expanded

# Golden test update (khi intentional UI change)
flutter test --update-goldens
```

## Build — Android

```bash
# Debug APK
flutter build apk --debug

# Release APK
flutter build apk --release

# Split APK theo ABI (giảm size)
flutter build apk --release --split-per-abi

# App Bundle (Play Store)
flutter build appbundle --release

# Build flavor cụ thể
flutter build apk --release --flavor production -t lib/main_production.dart

# Obfuscated build (security)
flutter build apk --release --obfuscate --split-debug-info=./debug-info/

# Compile-only check (nhanh, không build full APK)
flutter build apk --debug --analyze-size
```

## Build — iOS

```bash
# Debug build
flutter build ios --debug --no-codesign

# Release build
flutter build ios --release

# Build IPA (distribution)
flutter build ipa --release

# Obfuscated build (security)
flutter build ipa --release --obfuscate --split-debug-info=./debug-info/

# Pod install (khi lỗi iOS build)
cd ios && pod install --repo-update && cd ..

# Clean iOS build
cd ios && rm -rf Pods Podfile.lock && pod install && cd ..

# Xcode workspace (mở manual)
open ios/Runner.xcworkspace
```

## Build — Web

```bash
# Dev server
flutter run -d chrome

# Release build
flutter build web --release

# Build với base href (deploy subfolder)
flutter build web --release --base-href /myapp/

# Analyze bundle size (web)
flutter build web --release --source-maps
```

## Run & Debug

```bash
# Run trên device/emulator mặc định
flutter run

# Run trên device cụ thể
flutter run -d <device_id>

# List devices
flutter devices

# Run với verbose
flutter run --verbose

# Performance profiling
flutter run --profile

# Release mode test
flutter run --release

# Hot reload / restart (trong terminal khi đang run)
# r = hot reload, R = hot restart, q = quit
```

## Performance Profiling

```bash
# DevTools (browser-based profiler)
flutter pub global activate devtools
flutter pub global run devtools

# Run với profiling
flutter run --profile

# Timeline tracing
flutter run --trace-startup

# Widget rebuild tracking (trong DevTools)
# Performance → Track Widget Rebuilds

# Analyze APK size
flutter build apk --analyze-size
flutter build appbundle --analyze-size

# Skia shader warmup dump
flutter run --profile --cache-sksl --purge-persistent-cache
flutter build apk --bundle-sksl-path=flutter_01.sksl.json
```

## Memory & Leak Detection

```bash
# DevTools Memory tab
# 1. flutter run --debug
# 2. Open DevTools → Memory
# 3. Take heap snapshot, analyze retained objects

# Dump Flutter memory
flutter run --verbose 2>&1 | grep -i memory

# Observatory / VM Service
# flutter run → copy Observatory URL → open in browser
```

## Code Quality & CI

```bash
# Full CI pipeline
flutter clean && flutter pub get && \
  dart run build_runner build --delete-conflicting-outputs && \
  flutter analyze && \
  dart format --set-exit-if-changed . && \
  flutter test --coverage

# Check coverage threshold (example: 80%)
lcov --summary coverage/lcov.info | grep "lines" | awk '{print $2}'

# Dependency vulnerability scan
flutter pub audit
```

## Platform-specific Debug

```bash
# Android logcat (Flutter logs)
adb logcat -s flutter

# iOS logs (từ Xcode console hoặc)
flutter logs

# Platform channel debug
flutter run --verbose 2>&1 | grep -i "platform"
```

## Maintenance

```bash
# Flutter doctor (check environment)
flutter doctor -v

# Clean build cache
flutter clean

# Full rebuild
flutter clean && flutter pub get && dart run build_runner build --delete-conflicting-outputs

# Upgrade Flutter SDK
flutter upgrade

# Switch channel
flutter channel stable

# Precache platforms
flutter precache --ios --android --web

# Check Flutter version
flutter --version
```

## Project Creation

```bash
# Create new project
flutter create --org com.example my_app

# Create package
flutter create --template=package my_package

# Create plugin
flutter create --template=plugin my_plugin

# Create with specific platforms
flutter create --platforms=android,ios,web my_app

# Enable/disable platform
flutter config --enable-web
flutter config --enable-macos-desktop
```

## Debug Workflow

```bash
# 1. Reproduce issue
# 2. Check flutter analyze output
flutter analyze
# 3. Capture logs
flutter logs > debug_log.txt
# 4. Open DevTools
flutter pub global run devtools
# 5. Profile CPU/Memory/Network
# 6. Write regression test
flutter test test/regression/
```

## Optimization Workflow

```bash
# 1. Establish baseline
flutter run --profile
# 2. Open DevTools → Performance tab
# 3. Record timeline, identify jank frames (> 16ms)
# 4. Apply focused fix (one change at a time)
# 5. Re-profile same scenario
# 6. Compare frame times
# 7. If < 5% improvement → revert
```

## Signing & Release

```bash
# Generate keystore (Android)
keytool -genkey -v -keystore upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload

# Verify APK
apksigner verify --verbose build/app/outputs/flutter-apk/app-release.apk

# iOS distribution (fastlane)
cd ios && fastlane release && cd ..
```
