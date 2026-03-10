# iOS / Swift — Skills (Terminal Commands)

## Build & Run

```bash
# Build (Xcode CLI)
xcodebuild -workspace App.xcworkspace -scheme App -configuration Debug build

# Run on simulator
xcrun simctl boot "iPhone 15 Pro"
xcodebuild -workspace App.xcworkspace -scheme App -destination 'platform=iOS Simulator,name=iPhone 15 Pro' build

# Clean build
xcodebuild clean -workspace App.xcworkspace -scheme App

# Archive for distribution
xcodebuild archive -workspace App.xcworkspace -scheme App -archivePath build/App.xcarchive
```

## Swift Package Manager

```bash
# Resolve dependencies
swift package resolve

# Update dependencies
swift package update

# Generate Xcode project
swift package generate-xcodeproj

# Add dependency
# Edit Package.swift: .package(url: "https://...", from: "1.0.0")
```

## Testing

```bash
# Run all tests
xcodebuild test -workspace App.xcworkspace -scheme App -destination 'platform=iOS Simulator,name=iPhone 15 Pro'

# Run specific test
xcodebuild test -workspace App.xcworkspace -scheme App -only-testing:AppTests/AuthViewModelTests

# Code coverage
xcodebuild test -enableCodeCoverage YES -workspace App.xcworkspace -scheme App
```

## Code Quality

```bash
# SwiftLint
swiftlint lint --strict

# SwiftLint autocorrect
swiftlint lint --fix

# SwiftFormat
swiftformat . --config .swiftformat
```

## Simulator

```bash
# List simulators
xcrun simctl list devices

# Boot simulator
xcrun simctl boot "iPhone 15 Pro"

# Install app
xcrun simctl install booted build/App.app

# Screenshot
xcrun simctl io booted screenshot screenshot.png

# Open URL (deep link test)
xcrun simctl openurl booted "myapp://profile/123"

# Reset simulator
xcrun simctl erase "iPhone 15 Pro"
```

## Profiling

```bash
# Open Instruments
open /Applications/Xcode.app/Contents/Applications/Instruments.app

# Memory graph
# Xcode → Debug Navigator → Memory → Export Memory Graph

# Leaks (CLI)
leaks --atExit -- ./App
```

## Deployment

```bash
# Fastlane beta
bundle exec fastlane beta

# TestFlight upload
xcrun altool --upload-app -f App.ipa -t ios -u "email@example.com" -p "@keychain:AC_PASSWORD"

# App Store Connect API
xcrun notarytool submit App.zip --apple-id "email" --team-id "TEAM_ID"
```

## Certificates & Signing

```bash
# List signing identities
security find-identity -v -p codesigning

# Export provisioning profiles
ls ~/Library/MobileDevice/Provisioning\ Profiles/

# Verify signed app
codesign -vv --deep App.app
```
