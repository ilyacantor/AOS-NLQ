// Operator-visible outcome: with a full-depth RECORDS-PATH entity current (FullArr-T2 — financials + operational + fabrics DCL-classified from records via ingest-records, NOT pre-formed SE ingest-triples), the CFO dashboard's Net Income tile renders the records-path P&L value DCL holds for it (a value from pnl.net_income, DCL ground truth), proving the financial dashboards now populate for a new-way entity — the exact tiles that showed "No data for net_income" in the prior turn now fire.
/**
 * B17 — the financial dashboards fire for a NEW-WAY (records-path) entity.
 *
 * The prior-turn "new-way" test (FabricDemo) rendered "No data for net_income" because the
 * records-path produced no P&L. The financial + operational verticals of the SE-path cutover
 * now classify the full SE depth from records (ingest-records). This drives the CFO dashboard
 * through the operator UI and asserts the Net Income tile renders a value DCL actually holds
 * for the current records-path entity (pnl.net_income) — ground truth fetched from DCL at test
 * time, never hardcoded, never agent-authored.
 *
 * Live-services acceptance: DCL 8104 + NLQ 8005 + frontend 3005. Read-only page.request.get().
 */
import { test, expect, request as pwRequest } from 'playwright/test';

const DCL = 'http://localhost:8104';
const NLQ = 'http://localhost:8005';

// The current entity, its tenant, and the set of pnl.net_income values DCL classified for it.
async function groundTruth() {
  const api = await pwRequest.newContext();
  const snaps = (await (await api.get(`${NLQ}/api/v1/snapshots`)).json()).snapshots || [];
  const latest = snaps.reduce((a: any, b: any) =>
    new Date(b.run_timestamp).getTime() > new Date(a.run_timestamp).getTime() ? b : a);
  const entity = latest.entity_id;
  const snapshotId = latest.dcl_ingest_id;
  const runs = (await (await api.get(`${DCL}/api/dcl/triples/runs`)).json()).runs || [];
  let tenant: string | undefined;
  for (const r of runs) { if (r.entity_summary && entity in r.entity_summary) { tenant = r.tenant_id; break; } }
  const browse = await (await api.get(
    `${DCL}/api/dcl/triples/browse?tenant_id=${tenant}&entity_id=${entity}&domain=pnl&limit=200`)).json();
  const netIncome = (browse.triples || [])
    .filter((t: any) => t.concept === 'pnl.net_income' && t.property === 'amount')
    .map((t: any) => Math.round(Number(t.value) * 100) / 100);
  const provenanced = (browse.triples || []).find((t: any) => t.fabric_plane) || {};
  await api.dispose();
  return { entity, snapshotId, tenant, netIncome, plane: provenanced.fabric_plane };
}

function parseMoney(text: string): number {
  const m = text.match(/\$?\s*(-?[\d,]+(?:\.\d+)?)\s*([KMB])?/i);
  if (!m) return NaN;
  let n = Number(m[1].replace(/,/g, ''));
  const suf = (m[2] || '').toUpperCase();
  if (suf === 'K') n *= 1e3; else if (suf === 'M') n *= 1e6; else if (suf === 'B') n *= 1e9;
  return n;
}

test('CFO Net Income tile renders the records-path P&L value (financial dashboards fire for a new-way entity)', async ({ page }) => {
  const gt = await groundTruth();
  // The current entity is records-path (its triples carry a fabric plane, not pre-formed SE triples)
  // and DCL holds real P&L for it.
  expect(['erp', 'warehouse', 'bi', 'ipaas', 'event_bus', 'api_gateway']).toContain(gt.plane);
  expect(gt.netIncome.length, `DCL must hold pnl.net_income for ${gt.entity}`).toBeGreaterThan(1);

  let cfo: any = null;
  page.on('response', async (res) => {
    if (res.url().includes('/api/v1/query') && res.request().method() === 'POST') {
      try { const b = await res.json(); if (b?.dashboard_data?.kpi_net_income) cfo = b; } catch { /* not json */ }
    }
  });

  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/snapshots'), { timeout: 20_000 }),
    page.goto('/', { waitUntil: 'load' }),
  ]);
  const selector = page.locator('#snapshot-selector');
  await expect(selector).toBeVisible({ timeout: 20_000 });
  await selector.selectOption(gt.snapshotId);

  // Operator asks for the CFO dashboard (real UI event) — this renders the persona tiles.
  const search = page.locator('#nlq-search-input');
  await expect(search).toBeVisible({ timeout: 20_000 });
  await search.fill('show me the CFO dashboard');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/query') && r.request().method() === 'POST', { timeout: 60_000 }),
    search.press('Enter'),
  ]);
  await page.waitForTimeout(2500);

  // Backend resolved the Net Income tile to a real DCL-classified pnl.net_income value.
  const apiVal = Math.round(Number(cfo?.dashboard_data?.kpi_net_income?.value) * 100) / 100;
  expect(gt.netIncome, `kpi_net_income API value ${apiVal} must be a DCL-classified pnl.net_income`).toContainEqual(apiVal);

  // Frontend gate: the Net Income tile RENDERS that records-path value, not "No data".
  const tile = page.locator('[data-widget-id="kpi_net_income"]');
  await expect(tile, 'Net Income tile must render').toBeVisible({ timeout: 20_000 });
  await expect(tile, 'Net Income must show a value, not the prior "No data"').not.toContainText(/No data|unavailable/i);
  const rawShown = parseMoney((await tile.textContent()) || '');
  // DCL pnl.net_income is in $M (e.g. 113.84 = $113.84M); the tile may render it scaled
  // ("$113.8M" -> 113.8e6) or raw — normalize the rendered figure back to $M before comparing.
  const shownM = rawShown >= 1e4 ? rawShown / 1e6 : rawShown;
  const matches = gt.netIncome.some((v) => Math.abs(v - shownM) <= Math.max(0.5, Math.abs(v) * 0.02));
  expect(matches, `rendered Net Income ${rawShown} (=${shownM} $M) must equal a DCL pnl.net_income value ${JSON.stringify(gt.netIncome)}`).toBe(true);

  await page.screenshot({ path: 'tests/playwright/screenshots/cfo_dashboard_records_path.png', fullPage: true });
});
