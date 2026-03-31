/**
 * Report Portal E2E — verifies that v2 report endpoints render in the browser.
 *
 * This test exercises the fix for the missing tenant_id/pipeline_run_id
 * identity pair on NLQ→DCL→Convergence v2 calls.  Before the fix,
 * every report tab showed "Error loading report data" (HTTP 422).
 *
 * All tabs are tested in a single browser session to avoid WSL2 Chromium
 * process management issues with --single-process mode.
 *
 * Requirements:
 *   - All services running via pm2 (nlq-backend:8005, nlq-frontend:3005,
 *     dcl-backend:8004, convergence-backend:8010)
 */

import { test, expect } from 'playwright/test';

test('Report Portal renders all tabs with live Convergence data (I2/I6)', async ({ page }) => {
  // Block external resources that hang in WSL
  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) {
      route.continue();
    } else {
      route.abort();
    }
  });

  // Collect console errors
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (text.includes('The width(-1)') || text.includes('The height(-1)')) return;
    if (text.includes('Failed to fetch') || text.includes('NetworkError')) return;
    if (text.includes('net::ERR_NAME_NOT_RESOLVED') || text.includes('Failed to load resource')) return;
    // React duplicate-key warnings from cross-sell/upsell list rendering (pre-existing)
    if (text.includes('Encountered two children with the same key')) return;
    consoleErrors.push(text);
  });

  // ── Navigate to Report Portal ──
  await page.goto('/', { waitUntil: 'load' });
  const reportsTab = page.locator('#nav-tab-reports');
  await expect(reportsTab).toBeVisible({ timeout: 15_000 });
  await reportsTab.click();

  // Helper: assert a report tab loaded data (table with numbers, no error banner).
  async function assertTabLoaded(tabLabel: string) {
    const errorBanner = page.locator('text=Error loading report data');
    await expect(errorBanner).not.toBeVisible({ timeout: 10_000 });
    const numericCells = page.locator('table td').filter({ hasText: /[\d,]+\.\d/ });
    await expect(numericCells.first()).toBeVisible({ timeout: 30_000 });
  }

  // ── 1. P&L (Income Statement) — default tab ──
  await assertTabLoaded('P&L');
  // Revenue line must be present
  const revenueCell = page.locator('table td').filter({ hasText: /Revenue/ }).first();
  await expect(revenueCell).toBeVisible({ timeout: 5_000 });

  // ── 2. Balance Sheet ──
  await page.locator('button').filter({ hasText: /^BS$/ }).click();
  await assertTabLoaded('BS');

  // ── 3. Cash Flow ──
  await page.locator('button').filter({ hasText: /^CF$/ }).click();
  await assertTabLoaded('CF');

  // ── 4. Combining Income Statement ──
  await page.locator('button').filter({ hasText: /^Combining$/ }).click();
  // Combining uses a different table layout — check for Meridian header
  const errorBanner = page.locator('text=Error loading report data');
  await expect(errorBanner).not.toBeVisible({ timeout: 10_000 });
  const meridianHeader = page.locator('th').filter({ hasText: /Meridian/i });
  await expect(meridianHeader).toBeVisible({ timeout: 30_000 });

  // ── 5. Cross-Sell ──
  await page.locator('button').filter({ hasText: /X-Sell/ }).click();
  await page.waitForTimeout(5_000);
  await expect(page.locator('text=Error loading')).not.toBeVisible();

  // ── 6. QofE (includes EBITDA Bridge) ──
  await page.locator('button').filter({ hasText: /QofE/ }).click();
  await page.waitForTimeout(5_000);
  await expect(page.locator('text=Error loading')).not.toBeVisible();
  // EBITDA Bridge sub-tab should render
  const bridgeTab = page.locator('button').filter({ hasText: /EBITDA Bridge/ });
  await expect(bridgeTab).toBeVisible({ timeout: 10_000 });

  // ── Final: no fatal console errors ──
  if (consoleErrors.length > 0) {
    console.log('Console errors:', consoleErrors);
  }
  expect(consoleErrors).toHaveLength(0);
});
