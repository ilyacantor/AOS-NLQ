/**
 * Ask-view provenance across query types — "No Data" intermittency fix.
 *
 * Symptom: users reported an intermittent "No Data" badge. Not random —
 * tied to query routing. Single-metric queries ("what is revenue") flow
 * through v2.get_metric which stamps the provenance ctx var, so the
 * badge renders "Verified". Report queries ("show income statement")
 * flow through v2.get_all_metrics_by_period (and other report methods)
 * which never call _propagate_provenance, leaving ctx=None so the badge
 * renders "No Data" even though the underlying DCL HTTP read succeeded.
 *
 * This spec exercises both paths and asserts BOTH render "Verified" (or
 * at minimum, never "No Data"). Must fail on HEAD for the income
 * statement case; passes after the v2 client stamps provenance on
 * report-shape returns.
 *
 * B17 gate — UI is the pass/fail.
 *
 * Requirements:
 *   - NLQ backend (8005) + frontend (3005) + DCL (8004) running
 *   - At least one entity registered in DCL
 */

import { test, expect, request as pwRequest } from 'playwright/test';

interface ProbeCase {
  question: string;
  label: string;
}

const cases: ProbeCase[] = [
  { question: 'What is revenue for 2026 Q2?', label: 'single_metric' },
  { question: 'Show me the income statement', label: 'income_statement' },
  { question: 'CFO dashboard', label: 'dashboard' },
];

test.describe('Ask view provenance — every query type must render Verified', () => {
  for (const c of cases) {
    test(`${c.label}: "${c.question}" renders a real provenance badge`, async ({ page }) => {
      // Fetch entity via standalone context (single-process WSL2 config)
      const apiContext = await pwRequest.newContext();
      const entitiesResp = await apiContext.get('http://localhost:8005/api/v1/entities');
      expect(entitiesResp.ok()).toBeTruthy();
      const entitiesBody = await entitiesResp.json();
      const entities = entitiesBody.entities || [];
      expect(entities.length, 'no entities registered').toBeGreaterThan(0);
      await apiContext.dispose();

      // Abort non-localhost network
      await page.route('**/*', (route, request) => {
        if (request.url().includes('localhost')) route.continue();
        else route.abort();
      });

      // Wait for /api/v1/entities to complete during page load so the
      // frontend's auto-selection of list[0] is settled before submitting.
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

      await searchInput.fill(c.question);
      const [queryResponse] = await Promise.all([
        page.waitForResponse(
          (res) =>
            res.url().includes('/api/v1/query') &&
            res.request().method() === 'POST',
          { timeout: 60_000 },
        ),
        searchInput.press('Enter'),
      ]);
      expect(
        queryResponse.ok(),
        `/api/v1/query returned ${queryResponse.status()}`,
      ).toBeTruthy();

      const body = await queryResponse.json();
      const prov = body.provenance;
      const ds = body.data_source;
      const mode = prov?.mode ?? null;
      console.log(
        `[${c.label}] data_source=${ds} mode=${mode} value=${body.value} success=${body.success}`,
      );

      // Core assertion — the root cause check. Must have provenance with a real mode.
      expect(
        prov,
        `response.provenance must be present (${c.label}) — got ${JSON.stringify(prov)}`,
      ).not.toBeNull();
      expect(prov, 'response.provenance must be defined').toBeDefined();
      expect(
        mode,
        `response.provenance.mode must not be null (${c.label}) — this is the "No Data" bug`,
      ).not.toBeNull();
      const modeLower = String(mode).toLowerCase();
      expect(
        ['ingest', 'live', 'farm'],
        `mode=${modeLower} not in real set`,
      ).toContain(modeLower);

      // UI assertion — badge must render Verified or Simulation, never "No Data"
      const noDataBadge = page.getByText('No Data', { exact: true });
      await expect(
        noDataBadge,
        `Ask view must not render "No Data" for ${c.label}`,
      ).toHaveCount(0, { timeout: 10_000 });
    });
  }
});
