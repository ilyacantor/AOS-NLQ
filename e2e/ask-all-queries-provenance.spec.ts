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
  { question: 'why did rev incr', label: 'why_did_rev_incr' },
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

      // Wait for /api/v1/snapshots — the frontend derives entity_id from the
      // active surface's effective snapshot (App.tsx:181 askEntityId). The old
      // /api/v1/entities mount-fetch was removed; identity is now snapshot-driven.
      const [snapshotsLoaded] = await Promise.all([
        page.waitForResponse(
          (res) =>
            res.url().includes('/api/v1/snapshots') &&
            res.request().method() === 'GET',
          { timeout: 15_000 },
        ),
        page.goto('/', { waitUntil: 'load' }),
      ]);
      expect(snapshotsLoaded.status()).toBeLessThan(300);

      const searchInput = page.locator('#nlq-search-input');
      await expect(searchInput).toBeVisible({ timeout: 15_000 });

      // Cases that need a revenue model (why_did_rev_incr, single_metric,
      // income_statement, dashboard) only work against entities whose triples
      // carry revenue/expansion/renewal — i.e. SE-shape snapshots, not the
      // finops-demo-co subset. Operator picks an appropriate snapshot from
      // the dropdown when the ★ default doesn't fit. The selection itself is
      // the dropdown-as-intended behavior: select an option → query body
      // carries that snapshot_id and entity_id.
      const snapshotsBody = await snapshotsLoaded.json();
      const allSnaps: Array<{ entity_id: string; dcl_ingest_id: string; total_rows: number }> =
        snapshotsBody.snapshots || [];
      const revenueSnap = allSnaps.find(
        (s) => !s.entity_id.startsWith('finops-demo') && s.total_rows >= 5000,
      );
      if (revenueSnap) {
        await page.locator('#snapshot-selector').selectOption(revenueSnap.dcl_ingest_id);
        // Selection landed and React state propagated (pinned badge flips).
        await expect(page.locator('#snapshot-selector')).toHaveValue(revenueSnap.dcl_ingest_id);
        await expect(
          page.locator('[data-role="snapshot-follow-state"]').first(),
        ).toHaveText('pinned', { timeout: 5_000 });
      }

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

      // Stumped/clarification fallback must not surface — answer text must be
      // a real answer, never the personality.py STUMPED_RESPONSES /
      // STUMPED_WITH_SUGGESTIONS catalog.
      const answer = (body.answer || '').toString();
      const stumpedMarkers = [
        "I'm stumped",
        "I'm not sure what you mean",
        "stumped me",
        "scratching my silicon head",
        "circuits are confused",
        "404: Answer not found",
        "above my pay grade",
      ];
      for (const marker of stumpedMarkers) {
        expect(
          answer,
          `Ask answer for ${c.label} contains stumped fallback "${marker}" — query did not produce a real answer`,
        ).not.toContain(marker);
      }

      // Stuck-spinner guard — the LiveDataWaitingBanner ("Waiting for DCL live
      // data pipeline") must not be visible once the response has landed.
      const waitingBanner = page.getByText(/Waiting for DCL live data pipeline/);
      await expect(
        waitingBanner,
        `Stuck-spinner banner visible for ${c.label} — DCL ingest state unhealthy`,
      ).toHaveCount(0, { timeout: 5_000 });

      // Per-case strict checks for the literal preset query the operator types.
      if (c.label === 'why_did_rev_incr') {
        // Real, content-bearing answer with at least one breakdown component.
        expect(
          answer.length,
          'why did rev incr answer must be non-empty',
        ).toBeGreaterThan(20);
        // Backend returns BREAKDOWN_QUERY with a 3-component revenue breakdown.
        expect(
          (body.parsed_intent || '').toUpperCase(),
          'why did rev incr must be classified as BREAKDOWN_QUERY',
        ).toBe('BREAKDOWN_QUERY');
        expect(
          body.resolved_metric,
          'why did rev incr must resolve to the revenue metric',
        ).toBe('revenue');
        // The structured value carries the three revenue components — multi-element.
        const breakdown = body.value?.breakdown;
        expect(breakdown, 'value.breakdown must be present').toBeDefined();
        expect(
          Object.keys(breakdown || {}).length,
          'breakdown must carry more than one component',
        ).toBeGreaterThan(1);
        // Confidence must be high (the known-good handler returns 0.95).
        expect(
          body.confidence,
          'why did rev incr must return a confident answer',
        ).toBeGreaterThanOrEqual(0.8);
      }
    });
  }
});
