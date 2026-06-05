// Operator-visible outcome: with a NEW-WAY records-path entity current (FabricDemo, whose data DCL classified from records — fabric_plane=warehouse, source=aws_cost_explorer, NOT pre-formed SE ingest-triples), its dashboard's Cloud Spend tile renders the value DCL classified from the warehouse plane (~$128,914 = DCL ground truth), proving a new-way entity populates the dashboard from records with no old SE crutch. (The P&L tiles stay red because the records-path produces no P&L — the held SE-path cutover — surfaced, never hidden.)
/**
 * B17 — does a NEW-WAY entity populate the dashboards, with no old SE crutch?
 *
 * FluxEdge-TMZ8 populated a full CFO dashboard only because its triples came via the OLD
 * SE path (Farm -> /api/dcl/ingest-triples, pre-formed canonical concepts). That proves
 * nothing about the new architecture. This test uses a RECORDS-PATH entity — driven
 * source -> AAM transport -> /api/dcl/ingest-records, where DCL classifies records into
 * concepts (the four-fabric pipeline, POST /api/aam/operator/fabric/run). It proves the
 * entity is new-way by checking records-path provenance on its triples (fabric_plane /
 * source_system), then asserts the dashboard tile for a metric the records-path PRODUCES
 * (cloud_spend, from the warehouse plane) renders DCL's classified value.
 *
 * Prerequisite (B15): the four-fabric pipeline has run for the current entity
 * (POST /api/aam/operator/fabric/run). Live-services: DCL 8104 + NLQ 8005 + frontend 3005.
 * Read-only page.request.get only.
 */
import { test, expect, request as pwRequest } from 'playwright/test';

const DCL = 'http://localhost:8104';
const NLQ = 'http://localhost:8005';

// The current entity, its tenant, the classified cloud_spend total, and the records-path
// provenance marker — all from DCL at test time.
async function recordsPathGroundTruth() {
  const api = await pwRequest.newContext();
  const snaps = (await (await api.get(`${NLQ}/api/v1/snapshots`)).json()).snapshots || [];
  const latest = snaps.reduce((a: any, b: any) =>
    new Date(b.run_timestamp).getTime() > new Date(a.run_timestamp).getTime() ? b : a);
  const entity = latest.entity_id;
  const runs = (await (await api.get(`${DCL}/api/dcl/triples/runs`)).json()).runs || [];
  let tenant: string | undefined;
  for (const r of runs) { if (r.entity_summary && entity in r.entity_summary) { tenant = r.tenant_id; break; } }
  const browse = await (await api.get(
    `${DCL}/api/dcl/triples/browse?tenant_id=${tenant}&entity_id=${entity}&domain=cloud_spend&limit=200`)).json();
  const triples = browse.triples || [];
  const total = triples.find((t: any) => t.concept === 'cloud_spend.summary' && t.property === 'total_cost');
  const provenanced = triples.find((t: any) => t.fabric_plane) || {};
  await api.dispose();
  return {
    entity, tenant,
    cloudSpend: total ? Number(total.value) : NaN,
    fabricPlane: provenanced.fabric_plane,
    sourceSystem: provenanced.source_system,
  };
}

function parseMoney(text: string): number {
  const m = text.match(/\$?\s*([\d,]+(?:\.\d+)?)\s*([KMB])?/i);
  if (!m) return NaN;
  let n = Number(m[1].replace(/,/g, ''));
  const suf = (m[2] || '').toUpperCase();
  if (suf === 'K') n *= 1e3; else if (suf === 'M') n *= 1e6; else if (suf === 'B') n *= 1e9;
  return n;
}

test('a new-way records-path entity populates its dashboard tile from records (no SE crutch)', async ({ page }) => {
  const gt = await recordsPathGroundTruth();
  // The current entity must be NEW-WAY: its triples carry records-path provenance
  // (a warehouse/AWS fabric plane), not pre-formed SE ingest-triples.
  expect(gt.fabricPlane, `entity ${gt.entity} must be records-path (fabric_plane set), not an SE crutch`).toBe('warehouse');
  expect(Number.isFinite(gt.cloudSpend), `DCL must hold a classified cloud_spend total for ${gt.entity}`).toBe(true);

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
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/query') && r.request().method() === 'POST', { timeout: 60_000 }),
    page.getByRole('button', { name: /^Dashboard$/ }).click(),
  ]);
  await page.waitForTimeout(2500);

  // Backend classified the warehouse plane's records into the Cloud Spend tile = DCL ground truth.
  const csApi = Number(dashBody?.dashboard_data?.kpi_cloud_spend?.value);
  expect(csApi, 'kpi_cloud_spend API value must equal the DCL-classified cloud_spend total').toBeCloseTo(gt.cloudSpend, 1);

  // Frontend gate: the Cloud Spend tile RENDERS that records-path value (scoped by widget id).
  const csCard = page.locator('[data-widget-id="kpi_cloud_spend"]');
  await expect(csCard, 'Cloud Spend tile must render').toBeVisible({ timeout: 20_000 });
  await expect(csCard, 'Cloud Spend must show a value, not an empty surface').not.toContainText(/No data|Data unavailable/i);
  const shown = parseMoney((await csCard.textContent()) || '');
  expect(shown, `Cloud Spend tile must render ~$${gt.cloudSpend} (the records-path value)`).toBeGreaterThan(gt.cloudSpend * 0.95);
  expect(shown).toBeLessThan(gt.cloudSpend * 1.05);

  await page.screenshot({ path: 'tests/playwright/screenshots/dashboard_newway_entity.png', fullPage: true });
});
