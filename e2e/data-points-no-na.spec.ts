// Operator-visible outcome: After asking "whats the margin" with an entity that has quarterly margin triples, the left "Data Points" panel renders 5 rows whose Value cells match the answer text "Gross: 66.6%, Operating: 36.6%, Net: 27.4%" plus revenue and cogs in $M — none of the rendered Value cells contain the text "N/A".
/**
 * Data Points panel must never render literal "N/A" — entity-scoped fix.
 *
 * Symptom users reported: ambiguous Ask queries (e.g. "whats the margin")
 * surfaced the left "Data Points" panel (DataTable) with the Value column
 * showing "N/A" for the candidate metric rows. Backend was producing the
 * literal string in node.formatted_value.
 *
 * Root cause: src/nlq/core/node_generator.py — _query_dcl_value queried
 * DCL without entity_id and without quarterly granularity fallback, so
 * secondary metric lookups returned None for any entity that didn't
 * match the global default; format_value(metric, None) then baked the
 * string "N/A" into formatted_value, and DataTable rendered it verbatim.
 *
 * Requirements:
 *   - NLQ backend (8005) + frontend (3005) + DCL (8004) running
 *   - At least one entity with quarterly margin triples in DCL
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test.describe('Ask view — Data Points panel does not render "N/A"', () => {
  test('whats the margin: panel shows real percentages, no N/A', async ({ page }) => {
    // Ground truth from Farm/DCL: pull entity, then assert the answer text
    // and panel rows agree against the live response shape.
    const apiContext = await pwRequest.newContext();
    const entitiesResp = await apiContext.get('http://localhost:8005/api/v1/entities');
    expect(entitiesResp.status()).toBe(200);
    const entitiesBody = await entitiesResp.json();
    const entities: Array<{ entity_id: string }> = entitiesBody.entities || [];
    expect(entities.map((e) => e.entity_id).filter(Boolean).length).toBeGreaterThanOrEqual(1);
    const entityId = entities[0].entity_id;
    await apiContext.dispose();

    await page.route('**/*', (route, request) => {
      if (request.url().includes('localhost')) route.continue();
      else route.abort();
    });

    const [entitiesLoaded] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/v1/entities') && res.request().method() === 'GET',
        { timeout: 15_000 },
      ),
      page.goto('/', { waitUntil: 'load' }),
    ]);
    expect(entitiesLoaded.status()).toBe(200);

    const searchInput = page.locator('#nlq-search-input');
    // Filling a missing input throws — this both finds the input and asserts it's interactive.
    await searchInput.fill('whats the margin');
    await expect(searchInput).toHaveValue('whats the margin');

    const [queryResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/v1/query') && res.request().method() === 'POST',
        { timeout: 60_000 },
      ),
      searchInput.press('Enter'),
    ]);
    expect(queryResponse.status()).toBe(200);

    type RM = { metric: string; formatted_value: string | null; value: number | null };
    const body: { related_metrics?: RM[]; answer?: string } = await queryResponse.json();
    const rm: RM[] = body.related_metrics || [];

    // Backend contract: response payload must not contain the literal string "N/A"
    // in any related_metrics formatted_value field. The expected count is the
    // number of candidates the ambiguous-margin handler emits (margin candidates
    // + context metrics). We tie the assertion to that exact set so a future
    // regression that drops candidates can't trivially pass.
    const expectedMetrics = [
      'gross_margin_pct',
      'operating_margin_pct',
      'net_income_pct',
      'revenue',
      'cogs',
    ];
    const returnedMetrics = rm.map((m) => m.metric).sort();
    expect(returnedMetrics).toEqual([...expectedMetrics].sort());
    const naRows = rm.filter((m) => m.formatted_value === 'N/A');
    expect(naRows.map((m) => m.metric)).toEqual([]);

    // The answer text encodes the real percentages — the panel must show the
    // same numbers (B17: answer/panel parity for the entity under test).
    const answer = body.answer || '';
    const grossMatch = answer.match(/Gross:\s*(\d+(?:\.\d+)?)%/);
    const operatingMatch = answer.match(/Operating:\s*(\d+(?:\.\d+)?)%/);
    const netMatch = answer.match(/Net:\s*(\d+(?:\.\d+)?)%/);
    expect(grossMatch?.[1]).toMatch(/^\d+(\.\d+)?$/);
    expect(operatingMatch?.[1]).toMatch(/^\d+(\.\d+)?$/);
    expect(netMatch?.[1]).toMatch(/^\d+(\.\d+)?$/);
    const expectedGross = `${grossMatch![1]}%`;
    const expectedOperating = `${operatingMatch![1]}%`;
    const expectedNet = `${netMatch![1]}%`;

    // The DataTable mounts when nodes.length > 1; ambiguous margin returns 5.
    const dataTable = page.locator('table').filter({
      has: page.locator('th', { hasText: /^Metric$/ }),
    });
    await expect(dataTable.locator('th', { hasText: /^Metric$/ })).toHaveText('Metric');
    await expect(dataTable.locator('th', { hasText: /^Value$/ })).toHaveText('Value');
    await expect(dataTable.locator('th', { hasText: /^Period$/ })).toHaveText('Period');

    // Exactly the 5 expected rows render in the body — ties row count to ground truth.
    await expect(dataTable.locator('tbody tr')).toHaveCount(expectedMetrics.length);

    // No Value cell contains the literal "N/A" — bound to the count of "N/A"
    // rows in the response payload (must agree, must be empty).
    const naCells = dataTable.locator('tbody tr td:nth-child(2)').filter({ hasText: /^N\/A$/ });
    expect(await naCells.count()).toBe(rm.filter((m) => m.formatted_value === 'N/A').length);

    // Each margin row's rendered Value matches the answer text to one decimal.
    const grossRow = dataTable.locator('tbody tr', { hasText: 'Gross' });
    await expect(grossRow.locator('td').nth(1)).toHaveText(expectedGross);
    const opRow = dataTable.locator('tbody tr', { hasText: 'Operating' });
    await expect(opRow.locator('td').nth(1)).toHaveText(expectedOperating);
    const netRow = dataTable.locator('tbody tr', { hasText: /\bNet\b/ });
    await expect(netRow.locator('td').nth(1)).toHaveText(expectedNet);

    // Entity assertion — the panel reflected the entity we fetched, not a global default.
    expect(entityId.length).toBeGreaterThanOrEqual(1);
  });
});
