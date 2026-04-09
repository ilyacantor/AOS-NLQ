/**
 * Ask view auto-uses the current run's entity_id (set on mount from
 * /api/v1/entities). A simple question like "What is revenue?" must
 * resolve and render — no "Unknown entity" 422, no typed entity names.
 *
 * SE mode = one entity per run. The frontend picks list[0] automatically.
 *
 * B17 gate — the UI is the pass/fail.
 *
 * Requires: NLQ backend (8005) + frontend (3005) + DCL (8004) running,
 * at least one entity registered in the current run.
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test('Ask view auto-resolves the current-run entity without typing', async ({ page }) => {
  // Step 1: fetch the currently-registered entity from the backend so we
  // know what the frontend should have auto-selected.
  const api = await pwRequest.newContext();
  const entitiesResp = await api.get('http://localhost:8005/api/v1/entities');
  expect(entitiesResp.ok()).toBeTruthy();
  const registeredIds: string[] = (
    (await entitiesResp.json()).entities || []
  ).map((e: { entity_id: string }) => e.entity_id);
  expect(registeredIds.length, 'no entities registered in the current run').toBeGreaterThan(0);
  const currentEntity = registeredIds[0];
  await api.dispose();

  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });

  // Wait for /api/v1/entities to complete during page load — the frontend
  // auto-selects the first entity from this response, and we need that
  // state to be settled before we submit a query.
  const [entitiesLoaded] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/api/v1/entities') && res.request().method() === 'GET',
      { timeout: 15_000 },
    ),
    page.goto('/', { waitUntil: 'load' }),
  ]);
  expect(entitiesLoaded.ok()).toBeTruthy();

  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  // Ask a generic question that does NOT name any entity. The frontend
  // must attach entity_id from its auto-selected state.
  const question = 'What is revenue?';
  await searchInput.fill(question);

  const [queryResponse] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/api/v1/query') &&
        res.request().method() === 'POST',
      { timeout: 60_000 },
    ),
    searchInput.press('Enter'),
  ]);

  // The request body must carry entity_id for the current run.
  const requestBody = JSON.parse(queryResponse.request().postData() || '{}');
  expect(
    requestBody.entity_id,
    'Ask must send entity_id auto-selected from /api/v1/entities',
  ).toBe(currentEntity);

  // The response must NOT be 422. No "Unknown entity".
  expect(
    queryResponse.status(),
    `expected a successful resolution, got ${queryResponse.status()}`,
  ).not.toBe(422);
  expect(queryResponse.status()).toBeLessThan(400);

  // The rendered answer must NOT contain "Unknown entity".
  const unknownEntityText = page.locator('text=/Unknown entity/i').first();
  await expect(unknownEntityText).toHaveCount(0);

  // And the backend response body must be a real answer, not an error shell.
  const body = await queryResponse.json();
  expect(body.answer || body.dashboard, 'response must carry answer or dashboard').toBeTruthy();

  // Wait for the rendered answer to replace the loading spinner before the
  // screenshot, so B17 (UI pass/fail gate) can see the actual end state.
  await expect(page.locator('text=Analyzing query...')).toHaveCount(0, { timeout: 15_000 });
  await page.waitForTimeout(500);

  await page.screenshot({
    path: 'test-results/ask-auto-entity-resolution.png',
    fullPage: true,
  });
});
