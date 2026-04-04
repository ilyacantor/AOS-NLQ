/**
 * Map Widget — revenue total filtered to reference year
 *
 * Verifies that the dashboard map widget displays region data
 * and a total that reflects the reference year (not all-time).
 *
 * Requirements:
 *   - nlq-backend:8005 and nlq-frontend:3005 running
 *   - SE pipeline data ingested (revenue triples in DCL)
 */

import { test, expect } from 'playwright/test';

test('Map widget: displays regions with year-filtered revenue total', async ({ page }) => {
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

  // ── 1. Submit a CRO dashboard query ──
  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  await searchInput.fill('Show me a sales dashboard with revenue KPI, pipeline KPI, revenue by region map, and revenue trend');
  await searchInput.press('Enter');

  // Wait for the dashboard grid
  const gridLayout = page.locator('.react-grid-layout');
  await expect(gridLayout).toBeVisible({ timeout: 60_000 });

  // ── 2. Wait for the map widget total to render ──
  // MapWidget renders: <span class="text-lg font-bold text-white">{total}</span> <span>total</span>
  const totalLabel = page.locator('span.text-xs.text-slate-500', { hasText: 'total' }).first();
  await expect(totalLabel).toBeVisible({ timeout: 30_000 });

  // ── 3. Extract the map total value ──
  const mapTotalSpan = totalLabel.locator('xpath=preceding-sibling::span').first();
  const mapTotalText = await mapTotalSpan.textContent();
  console.log(`[Map] Map total text: ${mapTotalText}`);
  expect(mapTotalText).not.toBeNull();
  expect(mapTotalText).toContain('$');

  // ── 4. Extract region legend entries ──
  // Legend region names: <span class="text-xs text-slate-400">{r.region}</span>
  const regionLabels = page.locator('span.text-xs.text-slate-400');
  const regionCount = await regionLabels.count();
  console.log(`[Map] Found ${regionCount} region labels`);

  const foundRegions: string[] = [];
  for (let i = 0; i < regionCount; i++) {
    const text = await regionLabels.nth(i).textContent();
    if (text && ['AMER', 'EMEA', 'APAC', 'LATAM'].includes(text.trim())) {
      foundRegions.push(text.trim());
    }
  }
  console.log(`[Map] Regions found: ${foundRegions.join(', ')}`);
  expect(foundRegions.length).toBeGreaterThanOrEqual(2);

  // ── 5. Verify the total is year-filtered (not inflated) ──
  // Parse dollar amount
  function parseDollar(s: string): number {
    const clean = s.replace(/[$,]/g, '');
    if (clean.endsWith('B')) return parseFloat(clean) * 1000;
    if (clean.endsWith('M')) return parseFloat(clean);
    if (clean.endsWith('K')) return parseFloat(clean) / 1000;
    return parseFloat(clean);
  }

  const mapTotal = parseDollar(mapTotalText!);
  console.log(`[Map] Parsed map total: ${mapTotal}M`);

  // The all-time sum across 2024+2025+2026 would be ~$460M.
  // A single year should be roughly $100-200M range.
  // This catches the original bug where all periods were summed.
  expect(mapTotal).toBeLessThan(250);
  expect(mapTotal).toBeGreaterThan(50);
  console.log(`[Map] Total ${mapTotal}M is within single-year range (not inflated all-time)`);

  // ── 6. Find revenue KPI for cross-check ──
  const allWidgets = gridLayout.locator('.react-grid-item');
  const widgetCount = await allWidgets.count();
  let kpiValue: number | null = null;

  for (let i = 0; i < widgetCount; i++) {
    const text = await allWidgets.nth(i).textContent();
    const lower = (text || '').toLowerCase();
    // Look for a KPI widget with "revenue" that shows a dollar value
    if (lower.includes('revenue') && !lower.includes('region') && !lower.includes('trend')) {
      const dollars = (text || '').match(/\$[\d,.]+[BMK]?/);
      if (dollars) {
        kpiValue = parseDollar(dollars[0]);
        console.log(`[Map] Revenue KPI: ${dollars[0]} (${kpiValue}M) from widget: ${(text || '').substring(0, 80)}`);
        break;
      }
    }
  }

  if (kpiValue !== null) {
    // Map yearly total should be >= quarterly KPI (map is full year, KPI may be quarterly)
    console.log(`[Map] Map total (${mapTotal}M) vs Revenue KPI (${kpiValue}M)`);
    expect(mapTotal).toBeGreaterThanOrEqual(kpiValue * 0.8);
  }

  // ── 7. Screenshots ──
  // Find the map widget container (parent of the total label)
  const mapWidget = totalLabel.locator('xpath=ancestor::div[contains(@class, "react-grid-item")]').first();
  await mapWidget.screenshot({ path: 'test-results/map-revenue.png' });
  console.log('[Map] Map widget screenshot saved to test-results/map-revenue.png');

  await gridLayout.screenshot({ path: 'test-results/dashboard-with-map.png' });
  console.log('[Map] Full dashboard screenshot saved to test-results/dashboard-with-map.png');

  // ── Final: no console errors ──
  if (consoleErrors.length > 0) {
    console.log('[Map] Console errors:', consoleErrors);
  }
  expect(consoleErrors).toHaveLength(0);
});
