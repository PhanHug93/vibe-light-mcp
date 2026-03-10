# Kotlin Multiplatform — Skills (Terminal Commands)

## Build — Shared Module

```bash
# Build shared module (all targets)
./gradlew :shared:build

# Build shared chỉ cho Android
./gradlew :shared:compileKotlinAndroid

# Build shared chỉ cho iOS
./gradlew :shared:compileKotlinIosArm64
./gradlew :shared:compileKotlinIosSimulatorArm64

# Build iOS framework
./gradlew :shared:assembleSHAREDXCFramework

# Build release framework
./gradlew :shared:assembleReleaseXCFramework
```

## Build — Platform Apps

```bash
# Android app
./gradlew :androidApp:assembleDebug
./gradlew :androidApp:assembleRelease

# iOS app (từ Xcode CLI)
xcodebuild -workspace iosApp/iosApp.xcworkspace \
  -scheme iosApp \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  build

# Clean all
./gradlew clean
```

## CocoaPods Integration

```bash
# Install CocoaPods (nếu chưa có)
sudo gem install cocoapods

# Generate Podspec từ Gradle
./gradlew :shared:podspec

# Install pods cho iOS project
cd iosApp && pod install && cd ..

# Update pods
cd iosApp && pod update && cd ..

# Deintegrate + reinstall (khi lỗi)
cd iosApp && pod deintegrate && pod install && cd ..

# Sync Kotlin framework qua CocoaPods
./gradlew :shared:podInstall
```

## SPM (Swift Package Manager) — Alternative

```bash
# Build XCFramework cho SPM distribution
./gradlew :shared:assembleSHAREDXCFramework

# Output tại:
# shared/build/XCFrameworks/release/SHARED.xcframework
```

## Testing

```bash
# All shared tests
./gradlew :shared:allTests

# Common tests only
./gradlew :shared:testDebugUnitTest        # Android JVM tests
./gradlew :shared:iosSimulatorArm64Test    # iOS simulator tests

# Android app tests
./gradlew :androidApp:testDebugUnitTest

# Test với report
./gradlew :shared:allTests --info
open shared/build/reports/tests/allTests/index.html
```

## Dependency Management

```bash
# Dependency tree (shared module)
./gradlew :shared:dependencies

# Outdated dependencies check
./gradlew dependencyUpdates

# Verify Kotlin version alignment
./gradlew kotlinUpgradeYarnLock
```

## Debug & Inspect

```bash
# List all Gradle tasks cho shared
./gradlew :shared:tasks --all

# Kotlin compiler metadata
./gradlew :shared:compileKotlinMetadata

# Check expect/actual linkage
./gradlew :shared:compileCommonMainKotlinMetadata

# iOS framework headers (sau khi build)
cat shared/build/bin/iosSimulatorArm64/debugFramework/SHARED.framework/Headers/SHARED.h
```

## Xcode & iOS Tooling

```bash
# List simulators
xcrun simctl list devices

# Boot simulator
xcrun simctl boot "iPhone 16"

# Install app on simulator
xcrun simctl install booted path/to/app.app

# Open Xcode workspace
open iosApp/iosApp.xcworkspace

# Xcode clean derived data
rm -rf ~/Library/Developer/Xcode/DerivedData
```

## CI/CD Essentials

```bash
# Full verification pipeline
./gradlew clean :shared:allTests :androidApp:assembleDebug :shared:assembleSHAREDXCFramework

# Generate build scan
./gradlew build --scan

# Gradle cache info
./gradlew build --build-cache --info | grep -i cache
```

## SKIE / KMP-NativeCoroutines (iOS Flow interop)

```bash
# Verify SKIE plugin applied
./gradlew :shared:generateSwiftInterface

# Check generated Swift files
ls shared/build/generated/skie/
```
