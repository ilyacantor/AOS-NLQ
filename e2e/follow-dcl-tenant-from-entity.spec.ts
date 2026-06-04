// Operator-visible outcome: on NLQ Ask with the snapshot selector on DCL's current entity FabricDemo, asking "How many customers?" renders "Customer Count for 2026-Q2 is 6" — the exact integer DCL holds for FabricDemo's customer.total/count under its own tenant (fab1c0de); a metric FabricDemo lacks (gross margin) renders the readable "I don't have data for it right now" surface, not a number or a crash.
/**
 * B17 acceptance — follow-DCL + tenant-from-entity, through the operator UI.
 *
 * The NLQ Ask identity is snapshot-driven: the #snapshot-selector reflects DCL's
 * current entity (its most-recent ingest), and App.tsx sends that snapshot's
 * entity_id on every /api/v1/query. The backend then resolves THAT entity's tenant
 * (tenant-from-entity) and answers from it. This test drives the operator path —
 * select the snapshot, type the question, press Enter — and asserts the rendered
 * answer equals ground truth pulled from DCL at test time (never hardcoded).
 *
 * Live-services acceptance: real DCL (8104) + NLQ backend (8005) + frontend (3005).
 * Read-only page.request.get() to DCL is the ground-truth source for FabricDemo
 * (a four-fabric entity DCL holds, not a Farm SE entity); no mutating call is made.
 */
import { test, expect, request as pwRequest } from 'playwright/test';

const DCL = 'http://localhost:8104';
const NLQ = 'http://localhost:8005';

// Ground truth fetched once at test time: the current entity, its tenant, and the
// customer count DCL holds for it under that tenant.
async function groundTruth() {
  const api = await pwRequest.newContext();
  // The snapshot the UI auto-selects = the latest in the current tenant.
  const snaps = (await (await api.get(`${NLQ}/api/v1/snapshots`)).json()).snapshots || [];
  const latest = snaps.reduce((a: any, b: any) =>
    new Date(b.run_timestamp).getTime() > new Date(a.run_timestamp).getTime() ? b : a);
  const entity = latest.entity_id;
  const snapshotId = latest.dcl_ingest_id;
  // The tenant DCL records for this entity (what tenant-from-entity must resolve).
  const runs = (await (await api.get(`${DCL}/api/dcl/triples/runs`)).json()).runs || [];
  let tenant: string | undefined;
  for (const r of runs) { if (r.entity_summary && entity in r.entity_summary) { tenant = r.tenant_id; break; } }
  // Customer count DCL holds for this entity under that tenant — the expected answer.
  const browse = await (await api.get(
    `${DCL}/api/dcl/triples/browse?tenant_id=${tenant}&domain=customer&entity_id=${entity}&limit=50`)).json();
  const triple = (browse.triples || []).find((t: any) => t.property === 'count' && /customer/.test(t.concept || ''));
  await api.dispose();
  const count = Number(triple?.value);
  return { entity, snapshotId, tenant, count };
}

test('Ask renders the current entity\'s customer count = DCL ground truth (follow-DCL + tenant-from-entity)', async ({ page }) => {
  const gt = await groundTruth();
  expect(gt.tenant, `DCL must record a tenant for ${gt.entity}`).toMatch(/^[0-9a-f]{8}-/i);
  expect(Number.isInteger(gt.count), `DCL customer.total/count must be an integer, got ${gt.count}`).toBe(true);

  // Operator opens NLQ; wait for the snapshot list so identity is hydrated.
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/snapshots') && r.request().method() === 'GET', { timeout: 20_000 }),
    page.goto('/', { waitUntil: 'load' }),
  ]);

  // Operator picks the current entity's snapshot (real UI event on the selector).
  const selector = page.locator('#snapshot-selector');
  await expect(selector).toBeVisible({ timeout: 20_000 });
  await selector.selectOption(gt.snapshotId);

  // Operator types the question and presses Enter.
  const search = page.locator('#nlq-search-input');
  await expect(search).toBeVisible({ timeout: 20_000 });
  await search.fill('How many customers?');
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/query') && r.request().method() === 'POST', { timeout: 60_000 }),
    search.press('Enter'),
  ]);

  // The query carried the SELECTED entity, and resolution succeeded.
  const reqBody = JSON.parse(resp.request().postData() || '{}');
  expect(reqBody.entity_id, 'Ask must send the snapshot entity_id').toBe(gt.entity);
  expect(resp.status(), `expected resolution, got ${resp.status()}`).toBeLessThan(400);

  // The answer carries the entity's identity and the value DCL holds for it under
  // its own tenant — proof the query resolved THIS entity's tenant, not a global pin.
  const body = await resp.json();
  expect(body.entity_id, 'response entity_id mismatch').toBe(gt.entity);
  expect(Number(body.value), 'response value must equal DCL customer count').toBe(gt.count);

  // Frontend is the gate: the rendered answer shows the metric and the ground-truth
  // value. Build the matcher FROM the fetched count (not hardcoded).
  await expect(page.locator('text=Analyzing query...')).toHaveCount(0, { timeout: 20_000 });
  // The answer renders in several responsive variants; assert the VISIBLE one shows
  // the metric label and the ground-truth value (matcher built from the fetched count).
  await expect(
    page.getByText(new RegExp(`Customer Count[^]*\\b${gt.count}\\b`, 'i')).and(page.locator(':visible')).first(),
    `UI must render "Customer Count ... ${gt.count}"`,
  ).toBeVisible({ timeout: 20_000 });

  await page.screenshot({ path: 'tests/playwright/screenshots/follow_dcl_customer_count.png', fullPage: true });
});

test('Ask renders a readable no-data surface for a metric the current entity lacks (negative)', async ({ page }) => {
  const gt = await groundTruth();

  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/snapshots') && r.request().method() === 'GET', { timeout: 20_000 }),
    page.goto('/', { waitUntil: 'load' }),
  ]);
  await page.locator('#snapshot-selector').selectOption(gt.snapshotId);

  const search = page.locator('#nlq-search-input');
  await expect(search).toBeVisible({ timeout: 20_000 });
  await search.fill('What is gross margin?');
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/query') && r.request().method() === 'POST', { timeout: 60_000 }),
    search.press('Enter'),
  ]);

  // FabricDemo carries no COGS, so there is no gross margin: the backend returns a
  // null value with a readable message — never a fabricated number (A1).
  const body = await resp.json();
  expect(resp.status(), 'no-data is a 200 with a readable answer, not an error code').toBe(200);
  expect(body.value, 'gross margin must be null for an entity without COGS').toBeNull();

  // The UI must render that readable surface, naming the metric.
  await expect(page.locator('text=Analyzing query...')).toHaveCount(0, { timeout: 20_000 });
  await expect(
    page.getByText(/don't have data for it right now|missing data in the current dataset/i).and(page.locator(':visible')).first(),
    'UI must render the readable no-data message',
  ).toBeVisible({ timeout: 20_000 });
  // And the visible answer must NOT contain a fabricated percentage value (A1).
  const shownAnswer = await page.getByText(/Gross Margin/i).and(page.locator(':visible')).first().textContent();
  expect(shownAnswer ?? '', 'no fabricated gross margin % may be rendered').not.toMatch(/\d+(\.\d+)?\s*%/);

  await page.screenshot({ path: 'tests/playwright/screenshots/follow_dcl_gross_margin_nodata.png', fullPage: true });
});
