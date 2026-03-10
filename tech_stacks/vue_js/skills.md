# Vue.js 3 — Skills (Terminal Commands)

## Project Setup

```bash
# Tạo project mới (Vite)
npm create vite@latest my-app -- --template vue-ts

# Tạo project (create-vue — official)
npm create vue@latest

# Install dependencies
npm install
```

## Development

```bash
# Dev server (hot reload)
npm run dev

# Dev server custom port
npm run dev -- --port 3000

# Dev server expose LAN
npm run dev -- --host

# Preview production build locally
npm run preview
```

## Build

```bash
# Production build
npm run build

# Build với mode cụ thể
npm run build -- --mode staging

# Analyze bundle size
npx vite-bundle-visualizer

# Build output tại: dist/
```

## Code Quality

```bash
# Lint check
npm run lint

# Lint + auto-fix
npm run lint -- --fix

# Type check (vue-tsc)
npm run type-check
npx vue-tsc --noEmit

# Format (Prettier)
npx prettier --write "src/**/*.{vue,ts,tsx,css}"

# Format check only (CI)
npx prettier --check "src/**/*.{vue,ts,tsx,css}"
```

## Testing

```bash
# Unit tests (Vitest)
npm run test
npx vitest

# Watch mode
npx vitest --watch

# Coverage
npx vitest --coverage

# Run file cụ thể
npx vitest run src/components/__tests__/Button.test.ts

# E2E tests (Cypress)
npx cypress open
npx cypress run

# E2E tests (Playwright)
npx playwright test
npx playwright test --ui
```

## Dependencies

```bash
# Install package
npm install <package>

# Install dev dependency
npm install --save-dev <package>

# Uninstall
npm uninstall <package>

# Outdated check
npm outdated

# Update all (minor)
npm update

# Security audit
npm audit
npm audit fix
```

## Pinia (State Management)

```bash
# Install
npm install pinia

# Persist plugin
npm install pinia-plugin-persistedstate
```

## Vue Router

```bash
# Install
npm install vue-router@4
```

## i18n

```bash
# Install
npm install vue-i18n@9

# Extract keys (nếu dùng tooling)
npx vue-i18n-extract report --vueFiles './src/**/*.vue' --languageFiles './src/locales/**/*.json'
```

## API & HTTP

```bash
# Axios
npm install axios

# Generate API types từ OpenAPI
npx openapi-typescript https://api.example.com/openapi.json -o src/types/api.d.ts
```

## Tooling Setup

```bash
# ESLint + Vue plugin
npm install --save-dev eslint @eslint/js eslint-plugin-vue

# Prettier
npm install --save-dev prettier

# Vitest
npm install --save-dev vitest @vue/test-utils jsdom

# Auto-import plugin
npm install --save-dev unplugin-auto-import unplugin-vue-components
```

## Docker & Deploy

```bash
# Build Docker image
docker build -t my-vue-app .

# Serve dist với simple server
npx serve dist

# Deploy to Netlify
npx netlify deploy --prod --dir=dist

# Deploy to Vercel
npx vercel --prod
```

## Misc

```bash
# Vue Devtools (standalone)
npx @vue/devtools

# Check Vue version
npm list vue

# Check Vite version
npx vite --version

# Clean cache
rm -rf node_modules/.vite
rm -rf node_modules && npm install
```
