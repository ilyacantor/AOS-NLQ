import { test, expect } from 'playwright/test';

test.use({ viewport: { width: 1600, height: 2200 } });
test('Capture dashboard for inspection', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', m => { if (m.type()==='error') consoleErrors.push(m.text()); });
  await page.goto('/', { waitUntil: 'load' });
  await page.locator('#nlq-search-input').waitFor({ state: 'visible', timeout: 15000 });
  // Click the Dashboard tab to get the default rendered dashboard
  await page.getByRole('button', { name: /Dashboard/i }).first().click();
  // Wait for any widget to appear
  await page.locator('.react-grid-layout').first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: 'test-results/dashboard-current.png', fullPage: true });
  console.log('errors:', consoleErrors);
});
