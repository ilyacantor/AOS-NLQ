/**
 * Trust Badge — PR 7 verification spec.
 *
 * Before PR 7 the NLQ /query response attached a static provenance lineage
 * from data/entity_test_scenarios.json. The shape did not match
 * ProvenanceBadge's expected run_provenance fields (mode / source_systems /
 * dcl_ingest_id …), so the badge rendered "No Data" grey for every query
 * even though real DCL provenance existed in the ctx var.
 *
 * After PR 7, enrich_response no longer attaches the fixture provenance.
 * _ensure_provenance at routes.py:173-187 attaches the real ctx-var
 * provenance from the v2 client (mode=Farm → Simulation) or the old client
 * (mode=Ingest → Verified). This spec asserts the badge renders one of the
 * real states, never "No Data".
 *
 * B17 gate — UI is the pass/fail.
 *
 * Requirements:
 *   - NLQ backend (8005) + frontend (3005) + DCL (8004) running
 *   - At least one entity registered in DCL
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test('Trust Badge: live query renders Verified or Simulation, never "No Data"', async ({
  page,
}) => {
  // Step 1: pick a revenue-bearing SE-shape snapshot from /api/v1/snapshots
  // so the trust-badge query has data to resolve. Using a standalone
  // APIRequestContext that does NOT share the page's browser context.
  // Using page.request here dies with "Target page, context or browser has
  // been closed" under the --single-process Chromium WSL2 config.
  const apiContext = await pwRequest.newContext();
  const snapsResp = await apiContext.get('http://localhost:8005/api/v1/snapshots');
  expect(snapsResp.status()).toBeLessThan(300);
  const allSnaps: Array<{ entity_id: string; dcl_ingest_id: string; total_rows: number }> =
    (await snapsResp.json()).snapshots || [];
  const revenueSnap = allSnaps.find(
    (s) => !s.entity_id.startsWith('finops-demo') && s.total_rows >= 5000,
  );
  expect(revenueSnap, 'no revenue-bearing SE-shape snapshot in tenant').toBeDefined();
  const entityId: string = revenueSnap!.entity_id;
  const snapshotId: string = revenueSnap!.dcl_ingest_id;
  await apiContext.dispose();

  // Step 2: Abort non-localhost network so external CDN calls don't hang,
  // then load the Ask (Galaxy) view
  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });
  await page.goto('/', { waitUntil: 'load' });

  // Pin the snapshot so identity resolves to the SE-shape entity regardless
  // of which snapshot the finops dispatch has pushed to star most recently.
  await page.locator('#snapshot-selector').selectOption(snapshotId);
  await expect(page.locator('#snapshot-selector')).toHaveValue(snapshotId);
  await expect(
    page.locator('[data-role="snapshot-follow-state"]').first(),
  ).toHaveText('pinned', { timeout: 5_000 });

  const searchInput = page.locator('#nlq-search-input');
  await expect(searchInput).toBeVisible({ timeout: 15_000 });

  // Step 3: Type the revenue query naming the snapshot's entity so the
  // backend doesn't hit the _resolve_entity_id fallback.
  const question = `What is ${entityId} revenue for 2026 Q2?`;
  await searchInput.fill(question);

  // Step 4: Submit and wait for /api/v1/query POST to return
  const [queryResponse] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/api/v1/query') &&
        res.request().method() === 'POST',
      { timeout: 60_000 },
    ),
    searchInput.press('Enter'),
  ]);
  expect(queryResponse.ok(), `/api/v1/query returned ${queryResponse.status()}`).toBeTruthy();

  // Step 5: Verify the response payload itself carries real run_provenance
  // shape, not fixture shape. If this fails, the backend regressed.
  const body = await queryResponse.json();
  const prov = body.provenance;
  expect(prov, 'response.provenance must be present').not.toBeNull();
  expect(prov, 'response.provenance must be present').toBeDefined();

  // Fixture keys must NOT be present
  expect(prov).not.toHaveProperty('lineage');
  expect(prov).not.toHaveProperty('system_of_record');
  expect(prov).not.toHaveProperty('trust_score');

  // Real keys MUST be present
  expect(prov).toHaveProperty('mode');
  const mode = String(prov.mode || '').toLowerCase();
  expect(['ingest', 'live', 'farm'], `mode=${mode} not in real set`).toContain(mode);

  // Step 6: Verify the compact ProvenanceBadge is rendered with a real
  // label. The badge renders "Verified" (green, mode=ingest/live) OR
  // "Simulation" (blue, mode=farm). Never "No Data" (grey).
  //
  // We target the ProvenanceBadge span directly by its title attribute
  // ("Sourced from …") and assert DOM presence via count — the compact
  // badge uses text-[10px] which confuses Playwright's toBeVisible
  // heuristic. The full-page screenshot below is the visual B17 proof.
  const trustBadge = page.locator('span[title^="Data Verified"], span[title^="Sourced from"]');
  await expect(
    trustBadge,
    'ProvenanceBadge element must exist in the DOM after response',
  ).toHaveCount(2, { timeout: 15_000 });
  // Two: one in the answer panel header, one in the node detail area.

  const verifiedBadge = page.getByText('Verified', { exact: true });
  const simulationBadge = page.getByText('Simulation', { exact: true });

  // And there must be no "No Data" badge anywhere.
  const noDataBadge = page.getByText('No Data', { exact: true });
  await expect(noDataBadge, 'Trust Badge must not render "No Data" after PR 7').toHaveCount(
    0,
    { timeout: 5_000 },
  );

  const verifiedCount = await verifiedBadge.count();
  const simulationCount = await simulationBadge.count();
  expect(
    verifiedCount + simulationCount,
    `Expected at least one Verified or Simulation badge, got verified=${verifiedCount} simulation=${simulationCount}`,
  ).toBeGreaterThan(0);

  // Step 7: Screenshot for the PR description
  await page.screenshot({
    path: 'pr7-evidence/trust-badge-after.png',
    fullPage: true,
  });

  console.log(
    `[trust-badge] mode=${mode} verified=${verifiedCount} simulation=${simulationCount}`,
  );
});
