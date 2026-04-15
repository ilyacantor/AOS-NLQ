/**
 * Multi-year revenue query — user asks "show me revenue for 2024, 2025, 2026".
 *
 * The decomposer currently splits on commas into three "metric" tokens
 * ("revenue for 2024", "2025", "2026"). All three 404 against DCL. Before
 * the fix, NLQ swallowed the errors and reclassified the query as a
 * POINT_QUERY for the current quarter, returning a confident scalar
 * ("Revenue for 2026-Q2 is $37.2M") with a 95% badge — the user saw a
 * confident wrong answer.
 *
 * After the fix, the same query must return HTTP 422 with a structured
 * multi_metric_query_failed payload, and the UI must render the error
 * state (friendly message), never the confident scalar.
 *
 * B17 gate — the UI is the pass/fail.
 *
 * Requires: NLQ backend (8005) + frontend (3005) + DCL (8004) running,
 * at least one entity registered in the current run.
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test('Multi-year revenue query returns 422 and the UI renders the error state', async ({
  page,
}) => {
  const api = await pwRequest.newContext();
  const entitiesResp = await api.get('http://localhost:8005/api/v1/entities');
  expect(entitiesResp.ok()).toBeTruthy();
  const registeredIds: string[] = (
    (await entitiesResp.json()).entities || []
  ).map((e: { entity_id: string }) => e.entity_id);
  expect(
    registeredIds.length,
    'no entities registered in the current run',
  ).toBeGreaterThan(0);
  await api.dispose();

  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });

  const [entitiesLoaded] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/api/v1/entities') &&
        res.request().method() === 'GET',
      { timeout: 15_000 },
    ),
    page.goto('/', { waitUntil: 'load' }),
  ]);
  expect(entitiesLoaded.ok()).toBeTruthy();

  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  const question = 'show me revenue for 2024, 2025, 2026';
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

  // Backend contract: HTTP 422 with structured multi_metric_query_failed
  // detail. No silent fallback to POINT_QUERY.
  expect(
    queryResponse.status(),
    `expected 422, got ${queryResponse.status()}`,
  ).toBe(422);

  const body = await queryResponse.json();
  const detail = body.detail;
  expect(detail, 'response.detail must be an object').toBeTruthy();
  expect(detail.error).toBe('multi_metric_query_failed');
  expect(detail.question).toBe(question);

  // The three attempted metric names must be visible in the payload so an
  // operator (or downstream diagnostic) can see what was tried.
  expect(Array.isArray(detail.decomposed_into)).toBeTruthy();
  expect(detail.decomposed_into.length).toBeGreaterThanOrEqual(2);
  expect(Array.isArray(detail.attempts)).toBeTruthy();
  expect(detail.attempts.length).toBe(detail.decomposed_into.length);
  for (const a of detail.attempts) {
    expect(a.metric_attempted, 'attempt.metric_attempted required').toBeTruthy();
    expect(a.dcl_error, 'attempt.dcl_error required').toBeTruthy();
  }

  // UI contract: spinner clears, error state renders, confident scalar
  // must NOT appear.
  await expect(page.locator('text=Analyzing query...')).toHaveCount(0, {
    timeout: 15_000,
  });

  // GalaxyView renders the same text_response in both the mobile layout
  // (hidden on desktop by md:hidden) and the desktop layout, so filter
  // for the visible one.
  const errorMessage = page
    .locator('p:visible', {
      hasText: /Something went wrong processing your query/i,
    })
    .first();
  await expect(
    errorMessage,
    'UI must render the error state, not a confident scalar',
  ).toBeVisible({ timeout: 10_000 });

  // Regression guard: the pre-fix path returned "Revenue for 2026-Q2 is
  // $37.2M" (or similar scalar for whatever entity was auto-selected).
  // None of those must be rendered visibly.
  const confidentScalar = page.locator('p:visible', {
    hasText: /Revenue for 20\d\d-Q\d is \$/i,
  });
  await expect(
    confidentScalar,
    'UI must not render a confident scalar answer for a failed multi-metric query',
  ).toHaveCount(0);

  await page.waitForTimeout(500);
  await page.screenshot({
    path: 'test-results/multi-metric-422.png',
    fullPage: true,
  });
});
