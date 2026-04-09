/**
 * PR 2 — /api/v1/query returns 422 when an entity cannot be resolved,
 * and the Ask view renders a friendly inline error naming the registered
 * entities instead of silently hallucinating data for a different entity.
 *
 * B17 gate — the UI is the pass/fail.
 *
 * Requires: NLQ backend (8005) + frontend (3005) + DCL (8004) running,
 * at least one entity registered. BlueLogic must NOT be in the registry.
 *
 * One test per file — Chrome `--single-process` cannot relaunch the browser
 * context between tests in the same spec. The Dashboards empty-state test
 * lives in e2e/dashboards-entity-empty-state.spec.ts.
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test('PR 2 — Ask view renders inline 422 error when entity unresolvable', async ({ page }) => {
  // Step 1: confirm BlueLogic is not registered; capture the real entity list.
  const api = await pwRequest.newContext();
  const entitiesResp = await api.get('http://localhost:8005/api/v1/entities');
  expect(entitiesResp.ok()).toBeTruthy();
  const registeredIds: string[] = (
    (await entitiesResp.json()).entities || []
  ).map((e: { entity_id: string }) => e.entity_id);
  expect(registeredIds.length, 'no entities registered').toBeGreaterThan(0);
  expect(
    registeredIds.some((id) => id.toLowerCase().includes('bluelogic')),
    'BlueLogic must NOT be in the registry for this test',
  ).toBeFalsy();
  await api.dispose();

  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });
  await page.goto('/', { waitUntil: 'load' });

  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  const question = 'What is BlueLogic revenue for 2026 Q2?';
  await searchInput.fill(question);

  // The POST must come back as 422 — no silent fallback.
  const [queryResponse] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/api/v1/query') &&
        res.request().method() === 'POST',
      { timeout: 60_000 },
    ),
    searchInput.press('Enter'),
  ]);
  expect(
    queryResponse.status(),
    `expected 422 for unknown entity, got ${queryResponse.status()}`,
  ).toBe(422);

  const body = await queryResponse.json();
  expect(body.detail).toBeDefined();
  expect(body.detail.error).toBe('entity_unresolved');
  expect(body.detail.question).toContain('BlueLogic');
  expect(Array.isArray(body.detail.registered_entities)).toBe(true);
  expect(body.detail.registered_entities.length).toBeGreaterThan(0);

  // The friendly error message must name "Unknown entity" AND at least one
  // registered entity so the user knows what to pick. GalaxyView.tsx renders
  // an `isTextOnlyResponse` overlay in BOTH the mobile sheet (text-base) and
  // the desktop center overlay (text-lg). At viewport 1280×720 the mobile
  // layout is inside a `md:hidden` div → display:none. Target the desktop
  // overlay specifically via its unique `text-lg` + `whitespace-pre-line`
  // class combo so we don't match the hidden mobile copy.
  const errorRegion = page.locator(
    'p.text-lg.whitespace-pre-line:has-text("Unknown entity")',
  ).first();
  await expect(errorRegion, 'Ask view must render "Unknown entity" inline').toBeVisible({
    timeout: 15_000,
  });

  // At least one registered entity name must be on screen as part of the hint.
  const firstEntity = registeredIds[0];
  await expect(
    page.locator(`p.text-lg.whitespace-pre-line:has-text("${firstEntity}")`).first(),
    `must list registered entity ${firstEntity}`,
  ).toBeVisible({ timeout: 5_000 });

  // Must NOT contain a bogus numeric revenue answer (no $-amount hallucination).
  const hallucinatedDollars = page.locator('text=/\\$\\d+(\\.\\d+)?[BMK]?/').first();
  const hallucinationCount = await hallucinatedDollars.count();
  expect(
    hallucinationCount,
    'no hallucinated $ amount may be shown for an unresolved entity',
  ).toBe(0);

  await page.screenshot({
    path: 'test-results/pr2-ask-422-error.png',
    fullPage: true,
  });
});
