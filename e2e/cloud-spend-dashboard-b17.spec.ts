// Operator-visible outcome: with the CloudFleet-USE1 snapshot selected, asking "Cloud spend for 2026-Q2" renders the answer "$128,914.32" and the CTO dashboard's "Cloud Spend" KPI tile renders that same total — where $128,914.32 is Σ(monthly_cost_usd) over the 200 records returned by Farm's cloud_spend scan, fetched at test time (not hardcoded). Both reached through real operator clicks: #snapshot-selector selectOption, #dashboard-persona-select selectOption, and typing into #nlq-search-input.
/**
 * AAM Blueprint v4 §3.5 / four_fabric_build_runbook Phase 1 sub-step (f) — B17.
 *
 * The cloud-spend feed flows through AAM into dev DCL; this is the browser-render
 * gate that proves the operator sees the right number. Expected values are pulled
 * from Farm ground truth at run time (CLAUDE.md Acceptance Rule 1) — the test
 * never hardcodes the dollar figure and never authors it.
 *
 * Live-services acceptance: NLQ backend (8005) + frontend (3005) + dev DCL (8104)
 * + Farm (8003), with the through-AAM cloud_spend already in dev DCL.
 */
import { test, expect, request as pwRequest } from 'playwright/test';

const FARM_SCAN = 'http://localhost:8003/sources/cloud_spend/scan';
const NLQ_API = 'http://localhost:8005';

/** Σ(monthly_cost_usd) over the Farm cloud_spend scan — the ground-truth total. */
async function farmTotal(): Promise<{ total: number; count: number; source: string }> {
  const api = await pwRequest.newContext();
  const resp = await api.post(FARM_SCAN, {
    data: { scan_filter: {}, cursor: null, page_size: 1000 },
  });
  expect(resp.status(), 'Farm cloud_spend scan unreachable').toBeLessThan(300);
  const body = await resp.json();
  await api.dispose();
  const recs: Array<Record<string, any>> = body.records || [];
  expect(recs.length, 'Farm scan returned no records — no ground truth').toBeGreaterThan(0);
  const f = (r: Record<string, any>) => r.fields || r;
  const total = recs.reduce((s, r) => s + (Number(f(r).monthly_cost_usd) || 0), 0);
  return { total, count: recs.length, source: String(body.source_system || '') };
}

/** Resolve the CloudFleet-USE1 snapshot id at run time (no hardcoded UUID). */
async function cloudFleetSnapshotId(): Promise<string> {
  const api = await pwRequest.newContext();
  const resp = await api.get(`${NLQ_API}/api/v1/snapshots`);
  expect(resp.status(), 'GET /api/v1/snapshots failed').toBeLessThan(300);
  const body = await resp.json();
  await api.dispose();
  const snap = (body.snapshots || []).find((s: any) =>
    String(s.entity_id).startsWith('CloudFleet-USE1'),
  );
  expect(snap, 'CloudFleet-USE1 snapshot not present in dev DCL').toBeDefined();
  return snap.dcl_ingest_id;
}

/** "$128,914.32" form for a number — the en-US currency the UI renders. */
function usd(n: number): string {
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

test.describe('cloud-spend B17 — operator sees the through-AAM total on dev', () => {
  test('Ask renders the cloud-spend total equal to Farm ground truth', async ({ page }) => {
    const { total, count, source } = await farmTotal();
    expect(source).toBe('aws_cost_explorer');
    const snapId = await cloudFleetSnapshotId();
    const expected = usd(total); // e.g. $128,914.32, derived from the 200 scan records

    await page.goto('/', { waitUntil: 'load' });
    const search = page.locator('#nlq-search-input');
    await expect(search).toBeVisible({ timeout: 15_000 });
    await page.locator('#snapshot-selector').selectOption(snapId);

    await search.fill('Cloud spend for 2026-Q2');
    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes('/api/v1/query') && r.request().method() === 'POST',
        { timeout: 60_000 },
      ),
      search.press('Enter'),
    ]);
    expect(resp.status(), '/api/v1/query failed').toBeLessThan(300);
    const qbody = await resp.json();
    expect(String(qbody.data_source), 'answer not served from DCL').toContain('dcl');

    // The total renders in both the ANSWER panel and the center card; the left
    // panel is collapsible, so assert the operator sees it on a visible surface.
    await expect(async () => {
      const loc = page.getByText(expected, { exact: false });
      const n = await loc.count();
      let onScreen = false;
      for (let i = 0; i < n; i++) {
        if (await loc.nth(i).isVisible()) { onScreen = true; break; }
      }
      expect(onScreen, `answer "${expected}" rendered but no visible instance`).toBe(true);
    }).toPass({ timeout: 15_000 });
    await page.screenshot({ path: 'test-results/cloud-spend-ask-b17.png', fullPage: true });
    console.log(`[B17] Ask: ${count} Farm records → ${expected} rendered, data_source=${qbody.data_source}`);
  });

  test('CTO dashboard "Cloud Spend" tile renders the total equal to Farm ground truth', async ({ page }) => {
    const { total } = await farmTotal();
    const snapId = await cloudFleetSnapshotId();

    await page.goto('/', { waitUntil: 'load' });
    await page.locator('#nav-tab-dashboard').click();
    await expect(page.locator('#dashboard-persona-select')).toBeVisible({ timeout: 15_000 });
    await page.locator('#snapshot-selector').selectOption(snapId);
    await page.locator('#dashboard-persona-select').selectOption('CTO');

    await expect(page.locator('.react-grid-layout')).toBeVisible({ timeout: 30_000 });
    const tile = page.locator('.react-grid-item', {
      has: page.getByRole('heading', { name: 'Cloud Spend' }),
    });
    await expect(tile, '"Cloud Spend" tile not on the CTO dashboard').toBeVisible({ timeout: 30_000 });

    const tileText = (await tile.innerText()).replace(/\s+/g, ' ');
    // Parse the dollar amount the tile renders; compare to ground truth at whole-dollar grain.
    const m = tileText.replace(/,/g, '').match(/\$\s*([0-9]+(?:\.[0-9]+)?)/);
    const rendered = m ? Number(m[1]) : NaN;
    expect(
      Math.round(rendered),
      `CTO Cloud Spend tile should render ${usd(total)}; tile text was "${tileText}"`,
    ).toBe(Math.round(total));
    await page.screenshot({ path: 'test-results/cloud-spend-cto-dashboard-b17.png', fullPage: true });
    console.log(`[B17] CTO tile rendered "${tileText}" vs ground truth ${usd(total)}`);
  });
});
