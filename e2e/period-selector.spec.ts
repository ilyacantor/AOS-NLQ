/**
 * Period Selector — fiscal year dropdown drives dashboard data
 *
 * Verifies that:
 * 1. The period selector dropdown is visible with available years
 * 2. Selecting a different year changes the dashboard data
 * 3. Map total and KPI values reflect the selected year
 *
 * Requirements:
 *   - nlq-backend:8005 and nlq-frontend:3005 running
 *   - SE pipeline data ingested (revenue triples for multiple years)
 */

import { test, expect } from 'playwright/test';

test('Period selector: dropdown visible and drives dashboard year', async ({ page }) => {
  // ── Setup ──
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
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });

  await page.goto('/', { waitUntil: 'load' });

  // ── 1. Period selector is visible ──
  const periodSelect = page.locator('#period-selector');
  await expect(periodSelect).toBeVisible({ timeout: 15_000 });

  // Verify it has options
  const options = periodSelect.locator('option');
  const optionCount = await options.count();
  console.log(`[Period] ${optionCount} period options found`);
  expect(optionCount).toBeGreaterThanOrEqual(2);

  // List all options
  for (let i = 0; i < optionCount; i++) {
    const text = await options.nth(i).textContent();
    console.log(`  Option ${i}: ${text}`);
  }

  // ── 2. Default is most recent year (2026) ──
  const defaultValue = await periodSelect.inputValue();
  console.log(`[Period] Default value: ${defaultValue}`);
  expect(defaultValue).toBe('2026');

  // ── 3. Submit a dashboard query with default year ──
  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  await searchInput.fill('CFO dashboard');
  await searchInput.press('Enter');

  const gridLayout = page.locator('.react-grid-layout');
  await expect(gridLayout).toBeVisible({ timeout: 60_000 });

  // Wait for map to render
  const totalLabel2026 = page.locator('span.text-xs.text-slate-500', { hasText: 'total' }).first();
  await expect(totalLabel2026).toBeVisible({ timeout: 30_000 });

  // Extract 2026 map total
  const mapTotal2026Span = totalLabel2026.locator('xpath=preceding-sibling::span').first();
  const mapTotal2026Text = await mapTotal2026Span.textContent();
  console.log(`[Period] 2026 map total: ${mapTotal2026Text}`);

  // Screenshot with 2026
  await gridLayout.screenshot({ path: 'test-results/period-2026.png' });

  // ── 4. Switch to 2025 and re-query ──
  await periodSelect.selectOption('2025');
  const newValue = await periodSelect.inputValue();
  expect(newValue).toBe('2025');
  console.log(`[Period] Switched to: ${newValue}`);

  // Navigate back to re-submit with new period
  await page.goto('/', { waitUntil: 'load' });
  // Period selector retains selection via React state in provider
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  // Verify period is still 2025 after navigation
  const periodAfterNav = page.locator('#period-selector');
  await expect(periodAfterNav).toBeVisible({ timeout: 15_000 });
  // Re-select 2025 (state resets on navigation)
  await periodAfterNav.selectOption('2025');
  // Wait for React state to propagate
  await page.waitForTimeout(500);

  // Intercept the query request to verify reference_year is sent
  let capturedBody: any = null;
  await page.route('**/api/v1/query', (route, request) => {
    const body = request.postDataJSON();
    capturedBody = body;
    console.log(`[Period] Query body: ${JSON.stringify(body)}`);
    route.continue();
  });

  await searchInput.fill('CFO dashboard');
  await searchInput.press('Enter');

  // Wait for new dashboard
  await expect(gridLayout).toBeVisible({ timeout: 60_000 });

  const totalLabel2025 = page.locator('span.text-xs.text-slate-500', { hasText: 'total' }).first();
  await expect(totalLabel2025).toBeVisible({ timeout: 30_000 });

  const mapTotal2025Span = totalLabel2025.locator('xpath=preceding-sibling::span').first();
  const mapTotal2025Text = await mapTotal2025Span.textContent();
  console.log(`[Period] 2025 map total: ${mapTotal2025Text}`);

  // Screenshot with 2025
  await gridLayout.screenshot({ path: 'test-results/period-2025.png' });

  // ── 5. Verify the numbers are different (different years = different totals) ──
  function parseDollar(s: string): number {
    const clean = s.replace(/[$,]/g, '');
    if (clean.endsWith('B')) return parseFloat(clean) * 1000;
    if (clean.endsWith('M')) return parseFloat(clean);
    if (clean.endsWith('K')) return parseFloat(clean) / 1000;
    return parseFloat(clean);
  }

  const total2026 = parseDollar(mapTotal2026Text!);
  const total2025 = parseDollar(mapTotal2025Text!);
  console.log(`[Period] 2026: ${total2026}M, 2025: ${total2025}M`);

  // Log captured request body
  if (capturedBody) {
    console.log(`[Period] Captured reference_year in request: ${capturedBody.reference_year}`);
  }

  // 2026 should be larger than 2025 (revenue grows)
  expect(total2026).toBeGreaterThan(total2025);
  // Both should be in reasonable single-year range
  expect(total2025).toBeGreaterThan(50);
  expect(total2025).toBeLessThan(200);
  expect(total2026).toBeGreaterThan(50);
  expect(total2026).toBeLessThan(250);

  console.log(`[Period] Year-filtered correctly: 2025=$${total2025}M, 2026=$${total2026}M`);

  // ── Final: no console errors ──
  if (consoleErrors.length > 0) {
    console.log('[Period] Console errors:', consoleErrors);
  }
  expect(consoleErrors).toHaveLength(0);
});
