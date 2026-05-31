// Operator-visible outcome: the persona dropdown lists exactly 5 personas (CFO, CRO, COO, CTO, CHRO) with NO "Cloud Cost Optimization" option; the CTO dashboard renders a "Cloud Spend" KPI tile as the 2nd card and the CFO dashboard renders it as the 4th card (FinOps is a domain → CTO primary, CFO secondary); and an Ask answer for "revenue for 2025" returns provenance.per_triple with one source-tagged entry per contributing quarter.
/**
 * AAM Blueprint v3.1 decision (d) + §9.2 — NLQ acceptance.
 *
 * (1) FinOps is a domain, not a persona: the lone file persona (finops.yaml)
 *     and the "Cloud Cost Optimization" (CCO) dropdown persona are removed.
 *     cloud_spend surfaces on the CTO dashboard (primary) and CFO dashboard
 *     (secondary) via the persona-domain mapping — verified as a rendered tile.
 * (2) NLQ Ask carries per-triple provenance to match the Dashboards path.
 *
 * B17 gate — UI-driven (dropdown selectOption + search input), real clicks.
 * Requirements: NLQ backend (8005) + frontend (3005) + DCL (8004) running,
 * with at least one non-finops SE snapshot ingested.
 */
import { test, expect, request as pwRequest } from 'playwright/test';

// The 5 human-role personas after the FinOps-as-persona removal (decision (d)).
const EXPECTED_PERSONAS = ['CFO', 'CRO', 'COO', 'CTO', 'CHRO'];

async function pickRichSnapshotId(): Promise<string> {
  // Read-only ground-truth fetch (allowed exception): choose a non-finops
  // snapshot with real financial/operational data so dashboards render.
  const api = await pwRequest.newContext();
  const resp = await api.get('http://localhost:8005/api/v1/snapshots');
  expect(resp.status(), 'GET /api/v1/snapshots failed').toBeLessThan(300);
  const body = await resp.json();
  await api.dispose();
  const snaps: Array<{ entity_id: string; dcl_ingest_id: string; total_rows: number }> =
    body.snapshots || [];
  const rich = snaps
    .filter((s) => !s.entity_id.startsWith('finops-demo') && s.total_rows >= 5000)
    .sort((a, b) => b.total_rows - a.total_rows)[0];
  expect(rich, 'no rich non-finops snapshot available').toBeDefined();
  return rich.dcl_ingest_id;
}

