# React Native — Navigation & State Examples

## Type-Safe Navigation

```typescript
type RootStackParamList = {
  Home: undefined;
  Profile: { userId: string };
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

function AppNavigator() {
  return (
    <Stack.Navigator>
      <Stack.Screen name="Home" component={HomeScreen} />
      <Stack.Screen name="Profile" component={ProfileScreen} />
    </Stack.Navigator>
  );
}
```

## Deep Linking Config

```typescript
const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ['myapp://', 'https://myapp.com'],
  config: {
    screens: {
      Home: '',
      Profile: 'profile/:userId',
    },
  },
};
```

## Zustand Store

```typescript
interface AuthStore {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isLoading: false,
  login: async (email, password) => {
    set({ isLoading: true });
    const user = await authService.login(email, password);
    set({ user, isLoading: false });
  },
  logout: () => set({ user: null }),
}));
```

## React Query Usage

```typescript
const useUser = (userId: string) => {
  return useQuery({
    queryKey: ['user', userId],
    queryFn: () => api.getUser(userId),
    staleTime: 5 * 60 * 1000,
  });
};
```
