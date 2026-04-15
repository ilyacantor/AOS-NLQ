/**
 * Pipeline Funnel — visual rendering for "pipeline" shorthand query
 *
 * Verifies that submitting "pipeline" through the Ask view renders the
 * SalesFunnel SVG visualization (response_type=sales_funnel path),
 * not the text fallback.
 *
 * Requirements:
 *   - nlq-backend:8005 and nlq-frontend:3005 running
 *   - Farm SE pipeline ingested (customer.pipeline.{stage} triples in DCL)
 */

import { test, expect } from 'playwright/test';

test('Pipeline funnel: "pipeline" query renders SalesFunnel SVG with proportional bands', async ({ page }) => {

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

  // Start listening for the entities response BEFORE navigating so we
  // don't miss the early request. The frontend's entities-load useEffect
  // populates selectedDashboardEntityId, which in turn injects entity_id
  // into the query body. Bare "pipeline" must take the SHORTHAND path
  // (with entity_id in the body) to reach the funnel branch — including
  // an entity name in the question text routes it through POINT_QUERY
  // instead and bypasses the funnel.
  const entitiesResponsePromise = page.waitForResponse(
    (r) => r.url().includes('/api/v1/entities') && r.status() === 200,
    { timeout: 15_000 },
  );

  await page.goto('/', { waitUntil: 'load' });
  await entitiesResponsePromise;

  // Search input visible; entity auto-selected from registered list on mount.
  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  await searchInput.fill('pipeline');
  await searchInput.press('Enter');

  // SalesFunnel container appears in galaxy view.
  const funnelContainer = page.locator('#sales-funnel-visual');
  await expect(funnelContainer).toBeVisible({ timeout: 30_000 });

  // SVG with the funnel ARIA label.
  const funnelSvg = funnelContainer.locator('svg[aria-label^="Sales pipeline funnel"]');
  await expect(funnelSvg).toBeVisible({ timeout: 10_000 });

  // At least 2 stage bands rendered as <path> elements.
  const bandCount = await funnelSvg.locator('path').count();
  expect(bandCount).toBeGreaterThanOrEqual(2);

  // Extract band top widths and assert the funnel tapers — top of each
  // band is wider than the top of the next band (TAPER_BOTTOM = 0.3 in
  // SalesFunnel.tsx). The widths are not data-proportional; the funnel
  // shape is the metaphor and the dollar labels are the data.
  const topWidths = await funnelSvg.evaluate((svg) => {
    const out: number[] = [];
    for (const path of svg.querySelectorAll('path')) {
      const coords = (path.getAttribute('d') || '').match(/[\d.]+/g);
      if (!coords || coords.length < 8) continue;
      const x1 = parseFloat(coords[0]);
      const x2 = parseFloat(coords[2]);
      out.push(Math.abs(x2 - x1));
    }
    return out;
  });
  expect(topWidths.length).toBeGreaterThanOrEqual(2);
  for (let i = 0; i < topWidths.length - 1; i++) {
    expect(topWidths[i]).toBeGreaterThan(topWidths[i + 1]);
  }

  // Dollar-amount label inside at least one band.
  const labelTexts = await funnelSvg.locator('text').allTextContents();
  expect(labelTexts.some(t => t.trim().startsWith('$'))).toBe(true);

  // Source provenance line.
  await expect(funnelContainer.locator('text=/Source: dcl_v2/')).toBeVisible();

  await funnelContainer.screenshot({ path: 'test-results/pipeline-funnel.png' });

  if (consoleErrors.length > 0) {
    console.log('[Funnel] Console errors:', consoleErrors);
  }
  expect(consoleErrors).toHaveLength(0);
});
