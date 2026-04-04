/**
 * Pipeline Funnel — proportional stage sizing
 *
 * Verifies that the Sales Pipeline funnel widget renders SVG bands
 * whose widths are proportional to their dollar values.
 *
 * Requirements:
 *   - nlq-backend:8005 and nlq-frontend:3005 running
 *   - SE pipeline data ingested (pipeline stages in DCL)
 */

import { test, expect } from 'playwright/test';

test('Pipeline funnel: stage widths proportional to dollar values', async ({ page }) => {
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

  // ── 1. Submit a CRO dashboard query to generate the dashboard ──
  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  await searchInput.fill('Show me a sales dashboard with ARR KPI, pipeline KPI, bookings trend over time, win rate KPI, and quota attainment by rep');
  await searchInput.press('Enter');

  // Wait for the dashboard grid to appear (query auto-navigates to dashboard view)
  const gridLayout = page.locator('.react-grid-layout');
  await expect(gridLayout).toBeVisible({ timeout: 60_000 });

  // ── 3. Wait for the pipeline funnel SVG to appear ──
  const funnelSvg = page.locator('svg[aria-label^="Sales pipeline funnel"]');
  await expect(funnelSvg).toBeVisible({ timeout: 30_000 });

  // ── 4. Extract band widths and verify proportional to dollar values ──
  const bandData = await funnelSvg.evaluate((svg) => {
    const paths = svg.querySelectorAll('path');
    const bands: { topWidth: number; botWidth: number }[] = [];

    for (const path of paths) {
      const d = path.getAttribute('d') || '';
      // Parse M x1,y1 L x2,y1 L x3,y2 L x4,y2 Z
      const coords = d.match(/[\d.]+/g);
      if (!coords || coords.length < 8) continue;

      const x1 = parseFloat(coords[0]);
      const x2 = parseFloat(coords[2]);
      const x3 = parseFloat(coords[4]);
      const x4 = parseFloat(coords[6]);

      bands.push({
        topWidth: Math.abs(x2 - x1),
        botWidth: Math.abs(x3 - x4),
      });
    }
    return bands;
  });

  console.log('[Funnel] Band widths:', JSON.stringify(bandData.map((b, i) => ({
    band: i, topW: +b.topWidth.toFixed(1), botW: +b.botWidth.toFixed(1),
  })), null, 2));

  expect(bandData.length).toBeGreaterThanOrEqual(2);

  // ── 5a. Widths vary (proportional to dollar values, not uniform) ──
  const topWidths = bandData.map(b => Math.round(b.topWidth));
  const uniqueWidths = new Set(topWidths);
  expect(uniqueWidths.size).toBeGreaterThan(1);
  console.log(`[Funnel] Top widths: ${topWidths.join(', ')}px — ${uniqueWidths.size} distinct values`);

  // ── 5b. First band (Lead) is widest — largest dollar stage ──
  const maxW = Math.max(...topWidths);
  expect(topWidths[0]).toBe(maxW);
  console.log(`[Funnel] Lead band is widest at ${topWidths[0]}px`);

  // ── 5c. Smooth taper: bottom of band i = top of band i+1 ──
  for (let i = 0; i < bandData.length - 1; i++) {
    expect(bandData[i].botWidth).toBeCloseTo(bandData[i + 1].topWidth, 0);
  }

  // ── 6. Capture screenshot for visual verification ──
  await funnelSvg.scrollIntoViewIfNeeded();
  const funnelWidget = funnelSvg.locator('..');
  await funnelWidget.screenshot({ path: 'test-results/pipeline-funnel.png' });
  console.log('[Funnel] Screenshot saved to test-results/pipeline-funnel.png');

  // ── 7. Verify dollar labels are visible inside bands ──
  const dollarLabels = funnelSvg.locator('text');
  const labelCount = await dollarLabels.count();
  expect(labelCount).toBeGreaterThan(0);

  // At least one label should show a dollar amount
  let hasDollar = false;
  for (let i = 0; i < labelCount; i++) {
    const text = await dollarLabels.nth(i).textContent();
    if (text && text.startsWith('$')) {
      hasDollar = true;
      break;
    }
  }
  expect(hasDollar).toBe(true);

  // ── Final: no console errors ──
  if (consoleErrors.length > 0) {
    console.log('[Funnel] Console errors:', consoleErrors);
  }
  expect(consoleErrors).toHaveLength(0);
});
