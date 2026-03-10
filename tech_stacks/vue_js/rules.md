# Vue.js 3 — Rules

## Composition API (`<script setup>`)

- **Luôn dùng `<script setup>`** — không dùng Options API cho code mới
- Reactive state: `ref()` cho primitives, `reactive()` cho objects
- `computed()` cho derived state — không tính toán trong template
- `watch()` / `watchEffect()` cho side effects — cleanup trong `onUnmounted`
- Composables: tách logic tái sử dụng thành `use*.ts` files
- Props: `defineProps<T>()` với TypeScript interface, `withDefaults()` cho default values
- Emits: `defineEmits<T>()` — type-safe event declarations
- Expose: `defineExpose()` chỉ khi parent cần access child methods

## Component Architecture

- Atomic Design: `atoms/` → `molecules/` → `organisms/` → `templates/` → `pages/`
- Component naming: `PascalCase.vue`, dùng multi-word (`UserProfile`, không `Profile`)
- Props down, events up — **không mutate props trực tiếp**
- `v-model` với `defineModel()` (Vue 3.4+) cho two-way binding
- Slots: `<slot>` cho content projection, named slots cho complex layouts
- Async components: `defineAsyncComponent()` cho lazy loading

## State Management (Pinia)

- 1 store per domain/feature: `useUserStore`, `useCartStore`
- Store dùng Setup syntax (Composition API style):
  ```ts
  export const useUserStore = defineStore('user', () => {
    const user = ref<User | null>(null)
    const isLoggedIn = computed(() => !!user.value)
    async function fetchUser() { ... }
    return { user, isLoggedIn, fetchUser }
  })
  ```
- **Không** destructure store trực tiếp — dùng `storeToRefs()` để giữ reactivity
- Actions cho async operations — không gọi API trong components
- Persist plugin (`pinia-plugin-persistedstate`) cho localStorage sync

## Router (Vue Router 4)

- Routes lazy-load: `() => import('./pages/Home.vue')`
- Navigation guards: `beforeEach` cho auth check
- Route meta: `meta: { requiresAuth: true }`
- Nested routes cho layouts, named views cho complex pages
- Type-safe params với `defineProps` trong `<script setup>`

## TypeScript

- **Strict mode bật** (`strict: true` trong `tsconfig.json`)
- Interface cho Props, Emits, API response types
- `unknown` thay vì `any` — narrow bằng type guards
- Utility types: `Partial<T>`, `Pick<T>`, `Omit<T>` thay vì duplicate
- Enum → `const` object hoặc union types (tree-shakeable)

## Vite Config

- `vite.config.ts` — TypeScript config
- Path aliases: `@/` → `src/` (config cả `vite.config.ts` và `tsconfig.json`)
- Env variables: `.env`, `.env.production` — prefix `VITE_`
- Proxy API: `server.proxy` cho dev, tránh CORS
- Build: `rollupOptions.output.manualChunks` cho code splitting
- Plugins: `@vitejs/plugin-vue`, `unplugin-auto-import`, `unplugin-vue-components`

## Styling

- Scoped styles: `<style scoped>` mặc định
- CSS Modules: `<style module>` khi cần dynamic class binding
- CSS variables cho theming: `var(--color-primary)`
- Utility-first (Tailwind) hoặc component library (PrimeVue, Vuetify)

## Project Structure

```
src/
├── assets/          → images, fonts, global CSS
├── components/      → reusable UI components
│   ├── atoms/
│   ├── molecules/
│   └── organisms/
├── composables/     → use*.ts (shared logic)
├── layouts/         → page layouts
├── pages/           → route pages (views)
├── router/          → route definitions
├── stores/          → Pinia stores
├── services/        → API calls (axios/fetch wrappers)
├── types/           → TypeScript interfaces/types
├── utils/           → helper functions
├── App.vue
└── main.ts
```

## General

- ESLint + Prettier — format on save
- File naming: `PascalCase.vue` components, `camelCase.ts` utilities
- Barrel exports: `index.ts` per feature folder
- i18n: `vue-i18n` — không hardcode strings
- Error boundary: `onErrorCaptured` hook hoặc global error handler
