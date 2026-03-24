import { defineConfig } from '@playwright/test';

/**
 * Playwright configuration for the Enterprise FizzBuzz Platform E2E test suite.
 *
 * Configured for headless Chromium execution against the Next.js development
 * server. The static export uses a basePath of /EnterpriseFizzBuzz, so all
 * test navigation is relative to that prefix via the baseURL setting.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: {
    headless: true,
    baseURL: 'http://localhost:3000/EnterpriseFizzBuzz/',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'pnpm dev',
    port: 3000,
    reuseExistingServer: true,
    timeout: 120000,
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
