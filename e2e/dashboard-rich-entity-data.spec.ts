// Operator-visible outcome: with a rich entity (FluxEdge-TMZ8) as DCL's current entity, clicking the Dashboard tab renders a CFO dashboard of real financials — the Net Income tile shows "$100.1M" (= DCL pnl.net_income for the current quarter, 100.08), Revenue and Gross Margin tiles show real values, and the Sales Pipeline funnel + Revenue by Region map render — with no "No data", blank, or "stumped" tile anywhere.
/**
 * B17 acceptance — the CFO Dashboard renders REAL DATA for the current rich entity.
 *
 * The dashboard is snapshot-driven: the Dashboard tab auto-loads the CFO persona
 * dashboard for DCL's current entity. With a rich SE entity current, the persona
 * tiles populate. This test drives the operator path (click Dashboard) and asserts
 * the Net Income tile equals DCL ground truth pulled at test time (pnl.net_income
 * for the current quarter — never hardcoded), the other KPIs render values not
 * errors, and no failure surface ("No data" / "stumped") appears.
 *
 * Live-services acceptance: DCL (8104) + NLQ (8005) + frontend (3005). Read-only
 * page.request.get() to DCL/NLQ is the ground-truth source; no mutating call is made.
 */
import { test, expect, request as pwRequest } from 'playwright/test';

const DCL = 'http://localhost:8104';
const NLQ = 'http://localhost:8005';

function currentQuarter(): string {
  const d = new Date(); // matches App.tsx reference_date = today
  return `${d.getUTCFullYear()}-Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
}

// Ground truth: the current entity + its tenant, and the Net Income (pnl.net_income)
// DCL holds for it this quarter — the value the Net Income tile must show.
async function netIncomeGroundTruth() {
  const api = await pwRequest.newContext();
  const snaps = (await (await api.get(`${NLQ}/api/v1/snapshots`)).json()).snapshots || [];
  const latest = snaps.reduce((a: any, b: any) =>
    new Date(b.run_timestamp).getTime() > new Date(a.run_timestamp).getTime() ? b : a);
  const entity = latest.entity_id;
  const runs = (await (await api.get(`${DCL}/api/dcl/triples/runs`)).json()).runs || [];
  let tenant: string | undefined;
  for (const r of runs) { if (r.entity_summary && entity in r.entity_summary) { tenant = r.tenant_id; break; } }
  const browse = await (await api.get(
    `${DCL}/api/dcl/triples/browse?tenant_id=${tenant}&domain=pnl&entity_id=${entity}&limit=300`)).json();
  const q = currentQuarter();
  const ni = (browse.triples || []).find((t: any) => t.concept === 'pnl.net_income' && t.period === q);
  await api.dispose();
  return { entity, tenant, quarter: q, value: ni ? Number(ni.value) : NaN };
}

test('CFO dashboard renders real financials for the current rich entity = DCL ground truth', async ({ page }) => {
  const gt = await netIncomeGroundTruth();
  expect(Number.isFinite(gt.value), `DCL pnl.net_income[${gt.quarter}] for ${gt.entity} must exist`).toBe(true);

  // Capture the dashboard query response (the CFO persona query the tab auto-loads).
  let dashBody: any = null;
  page.on('response', async (res) => {
    if (res.url().includes('/api/v1/query') && res.request().method() === 'POST') {
      try { const b = await res.json(); if (b && b.dashboard_data) dashBody = b; } catch { /* not json */ }
    }
  });

  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/snapshots'), { timeout: 20_000 }),
    page.goto('/', { waitUntil: 'load' }),
  ]);

  // Operator clicks the Dashboard tab → it auto-loads the CFO dashboard for the current entity.
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/query') && r.request().method() === 'POST', { timeout: 60_000 }),
    page.getByRole('button', { name: /^Dashboard$/ }).click(),
  ]);
  await page.waitForTimeout(2500);

  // Backend computed the Net Income tile from the right entity's tenant: equals DCL ground truth.
  const niApi = Number(dashBody?.dashboard_data?.kpi_net_income?.value);
  expect(niApi, `kpi_net_income API value must equal DCL pnl.net_income[${gt.quarter}]`).toBeCloseTo(gt.value, 1);

  // Frontend is the gate: the Net Income tile RENDERS that value (scoped by its widget id).
  const niCard = page.locator('[data-widget-id="kpi_net_income"]');
  await expect(niCard, 'Net Income tile must render').toBeVisible({ timeout: 20_000 });
  await expect(niCard).toContainText(/Net Income/i);
  const niText = (await niCard.textContent()) || '';
  const niShown = Number((niText.match(/\$?([\d,]+(?:\.\d+)?)\s*M/i)?.[1] || '').replace(/,/g, ''));
  expect(niShown, `Net Income tile must render ~${gt.value} (got "${niText.trim()}")`).toBeCloseTo(gt.value, 0);

  // The other financial KPIs render real values — not "No data".
  for (const [wid, label] of [['kpi_revenue', 'Revenue'], ['kpi_gross_margin_pct', 'Gross Margin']]) {
    const card = page.locator(`[data-widget-id="${wid}"]`);
    await expect(card, `${label} tile must render`).toBeVisible({ timeout: 20_000 });
    await expect(card, `${label} must show a value, not an empty/error surface`).not.toContainText(/No data|Data unavailable|stumped/i);
    await expect(card).toContainText(/\d/); // a numeric value is present
  }

  // The pipeline funnel and the region breakdown render (real chart data, not empty).
  await expect(page.getByText(/Sales Pipeline/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Closed-Won/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/Revenue by Region/i).first()).toBeVisible({ timeout: 20_000 });

  // No failure surface anywhere on the dashboard — the operator sees data, not errors.
  const failures = await page.getByText(/No data for|Data unavailable|I'?m stumped|No pipeline stages|No regional data|No time series|No .* breakdown data/i).count();
  expect(failures, 'dashboard must show no "No data"/error tiles').toBe(0);

  await page.screenshot({ path: 'tests/playwright/screenshots/dashboard_rich_entity.png', fullPage: true });
});
