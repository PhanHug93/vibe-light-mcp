# React Native — Rules

## Architecture

- **Feature-based structure**: `src/features/{name}/`, each with screens, components, hooks, services
- **Shared modules**: `src/shared/` for cross-feature utilities, theme, navigation types
- **Clean layers**: Screen → Hook/ViewModel → Service/API → Storage
- **No circular imports**: features never import from other features

## Navigation (React Navigation)

- **Type-safe**: Define `RootStackParamList` for all navigators
- **Library**: `@react-navigation/native-stack` for native performance
- **Centralized**: All navigators in `src/navigation/`
- **Nesting**: Tab inside Stack, Drawer wrapping Tab when needed
- **Deep Linking**: Configure `linking` prop in `NavigationContainer`
- **Validate**: Always validate `route.params` before fetching data

## State Management

- **Local state**: `useState` / `useReducer` for component-scoped state
- **Global state**: Zustand or Redux Toolkit — pick one per project
- **Server state**: React Query / TanStack Query for API cache
- **No prop drilling**: Use context or state management for shared state
- **Immutable updates**: Always spread/create new objects in reducers

## Component Patterns

- **Functional only**: No class components
- **Custom hooks**: Extract logic into `use*` hooks
- **Memoization**: `React.memo` for heavy lists, `useMemo`/`useCallback` for stable refs
- **Design tokens**: Centralized theme with `useTheme()` hook
- **Platform-specific**: Use `Platform.select()` or `.ios.tsx`/`.android.tsx` files

## Performance

- **FlatList**: Always use `keyExtractor`, `getItemLayout`, `removeClippedSubviews`
- **No inline styles**: Use `StyleSheet.create()` — cached at module level
- **Hermes**: Enable for production builds (default in recent RN)
- **Bundle**: Use `react-native-bundle-visualizer` to audit size
- **Images**: Use `react-native-fast-image` for caching

## Error Handling

- **Error Boundaries**: Wrap navigation stacks with React Error Boundaries
- **API errors**: Typed error responses, toast/alert for user-facing errors
- **Crash reporting**: Sentry or Crashlytics integration mandatory

## Security

- **Secrets**: `react-native-keychain` for tokens — never AsyncStorage for sensitive data
- **SSL Pinning**: `react-native-ssl-pinning` for production
- **Code Obfuscation**: Enable Hermes bytecode + ProGuard (Android) + bitcode (iOS)
- **No logs in prod**: Strip `console.log` in release builds

## Anti-Patterns ❌

- Class components
- Inline styles in render
- `any` type in TypeScript
- Direct API calls in components (use hooks/services)
- Storing tokens in AsyncStorage
- Missing `keyExtractor` in FlatList
