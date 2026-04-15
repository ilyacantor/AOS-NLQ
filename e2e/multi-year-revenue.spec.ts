/**
 * Multi-year revenue query — user asks "show me revenue for 2024, 2025, 2026".
 *
 * Before the fix, the decomposer split on commas into three "metric"
 * tokens and all three 404'd against DCL, which NLQ swallowed into a
 * confident POINT_QUERY scalar ("Revenue for 2026-Q2 is $37.2M") with a
 * 95% badge — the user saw a confident wrong answer. The first fix
 * removed the silent fallback (422 with multi_metric_query_failed) but
 * did not deliver the right answer.
 *
 * After the real fix, the same query must return HTTP 200 with a
 * related_metrics array containing one entry per year (2024, 2025,
 * 2026), and the UI must render a three-row DataTable — never the
 * confident scalar and never the error state.
 *
 * B17 gate — the UI is the pass/fail.
 *
 * Requires: NLQ backend (8005) + frontend (3005) + DCL (8004) running,
 * at least one entity registered in the current run.
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test('Multi-year revenue query returns time-series + UI renders three-row table', async ({
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

  // Backend contract: HTTP 200 with related_metrics time-series.
  expect(
    queryResponse.status(),
    `expected 200, got ${queryResponse.status()}`,
  ).toBe(200);

  const body = await queryResponse.json();
  expect(body.success, 'response.success must be true').toBe(true);
  expect(
    Array.isArray(body.related_metrics),
    'response.related_metrics must be an array',
  ).toBeTruthy();
  expect(
    body.related_metrics.length,
    `expected 3 related_metrics, got ${body.related_metrics.length}`,
  ).toBe(3);

  const periods = body.related_metrics.map((r: { period: string }) => r.period);
  expect(periods).toEqual(expect.arrayContaining(['2024', '2025', '2026']));
  expect(new Set(periods).size).toBe(3);

  for (const rm of body.related_metrics) {
    expect(rm.metric, 'related_metric.metric required').toBe('revenue');
    expect(rm.value, `value must be non-null for period ${rm.period}`).not.toBeNull();
    expect(
      rm.formatted_value,
      `formatted_value required for period ${rm.period}`,
    ).toBeTruthy();
  }

  // data_source must start with 'dcl' per B9/B12 ('dcl' or 'dcl_v2').
  expect(body.data_source).toMatch(/^dcl/);

  // UI contract: spinner clears, DataTable renders three rows (one per
  // period), error state must NOT appear, confident scalar must NOT
  // appear. DataTable is rendered once in the mobile md:hidden layout
  // and once in the desktop md:flex layout — filter for visible rows.
  await expect(page.locator('text=Analyzing query...')).toHaveCount(0, {
    timeout: 15_000,
  });

  const dataRows = page.locator('table tr:visible').filter({
    hasText: /20(24|25|26)/,
  });
  await expect(
    dataRows,
    'UI must render a row per period (2024, 2025, 2026)',
  ).toHaveCount(3, { timeout: 10_000 });

  const errorBanner = page.locator('p:visible', {
    hasText: /Something went wrong processing your query/i,
  });
  await expect(
    errorBanner,
    'UI must NOT render the error state for a successful multi-period query',
  ).toHaveCount(0);

  const confidentScalar = page.locator('p:visible', {
    hasText: /Revenue for 20\d\d-Q\d is \$/i,
  });
  await expect(
    confidentScalar,
    'UI must not render a confident scalar answer for a multi-period query',
  ).toHaveCount(0);

  await page.waitForTimeout(500);
  await page.screenshot({
    path: 'test-results/multi-year-revenue.png',
    fullPage: true,
  });
});
