import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end journeys against the production build served by the FastAPI app (as on Cloud Run),
 * with model calls replayed from the committed recordings: free, offline and deterministic.
 */
const port = 4173;

export default defineConfig({
  testDir: './e2e',
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 60_000,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${String(port)}`,
    trace: 'retain-on-failure',
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: `npm run build && uv run --project ../api uvicorn arzi.main:create_app --factory --port ${String(port)}`,
    url: `http://127.0.0.1:${String(port)}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      ARZI_STATIC_DIR: 'dist',
      ARZI_LLM_MODE: 'replay',
      ARZI_REPLAY_DELAY_MS: '0',
      ARZI_DEMO_CASES_ENABLED: 'true',
    },
  },
});
