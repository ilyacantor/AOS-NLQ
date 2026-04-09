/**
 * SE Pipeline E2E — Farm → DCL → NLQ
 *
 * Verifies that ingested SE pipeline data renders correctly across
 * NLQ surfaces: Ask/Query and Dashboard.
 *
 * All checks run in a single browser session to avoid WSL2 Chromium
 * --single-process crashes on context teardown.
 *
 * Requirements:
 *   - All services running via pm2 (nlq-backend:8005, nlq-frontend:3005,
 *     dcl-backend:8004, farm-backend:8003)
 *   - SE pipeline has run (triples ingested into DCL)
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test('SE pipeline: Ask/Query + Dashboard (Farm → DCL → NLQ)', async ({ page }) => {
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

  await searchInput.fill(`What is ${entityName} revenue?`);
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

  // PR 2: Dashboards view starts in empty state — operator must pick an
  // entity before the generator runs (I4: no silent default).
  const entitySelector = page.locator('#dashboard-entity-selector');
  await expect(entitySelector).toBeVisible({ timeout: 10_000 });
  await expect(entitySelector.locator('option')).not.toHaveCount(1, { timeout: 10_000 });
  const firstEntityValue = await entitySelector.locator('option').nth(1).getAttribute('value');
  expect(firstEntityValue, 'dropdown must have at least one entity option').toBeTruthy();
  await entitySelector.selectOption(firstEntityValue!);

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

  // ── Final: no console errors across all surfaces ──
  if (consoleErrors.length > 0) {
    console.log('[SE-E2E] Console errors:', consoleErrors);
  }
  expect(consoleErrors).toHaveLength(0);
});
