// Operator-visible outcome: the expanded DCL status light "Run ID" equals DCL's runs-API current run dcl_ingest_id (e.g. 0b1731a4 / HarborFlow), and when DCL's /api/health last_run_id diverges from that run, the rendered Run ID is the runs-API id, NOT the health id — proving NLQ reads run identity from the runs surface (GET /api/dcl/triples/runs), not the liveness health payload (dcl#69).
//
// Regression guard for the dcl#69 migration: if pipeline/status ever reverts to
// consuming the health payload's last_run_id, the rendered Run ID would drift off
// the real current run and this spec fails. Run identity is liveness-independent.
//
// Requirements: NLQ (3005 → 8005) + dev DCL (:8104) running, >=1 ingested run.
import { test, expect, request } from 'playwright/test';

const DCL = 'http://localhost:8104';

test('status light Run ID is sourced from the runs API, not the health payload', async ({ page }) => {
  // Ground truth — read-only GETs (allowed B17 exception): the authoritative
  // current run from the runs surface, plus the liveness health payload's id.
  const api = await request.newContext();
  const runsResp = await api.get(`${DCL}/api/dcl/triples/runs?limit=1`);
  const runsBody = await runsResp.json();
  const topRun = (runsBody.runs || runsBody)[0];
  const runsApiId = topRun.dcl_ingest_id as string;
  // A non-empty namespaced id also proves the runs API was reachable and returned a run.
  expect(runsApiId, 'runs API returns a current-run dcl_ingest_id').toMatch(/^[0-9a-f-]{8,}/);

  const healthResp = await api.get(`${DCL}/api/health`);
  const healthId = healthResp.ok() ? (await healthResp.json()).last_run_id : null;

  // Drive the real UI: open NLQ, expand the DataPipelineStatus panel.
  await page.goto('/', { waitUntil: 'load' });
  await page.waitForTimeout(3_000);
  await page.getByRole('button', { name: /^Live$|^Offline$/ }).first().click();

  const runIdCell = page
    .locator('text=Run ID')
    .locator('xpath=following-sibling::*[1]')
    .first();
  await expect(runIdCell, 'expanded status light shows a Run ID row').toBeVisible({ timeout: 10_000 });
  const rendered = ((await runIdCell.textContent()) || '').trim();

  // POSITIVE: the displayed run identity is the runs-API current run.
  expect(rendered, `status-light Run ID must equal runs-API current run ${runsApiId}`).toBe(runsApiId);

  // NEGATIVE (guarded so it is never flaky): only when the health payload's
  // last_run_id actually diverges from the current run do we assert the UI did
  // NOT pick up the health id. When they coincide the positive check suffices.
  if (healthId && healthId !== runsApiId) {
    expect(
      rendered,
      `status-light Run ID must NOT be the divergent health last_run_id ${healthId} (dcl#69: health is liveness, not run identity)`,
    ).not.toBe(healthId);
  }
});
