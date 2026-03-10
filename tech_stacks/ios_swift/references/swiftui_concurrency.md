# iOS / Swift — SwiftUI & Concurrency Examples

## SwiftUI ViewModel

```swift
@MainActor
final class ProfileViewModel: ObservableObject {
    @Published private(set) var state: ViewState = .loading
    
    enum ViewState {
        case loading
        case loaded(User)
        case error(String)
    }
    
    private let userService: UserServiceProtocol
    
    init(userService: UserServiceProtocol) {
        self.userService = userService
    }
    
    func loadUser(id: String) async {
        state = .loading
        do {
            let user = try await userService.fetchUser(id: id)
            state = .loaded(user)
        } catch {
            state = .error(error.localizedDescription)
        }
    }
}
```

## NavigationStack (iOS 16+)

```swift
struct ContentView: View {
    @State private var path = NavigationPath()
    
    var body: some View {
        NavigationStack(path: $path) {
            HomeView()
                .navigationDestination(for: User.self) { user in
                    ProfileView(user: user)
                }
                .navigationDestination(for: String.self) { id in
                    DetailView(id: id)
                }
        }
    }
}
```

## Actor for Thread Safety

```swift
actor TokenManager {
    private var token: String?
    private var refreshTask: Task<String, Error>?
    
    func getToken() async throws -> String {
        if let token, !isExpired(token) { return token }
        
        if let task = refreshTask {
            return try await task.value
        }
        
        let task = Task { try await refreshToken() }
        refreshTask = task
        let newToken = try await task.value
        refreshTask = nil
        return newToken
    }
}
```

## Combine Publisher

```swift
class AuthViewModel: ObservableObject {
    @Published var email = ""
    @Published var password = ""
    @Published var isValid = false
    
    private var cancellables = Set<AnyCancellable>()
    
    init() {
        Publishers.CombineLatest($email, $password)
            .map { !$0.isEmpty && $1.count >= 8 }
            .assign(to: &$isValid)
    }
}
```
