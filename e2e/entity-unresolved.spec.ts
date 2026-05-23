/**
 * Ask view auto-uses the active snapshot's entity_id (App.tsx:181
 * `askEntityId = askSurface.effective?.entity_id`). A simple question like
 * "What is revenue?" must resolve and render — no "Unknown entity" 422,
 * no typed entity names.
 *
 * Identity is snapshot-driven. The frontend reads /api/v1/snapshots, picks
 * the latest by run_timestamp (the ★ option), and the resulting entity_id
 * is the one the request body carries.
 *
 * B17 gate — the UI is the pass/fail.
 *
 * Requires: NLQ backend (8005) + frontend (3005) + DCL (8004) running,
 * with at least one snapshot in the current tenant.
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test('Ask view auto-resolves the current snapshot entity without typing', async ({ page }) => {
  // Step 1: read the latest snapshot's entity_id from the backend — that
  // is what the frontend should have auto-selected via the SnapshotContext.
  const api = await pwRequest.newContext();
  const snapshotsResp = await api.get('http://localhost:8005/api/v1/snapshots');
  expect(snapshotsResp.status()).toBeLessThan(300);
  const snapshotList: Array<{ entity_id: string; run_timestamp: string; dcl_ingest_id: string }> =
    (await snapshotsResp.json()).snapshots || [];
  expect(snapshotList.length, 'no snapshots in current tenant').toBeGreaterThan(0);
  // computeLatest mirrors SnapshotContext.tsx:26 — max(run_timestamp).
  const latestSnapshot = snapshotList.reduce((newest, s) =>
    new Date(s.run_timestamp).getTime() > new Date(newest.run_timestamp).getTime() ? s : newest
  );
  const currentEntity = latestSnapshot.entity_id;
  const currentSnapshotId = latestSnapshot.dcl_ingest_id;
  await api.dispose();

  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });

  // Wait for /api/v1/snapshots — the SnapshotContext hydrates from this
  // response, and the page must be settled before we submit a query so
  // that body.entity_id and body.snapshot_id reflect the active surface.
  const [snapshotsLoaded] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/api/v1/snapshots') && res.request().method() === 'GET',
      { timeout: 15_000 },
    ),
    page.goto('/', { waitUntil: 'load' }),
  ]);
  expect(snapshotsLoaded.status()).toBeLessThan(300);

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

  // The request body must carry entity_id + snapshot_id auto-selected
  // from the active surface's effective snapshot (App.tsx:181, 282).
  const requestBody = JSON.parse(queryResponse.request().postData() || '{}');
  expect(
    requestBody.entity_id,
    'Ask must send entity_id auto-derived from the latest snapshot',
  ).toBe(currentEntity);
  expect(
    requestBody.snapshot_id,
    'Ask must send snapshot_id from the active snapshot selector',
  ).toBe(currentSnapshotId);

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
