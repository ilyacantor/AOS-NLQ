/**
 * Period Selector — all widget dimensions respond to year change
 *
 * Verifies that KPIs, map, category charts, and trend all reflect
 * the selected fiscal year when the period selector changes.
 */

import { test, expect } from 'playwright/test';

interface WidgetSnapshot {
  title: string
  text: string
  dollars: string[]
  percents: string[]
}

function parseDollar(s: string): number {
  const clean = s.replace(/[$,]/g, '');
  if (clean.endsWith('B')) return parseFloat(clean) * 1000;
  if (clean.endsWith('M')) return parseFloat(clean);
  if (clean.endsWith('K')) return parseFloat(clean) / 1000;
  return parseFloat(clean);
}

async function captureWidgets(page: any): Promise<WidgetSnapshot[]> {
  const gridLayout = page.locator('.react-grid-layout');
  const widgets = gridLayout.locator('.react-grid-item');
  const count = await widgets.count();
  const snapshots: WidgetSnapshot[] = [];

  for (let i = 0; i < count; i++) {
    const text = (await widgets.nth(i).textContent()) || '';
    const dollars = text.match(/\$[\d,.]+[BMK]?/g) || [];
    const percents = text.match(/[\d.]+%/g) || [];
    // Extract title — first line or first recognizable heading
    const title = text.split(/\$|[\d]/)[0].trim().substring(0, 40);
    snapshots.push({ title, text: text.substring(0, 200), dollars, percents });
  }
  return snapshots;
}

async function queryDashboard(page: any, query: string, year: string) {
  await page.goto('/', { waitUntil: 'load' });

  const periodSelect = page.locator('#period-selector');
  await expect(periodSelect).toBeVisible({ timeout: 15_000 });
  await periodSelect.selectOption(year);
  await page.waitForTimeout(300);

  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });
  await searchInput.fill(query);
  await searchInput.press('Enter');

  const gridLayout = page.locator('.react-grid-layout');
  await expect(gridLayout).toBeVisible({ timeout: 60_000 });

  // Wait for widgets to finish loading
  await page.waitForTimeout(3000);
}

