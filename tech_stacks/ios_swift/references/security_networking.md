# iOS / Swift — Security & Networking Examples

## Keychain Access

```swift
func saveToken(_ token: String) throws {
    let data = Data(token.utf8)
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrAccount as String: "authToken",
        kSecValueData as String: data,
        kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
    ]
    SecItemDelete(query as CFDictionary)
    let status = SecItemAdd(query as CFDictionary, nil)
    guard status == errSecSuccess else { throw KeychainError.saveFailed }
}
```

## URLSession with async/await

```swift
func fetchUser(id: String) async throws -> User {
    let url = baseURL.appendingPathComponent("users/\(id)")
    var request = URLRequest(url: url)
    request.setValue("Bearer \(try await tokenManager.getToken())", forHTTPHeaderField: "Authorization")
    
    let (data, response) = try await URLSession.shared.data(for: request)
    
    guard let httpResponse = response as? HTTPURLResponse,
          (200...299).contains(httpResponse.statusCode) else {
        throw NetworkError.invalidResponse
    }
    
    return try JSONDecoder().decode(User.self, from: data)
}
```

## Certificate Pinning

```swift
class PinningDelegate: NSObject, URLSessionDelegate {
    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge) async 
        -> (URLSession.AuthChallengeDisposition, URLCredential?) {
        guard let trust = challenge.protectionSpace.serverTrust,
              SecTrustEvaluateWithError(trust, nil),
              let cert = SecTrustGetCertificateAtIndex(trust, 0) else {
            return (.cancelAuthenticationChallenge, nil)
        }
        let pinnedHash = "SHA256_HASH_HERE"
        let serverHash = sha256(SecCertificateCopyData(cert) as Data)
        return serverHash == pinnedHash 
            ? (.useCredential, URLCredential(trust: trust)) 
            : (.cancelAuthenticationChallenge, nil)
    }
}
```