test.describe('FinOps-as-domain: cloud_spend on CTO/CFO + Ask per-triple provenance', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/*', (route, req) =>
      req.url().includes('localhost') ? route.continue() : route.abort(),
    );
  });

  test('persona dropdown has the 5 role personas and NO FinOps/CCO option', async ({ page }) => {
    await page.goto('/', { waitUntil: 'load' });
    await page.locator('#nav-tab-dashboard').click();
    const personaSelect = page.locator('#dashboard-persona-select');
    await expect(personaSelect).toBeVisible({ timeout: 15_000 });

    const optionValues = await personaSelect.locator('option').evaluateAll((els) =>
      els.map((e) => (e as HTMLOptionElement).value),
    );
    const optionLabels = await personaSelect.locator('option').evaluateAll((els) =>
      els.map((e) => (e.textContent || '').trim()),
    );
    expect(optionValues).toEqual(EXPECTED_PERSONAS);
    // The deleted FinOps persona must not reappear under any label/value.
    expect(optionValues).not.toContain('CCO');
    for (const label of optionLabels) {
      expect(label.toLowerCase()).not.toContain('cloud cost optimization');
      expect(label.toLowerCase()).not.toContain('finops');
    }
  });

  test('CTO dashboard renders a "Cloud Spend" KPI tile as the 2nd card (primary)', async ({ page }) => {
    const snapId = await pickRichSnapshotId();
    await page.goto('/', { waitUntil: 'load' });
    await page.locator('#nav-tab-dashboard').click();
    await expect(page.locator('#dashboard-persona-select')).toBeVisible({ timeout: 15_000 });
    await page.locator('#snapshot-selector').selectOption(snapId);
    await page.locator('#dashboard-persona-select').selectOption('CTO');

    // Switching to the Dashboard tab auto-renders the default (CFO) dashboard,
    // so wait for the CTO-distinctive first tile ("Uptime") before asserting —
    // confirms the CTO regeneration finished, not a stale CFO grid.
    await expect(page.locator('.react-grid-layout')).toBeVisible({ timeout: 30_000 });
    const firstKpi = page.locator('.react-grid-item h3').first();
    await expect(firstKpi).toHaveText('Uptime', { timeout: 30_000 });

    const kpiTitles = await page.locator('.react-grid-item h3').allTextContents();
    // cloud_spend is routed to CTO as primary → 2nd KPI in the pack.
    expect(kpiTitles).toContain('Cloud Spend');
    expect(kpiTitles.indexOf('Cloud Spend')).toBe(1);
    await expect(page.getByRole('heading', { name: 'Cloud Spend' }).first()).toBeVisible({ timeout: 5_000 });
    await page.screenshot({ path: 'test-results/cto-dashboard-cloud-spend.png', fullPage: true });
  });

  test('CFO dashboard renders a "Cloud Spend" KPI tile as the 4th card (secondary)', async ({ page }) => {
    const snapId = await pickRichSnapshotId();
    await page.goto('/', { waitUntil: 'load' });
    await page.locator('#nav-tab-dashboard').click();
    await expect(page.locator('#dashboard-persona-select')).toBeVisible({ timeout: 15_000 });
    await page.locator('#snapshot-selector').selectOption(snapId);
    await page.locator('#dashboard-persona-select').selectOption('CFO');

    await expect(page.locator('.react-grid-layout')).toBeVisible({ timeout: 30_000 });
    // Wait for the CFO-distinctive first tile ("Revenue") so we assert against
    // the CFO grid, not a transitional render.
    const firstKpi = page.locator('.react-grid-item h3').first();
    await expect(firstKpi).toHaveText('Revenue', { timeout: 30_000 });

    const kpiTitles = await page.locator('.react-grid-item h3').allTextContents();
    // cloud_spend is routed to CFO as secondary → 4th KPI, below the P&L lines.
    expect(kpiTitles).toContain('Cloud Spend');
    expect(kpiTitles.indexOf('Cloud Spend')).toBe(3);
    expect(kpiTitles.slice(0, 3)).toEqual(['Revenue', 'Gross Margin', 'Net Income']);
    await page.screenshot({ path: 'test-results/cfo-dashboard-cloud-spend.png', fullPage: true });
  });

  test('Ask answer carries per-triple provenance (one source-tagged entry per quarter)', async ({ page }) => {
    const snapId = await pickRichSnapshotId();
    await page.goto('/', { waitUntil: 'load' });
    const searchInput = page.locator('#nlq-search-input');
    await expect(searchInput).toBeVisible({ timeout: 15_000 });
    await page.locator('#snapshot-selector').selectOption(snapId);

    await searchInput.fill('what is our revenue for 2025');
    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes('/api/v1/query') && r.request().method() === 'POST',
        { timeout: 60_000 },
      ),
      searchInput.press('Enter'),
    ]);
    expect(resp.status(), '/api/v1/query failed').toBeLessThan(300);
    const body = await resp.json();
    const prov = body.provenance;

    // Run-level provenance still present and real (not "No Data").
    expect(prov, 'response.provenance missing').toBeDefined();
    expect(['ingest', 'live', 'farm']).toContain(String(prov.mode).toLowerCase());
    await expect(page.getByText('No Data', { exact: true })).toHaveCount(0, { timeout: 10_000 });

    // Per-triple provenance — the §9.2 deliverable. FY2025 aggregates 4
    // quarterly triples, so per_triple has one provenance entry per quarter,
    // each tagged with the source system that produced it.
    const perTriple = prov.per_triple;
    expect(Array.isArray(perTriple), 'provenance.per_triple must be an array').toBe(true);
    // FY2025 = 4 quarterly contributing triples → 4 per-triple entries.
    expect(perTriple.length).toBe(4);
    for (const entry of perTriple) {
      // Each contributing triple's source is drawn from the run-level source
      // set (per-triple provenance ⊆ run provenance) — not fabricated.
      expect(prov.source_systems).toContain(entry.source_system);
    }
  });
});
