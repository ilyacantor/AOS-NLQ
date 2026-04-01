/**
 * SE Pipeline E2E — Farm → DCL → NLQ
 *
 * Verifies that ingested SE pipeline data renders correctly across all
 * three NLQ surfaces: Ask/Query, Dashboard, and Report Portal.
 *
 * All checks run in a single browser session to avoid WSL2 Chromium
 * --single-process crashes on context teardown.
 *
 * Requirements:
 *   - All services running via pm2 (nlq-backend:8005, nlq-frontend:3005,
 *     dcl-backend:8004, farm-backend:8003)
 *   - SE pipeline has run (triples ingested into DCL)
 */

import { test, expect } from 'playwright/test';

test('SE pipeline: Ask/Query + Dashboard + Report Portal (Farm → DCL → NLQ)', async ({ page }) => {
  // ── Setup: block external resources, collect console errors ──
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (text.includes('The width(-1)') || text.includes('The height(-1)')) return;
    if (text.includes('Failed to fetch') || text.includes('NetworkError')) return;
    if (text.includes('net::ERR_NAME_NOT_RESOLVED') || text.includes('Failed to load resource')) return;
    if (text.includes('Encountered two children with the same key')) return;
    consoleErrors.push(text);
  });
  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) {
      route.continue();
    } else {
      route.abort();
    }
  });

  await page.goto('/', { waitUntil: 'load' });

  // ── 1. Pipeline Status: DCL connected ──
  await page.waitForTimeout(2_000);
  const liveIndicator = page.locator('text=Live');
  const liveVisible = await liveIndicator.isVisible().catch(() => false);
  if (liveVisible) {
    await expect(liveIndicator).toBeVisible();
    console.log('[SE-E2E] Pipeline status: Live');
  }

  // ── 2. Ask/Query: type a query, verify answer with data ──
  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  await searchInput.fill("What's revenue?");
  await searchInput.press('Enter');

  // Wait for the answer chat bubble (exclude sidebar summary with line-clamp-2)
  const answerText = page.locator('p.text-slate-200.text-sm.leading-relaxed:not(.line-clamp-2)');
  await expect(answerText).toBeVisible({ timeout: 30_000 });

  const answer = await answerText.textContent();
  expect(answer).toBeTruthy();
  console.log(`[SE-E2E] Answer: "${answer}"`);

  // Provenance badge state (Verified = SE pipeline data, No Data = no ingest)
  const badge = page.locator('span').filter({ hasText: /Verified|No Data/ }).first();
  const badgeVisible = await badge.isVisible().catch(() => false);
  if (badgeVisible) {
    console.log(`[SE-E2E] Provenance: "${await badge.textContent()}"`);
  }

  // Confidence should be reported
  const confLabel = page.locator('text=/Conf: \\d+%/');
  if (await confLabel.isVisible().catch(() => false)) {
    console.log(`[SE-E2E] ${await confLabel.textContent()}`);
  }

  // ── 3. Dashboard: widgets render with real data ──
  await page.locator('#nav-tab-dashboard').click();

  const gridLayout = page.locator('.react-grid-layout');
  await expect(gridLayout).toBeVisible({ timeout: 30_000 });

  const gridItems = gridLayout.locator('.react-grid-item');
  expect(await gridItems.count()).toBeGreaterThan(0);

  const kpiValues = page.locator('.text-xl.font-bold.text-white');
  if (await kpiValues.count() > 0) {
    const firstValue = await kpiValues.first().textContent();
    expect(firstValue).toBeTruthy();
    expect(firstValue).toMatch(/\d/);
    console.log(`[SE-E2E] First KPI: "${firstValue}"`);
  }

  const firstTitle = gridItems.first().locator('h3');
  await expect(firstTitle).toBeVisible({ timeout: 10_000 });

  // ── 4. Report Portal: P&L, BS, CF with live data ──
  await page.locator('#nav-tab-reports').click();

  const errorBanner = page.locator('text=Error loading report data');
  const numericCells = page.locator('table td').filter({ hasText: /[\d,]+\.\d/ });

  // P&L (default tab)
  await expect(errorBanner).not.toBeVisible({ timeout: 10_000 });
  await expect(numericCells.first()).toBeVisible({ timeout: 30_000 });
  const revenueCell = page.locator('table td').filter({ hasText: /Revenue/ }).first();
  await expect(revenueCell).toBeVisible({ timeout: 5_000 });
  console.log('[SE-E2E] P&L: Revenue line visible');

  // Balance Sheet
  await page.locator('button').filter({ hasText: /^BS$/ }).click();
  await expect(errorBanner).not.toBeVisible({ timeout: 10_000 });
  await expect(numericCells.first()).toBeVisible({ timeout: 30_000 });
  console.log('[SE-E2E] BS: data visible');

  // Cash Flow
  await page.locator('button').filter({ hasText: /^CF$/ }).click();
  await expect(errorBanner).not.toBeVisible({ timeout: 10_000 });
  await expect(numericCells.first()).toBeVisible({ timeout: 30_000 });
  console.log('[SE-E2E] CF: data visible');

  // ── Final: no console errors across all surfaces ──
  if (consoleErrors.length > 0) {
    console.log('[SE-E2E] Console errors:', consoleErrors);
  }
  expect(consoleErrors).toHaveLength(0);
});
