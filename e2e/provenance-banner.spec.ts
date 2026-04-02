/**
 * Provenance banner — verifies Dashboard shows provenance for the active pipeline state,
 * and Ask does NOT show the banner (Ask has the snapshot selector instead).
 *
 * All checks in a single browser session to avoid WSL2 Chromium
 * --single-process crashes on context teardown.
 *
 * Requirements:
 *   - NLQ (8005/3005) + DCL (8004) running
 *   - At least one pipeline run ingested into DCL (via REST ingest path)
 */

import { test, expect } from 'playwright/test';

test('Provenance banner: visible on Dashboard, hidden on Ask', async ({ page }) => {
  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });

  await page.goto('/', { waitUntil: 'load' });

  // Wait for data to load
  await page.waitForTimeout(2_000);

  // ── 1. Ask: no provenance banner ──
  const bannerEntity = page.locator('text=Entity:');
  await expect(bannerEntity).not.toBeVisible();
  console.log('[provenance] Ask: no banner visible (correct)');

  // ── 2. Ask: snapshot selector visible ──
  const selector = page.locator('#snapshot-selector');
  await expect(selector).toBeVisible({ timeout: 10_000 });
  console.log('[provenance] Ask: selector visible (correct)');

  // ── 3. Dashboard: provenance banner visible ──
  await page.locator('#nav-tab-dashboard').click();
  await page.waitForTimeout(2_000);

  // Banner shows entity, snapshot, and timestamp labels
  await expect(page.locator('text=Snapshot:')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('text=Updated:')).toBeVisible({ timeout: 10_000 });
  console.log('[provenance] Dashboard banner visible with provenance data');
});
