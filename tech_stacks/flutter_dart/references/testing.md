# Flutter / Dart — Testing & Performance Reference

## Widget Testing

```dart
testWidgets('should show loading', (tester) async {
  await tester.pumpWidget(
    BlocProvider<AuthBloc>(
      create: (_) => mockBloc,
      child: const LoginScreen(),
    ),
  );
  expect(find.byType(CircularProgressIndicator), findsOneWidget);
});
```

## Performance

- `const` constructors for immutable widgets
- `RepaintBoundary` for heavy subtrees
- `ListView.builder` over `ListView` for large lists
- Avoid opacity animations — use `FadeTransition` instead
- Profile with `flutter run --profile` and DevTools

## Security

- `flutter_secure_storage` for tokens
- Certificate pinning with `SecurityContext`
- Code obfuscation: `flutter build apk --obfuscate --split-debug-info=symbols/`
