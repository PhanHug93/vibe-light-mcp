# Vue.js — Component Patterns Reference

## Composition API

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const count = ref(0)
const doubled = computed(() => count.value * 2)

onMounted(() => {
  console.log('Component mounted')
})
</script>
```

## Pinia Store

```typescript
export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const isLoggedIn = computed(() => !!user.value)

  async function login(email: string, password: string) {
    user.value = await authApi.login(email, password)
  }

  return { user, isLoggedIn, login }
})
```

## Router Config

```typescript
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: HomePage },
    { path: '/about', component: AboutPage, meta: { requiresAuth: true } },
  ],
})
```

## Composable Pattern

```typescript
export function useApi<T>(url: string) {
  const data = ref<T | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetch() {
    loading.value = true
    try {
      data.value = await $fetch<T>(url)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false  
    }
  }

  return { data, loading, error, fetch }
}
```
