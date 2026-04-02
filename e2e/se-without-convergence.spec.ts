/**
 * SE without Convergence — verifies that SE surfaces work when Convergence is not running.
 *
 * All checks in a single browser session to avoid WSL2 Chromium
 * --single-process crashes on context teardown.
 *
 * Requirements:
 *   - NLQ (8005/3005) + DCL (8004) running
 *   - Convergence (8010) NOT running
 *   - SE pipeline has run (triples ingested into DCL)
 */

import { test, expect } from 'playwright/test';

test('SE surfaces work without Convergence: Ask + Dashboard + Health', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (text.includes('The width(-1)') || text.includes('The height(-1)')) return;
    if (text.includes('net::ERR_NAME_NOT_RESOLVED') || text.includes('Failed to load resource')) return;
    if (text.includes('Encountered two children with the same key')) return;
    consoleErrors.push(text);
  });
  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });

  // ── 1. Health check: DCL connected ──
  const healthRes = await page.request.get('/api/v1/health');
  expect(healthRes.ok()).toBeTruthy();
  const healthData = await healthRes.json();
  expect(healthData.dcl_available).toBe(true);
  console.log(`[SE-no-conv] Health: status=${healthData.status}, dcl=${healthData.dcl_available}`);

  // ── 2. Ask: loads and answers a query ──
  await page.goto('/', { waitUntil: 'load' });

  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  await searchInput.fill("What's revenue?");
  await searchInput.press('Enter');

  const answerText = page.locator('p.text-slate-200.text-sm.leading-relaxed:not(.line-clamp-2)');
  await expect(answerText).toBeVisible({ timeout: 30_000 });
  const answer = await answerText.textContent();
  expect(answer).toBeTruthy();
  console.log(`[SE-no-conv] Ask answer: "${answer}"`);

  // No console errors mentioning Convergence or 503
  const convergenceErrors = consoleErrors.filter(
    (e) => e.toLowerCase().includes('convergence') || e.includes('503')
  );
  expect(convergenceErrors).toEqual([]);

  // ── 3. Dashboard: loads ──
  await page.locator('#nav-tab-dashboard').click();

  const gridLayout = page.locator('.react-grid-layout');
  await expect(gridLayout).toBeVisible({ timeout: 30_000 });

  const cells = page.locator('.react-grid-layout .react-grid-item');
  await expect(cells.first()).toBeVisible({ timeout: 15_000 });
  console.log(`[SE-no-conv] Dashboard widgets: ${await cells.count()}`);
});
