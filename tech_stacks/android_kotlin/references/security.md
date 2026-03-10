# Android / Kotlin — Security Reference

## Encryption & Storage

- `EncryptedSharedPreferences` (AES-256-GCM) cho tokens — never plain SharedPreferences
- Android Keystore cho signing, encryption, biometric-bound crypto
- Zeroize sensitive `ByteArray` after use — không dùng `String` cho private key

## Screen Protection

- `FLAG_SECURE` cho sensitive screens (screenshot/recording protection)
- Clipboard TTL — clear sau X giây

## Build Config

- R8/ProGuard: obfuscate release, remove debug logs
- `android:allowBackup="false"`, `android:usesCleartextTraffic="false"`

## Network

- HTTPS-only, certificate pinning per flavor
- OkHttp interceptors order: Logging (DEBUG only) → Auth → Retry → Cache
- Token refresh: single-flight safe với `Mutex`, prevent duplicate 401 refresh
- Không log: Authorization header, PII, raw JSON response
