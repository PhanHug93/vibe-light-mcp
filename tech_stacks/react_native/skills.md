# React Native — Skills (Terminal Commands)

## Project Setup

```bash
# Create new project
npx react-native init MyApp --template react-native-template-typescript

# Install dependencies
npm install  # or yarn

# Pod install (iOS)
cd ios && pod install && cd ..
```

## Run & Build

```bash
# Start Metro bundler
npx react-native start --reset-cache

# Run iOS
npx react-native run-ios --simulator="iPhone 15 Pro"

# Run Android
npx react-native run-android

# Release build iOS
npx react-native run-ios --configuration Release

# Release build Android
cd android && ./gradlew assembleRelease
```

## Debug

```bash
# Open React Native Debugger
open "rndebugger://set-debugger-loc?host=localhost&port=8081"

# Logcat (Android)
adb logcat *:S ReactNative:V ReactNativeJS:V

# Flipper
open /Applications/Flipper.app

# Clear caches
watchman watch-del-all && rm -rf node_modules && npm install
cd ios && pod install && cd ..
npx react-native start --reset-cache
```

## Testing

```bash
# Unit tests
npx jest --coverage

# Run specific test file
npx jest src/features/auth/__tests__/login.test.tsx

# E2E (Detox)
npx detox build --configuration ios.sim.debug
npx detox test --configuration ios.sim.debug

# TypeScript check
npx tsc --noEmit
```

## Code Quality

```bash
# ESLint
npx eslint src/ --ext .ts,.tsx --fix

# Prettier
npx prettier --write "src/**/*.{ts,tsx}"

# Bundle size analysis
npx react-native-bundle-visualizer
```

## Deployment

```bash
# iOS — Fastlane
cd ios && bundle exec fastlane beta

# Android — Fastlane  
cd android && bundle exec fastlane beta

# CodePush update
appcenter codepush release-react -a Owner/App -d Staging
```
