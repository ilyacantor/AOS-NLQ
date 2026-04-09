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

import { test, expect, request as pwRequest } from 'playwright/test';

test('SE surfaces work without Convergence: Ask + Dashboard + Health', async ({ page }) => {
  // PR 2: include the registered entity name in the Ask query so the backend
  // can resolve it via _detect_entity_id. Bare "What's revenue?" 422s now.
  const api = await pwRequest.newContext();
  const entitiesResp = await api.get('http://localhost:8005/api/v1/entities');
  const registered = ((await entitiesResp.json()).entities || []) as Array<{
    entity_id: string;
    display_name?: string;
  }>;
  expect(registered.length, 'no entities registered').toBeGreaterThan(0);
  const entityName = registered[0].display_name || registered[0].entity_id;
  await api.dispose();

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

  await searchInput.fill(`What is ${entityName} revenue?`);
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

  // Dashboards auto-selects the current-run entity on mount (SE mode).
  const entitySelector = page.locator('#dashboard-entity-selector');
  await expect(entitySelector).toBeVisible({ timeout: 10_000 });
  await expect(entitySelector.locator('option').first()).toBeAttached({ timeout: 10_000 });
  const firstEntityValue = await entitySelector.locator('option').first().getAttribute('value');
  expect(firstEntityValue, 'dropdown must have at least one entity option').toBeTruthy();

  const gridLayout = page.locator('.react-grid-layout');
  await expect(gridLayout).toBeVisible({ timeout: 30_000 });

  const cells = page.locator('.react-grid-layout .react-grid-item');
  await expect(cells.first()).toBeVisible({ timeout: 15_000 });
  console.log(`[SE-no-conv] Dashboard widgets: ${await cells.count()}`);
});