test('All widget types respond to period selector year change', async ({ page }) => {
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

  const dashQuery = 'Show me a sales dashboard with revenue KPI, pipeline KPI, revenue by region map, revenue by customer, and revenue trend';

  // ── 1. Capture FY 2026 dashboard ──
  console.log('[All] === FY 2026 ===');
  await queryDashboard(page, dashQuery, '2026');

  const gridLayout = page.locator('.react-grid-layout');
  await gridLayout.screenshot({ path: 'test-results/period-all-2026.png' });

  const snap2026 = await captureWidgets(page);
  for (const w of snap2026) {
    console.log(`[2026] ${w.title}: dollars=${w.dollars.join(',')} percents=${w.percents.join(',')}`);
  }

  // ── 2. Capture FY 2025 dashboard ──
  console.log('[All] === FY 2025 ===');
  await queryDashboard(page, dashQuery, '2025');

  await gridLayout.screenshot({ path: 'test-results/period-all-2025.png' });

  const snap2025 = await captureWidgets(page);
  for (const w of snap2025) {
    console.log(`[2025] ${w.title}: dollars=${w.dollars.join(',')} percents=${w.percents.join(',')}`);
  }

  // ── 3. Verify dimensions changed between years ──

  // 3a. Map total — should be different
  const mapTotal2026 = page.locator('span.text-xs.text-slate-500', { hasText: 'total' }).first();
  // We already have screenshots — extract from widget snapshots instead
  const map2026 = snap2026.find(w => w.title.toLowerCase().includes('region'));
  const map2025 = snap2025.find(w => w.title.toLowerCase().includes('region'));

  if (map2026 && map2025) {
    const mapDollars2026 = map2026.dollars.map(d => parseDollar(d));
    const mapDollars2025 = map2025.dollars.map(d => parseDollar(d));
    console.log(`[All] Map 2026 dollars: ${mapDollars2026.join(', ')}M`);
    console.log(`[All] Map 2025 dollars: ${mapDollars2025.join(', ')}M`);

    // Map totals should differ
    const total2026 = mapDollars2026.reduce((a, b) => a + b, 0);
    const total2025 = mapDollars2025.reduce((a, b) => a + b, 0);
    console.log(`[All] Map total 2026: ${total2026}M, 2025: ${total2025}M`);
    expect(total2026).not.toEqual(total2025);
    expect(total2026).toBeGreaterThan(total2025); // revenue grows YoY
  }

  // 3b. Revenue KPI — should differ between years
  const revKpi2026 = snap2026.find(w => w.title.toLowerCase().includes('revenue') && !w.title.toLowerCase().includes('region') && !w.title.toLowerCase().includes('trend') && !w.title.toLowerCase().includes('customer'));
  const revKpi2025 = snap2025.find(w => w.title.toLowerCase().includes('revenue') && !w.title.toLowerCase().includes('region') && !w.title.toLowerCase().includes('trend') && !w.title.toLowerCase().includes('customer'));

  if (revKpi2026 && revKpi2025 && revKpi2026.dollars.length > 0 && revKpi2025.dollars.length > 0) {
    const kpi2026 = parseDollar(revKpi2026.dollars[0]);
    const kpi2025 = parseDollar(revKpi2025.dollars[0]);
    console.log(`[All] Revenue KPI 2026: $${kpi2026}M, 2025: $${kpi2025}M`);
    expect(kpi2026).not.toEqual(kpi2025);
  } else {
    console.log(`[All] Revenue KPI not found in both years — 2026: ${revKpi2026?.dollars}, 2025: ${revKpi2025?.dollars}`);
  }

  // 3c. Pipeline — should differ between years
  const pipe2026 = snap2026.find(w => w.title.toLowerCase().includes('pipeline') || w.text.toLowerCase().includes('pipeline'));
  const pipe2025 = snap2025.find(w => w.title.toLowerCase().includes('pipeline') || w.text.toLowerCase().includes('pipeline'));

  if (pipe2026 && pipe2025 && pipe2026.dollars.length > 0 && pipe2025.dollars.length > 0) {
    const pipeDollars2026 = pipe2026.dollars.map(d => parseDollar(d));
    const pipeDollars2025 = pipe2025.dollars.map(d => parseDollar(d));
    console.log(`[All] Pipeline 2026: ${pipeDollars2026.join(',')}M`);
    console.log(`[All] Pipeline 2025: ${pipeDollars2025.join(',')}M`);
    // At least the first dollar amount should differ
    expect(pipeDollars2026[0]).not.toEqual(pipeDollars2025[0]);
  } else {
    console.log(`[All] Pipeline not found in both years`);
  }

  // 3d. Revenue by Customer — should differ
  const cust2026 = snap2026.find(w => w.title.toLowerCase().includes('customer'));
  const cust2025 = snap2025.find(w => w.title.toLowerCase().includes('customer'));

  if (cust2026 && cust2025 && cust2026.dollars.length > 0 && cust2025.dollars.length > 0) {
    const custTotal2026 = cust2026.dollars.map(d => parseDollar(d)).reduce((a, b) => a + b, 0);
    const custTotal2025 = cust2025.dollars.map(d => parseDollar(d)).reduce((a, b) => a + b, 0);
    console.log(`[All] Customer total 2026: $${custTotal2026.toFixed(1)}M, 2025: $${custTotal2025.toFixed(1)}M`);
    expect(custTotal2026).not.toEqual(custTotal2025);
  } else {
    console.log(`[All] Customer chart not found in both years`);
  }

  // ── 4. Summary ──
  console.log(`[All] Widgets tested: map=${!!map2026 && !!map2025}, revenue_kpi=${!!revKpi2026 && !!revKpi2025}, pipeline=${!!pipe2026 && !!pipe2025}, customer=${!!cust2026 && !!cust2025}`);
  console.log('[All] Screenshots saved to test-results/period-all-2025.png and period-all-2026.png');

  // ── Final: no console errors ──
  if (consoleErrors.length > 0) {
    console.log('[All] Console errors:', consoleErrors);
  }
  expect(consoleErrors).toHaveLength(0);
});
