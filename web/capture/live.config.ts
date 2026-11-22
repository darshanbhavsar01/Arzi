import { defineConfig, devices } from '@playwright/test';

/** One-off capture of every screen from a deployed URL: `LIVE_URL=... npx playwright test -c capture/live.config.ts`. */
export default defineConfig({
  testDir: '.',
  workers: 1,
  timeout: 180_000,
  reporter: [['list']],
  use: {
    baseURL: process.env.LIVE_URL,
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
});
