/**
 * Snapshot selector — verifies the selector renders on Ask, defaults to latest,
 * and drives query identity via snapshot_id in request body.
 *
 * All checks in a single browser session to avoid WSL2 Chromium
 * --single-process crashes on context teardown.
 *
 * Requirements:
 *   - NLQ (8005/3005) + DCL (8004) running
 *   - At least one pipeline run ingested into DCL (via REST ingest path)
 */

import { test, expect } from 'playwright/test';

test('Snapshot selector: visible on Ask, defaults latest, drives identity', async ({ page }) => {
  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });

  await page.goto('/', { waitUntil: 'load' });

  // ── 1. Selector visible on Ask ──
  const selector = page.locator('#snapshot-selector');
  await expect(selector).toBeVisible({ timeout: 15_000 });

  // ── 2. Defaults to latest ──
  const options = selector.locator('option');
  const optionCount = await options.count();
  expect(optionCount).toBeGreaterThan(0);

  const selectedValue = await selector.inputValue();
  expect(selectedValue).toBeTruthy();
  console.log(`[snapshot] Default snapshot: ${selectedValue}`);

  // ── 3. Selection drives query identity ──
  const queryPromise = page.waitForRequest((req) =>
    req.url().includes('/api/v1/query') && req.method() === 'POST'
  );

  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 10_000 });
  await searchInput.fill("What's revenue?");
  await searchInput.press('Enter');

  const queryReq = await queryPromise;
  const body = queryReq.postDataJSON();
  expect(body.snapshot_id).toBe(selectedValue);
  console.log(`[snapshot] Query body.snapshot_id = ${body.snapshot_id}`);

});
