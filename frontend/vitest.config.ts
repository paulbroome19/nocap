import { defineConfig } from 'vitest/config'

// Lightweight config for unit tests (no browser). JSX modules (the route table)
// import fine under esbuild's automatic runtime; no DOM is needed for route
// matching, so the default node environment is used.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
