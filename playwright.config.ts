import { defineConfig } from 'playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:5000',
    headless: true,
    viewport: { width: 1280, height: 720 },
    launchOptions: {
      executablePath: '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
        '--disable-software-rasterizer',
        '--single-process',
      ],
    },
  },
  /* Do NOT auto-start webServer — we manage servers externally */
});
