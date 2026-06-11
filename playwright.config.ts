import { defineConfig } from 'playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  retries: 2,
  use: {
    baseURL: 'http://localhost:3005',
    headless: true,
    viewport: { width: 1280, height: 720 },
    screenshot: 'only-on-failure',
    launchOptions: {
      executablePath: '/home/ilyac/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome',
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
        '--disable-software-rasterizer',
        // '--single-process' removed: it SIGTRAP-crashes chromium on
        // consecutive launches under WSL2 ("Target page, context or browser
        // has been closed" before any assertion) — the aam#55 failure class.
        // Every other repo's suite runs this chromium without the flag.
      ],
    },
  },
  /* Do NOT auto-start webServer — we manage servers externally */
});
