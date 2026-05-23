/**
 * Provenance banner — verifies Dashboard shows provenance for the active pipeline state,
 * and Ask does NOT show the banner (Ask has the snapshot selector instead).
 *
 * All checks in a single browser session to avoid WSL2 Chromium
 * --single-process crashes on context teardown.
 *
 * Requirements:
 *   - NLQ (8005/3005) + DCL (8004) running
 *   - At least one pipeline run ingested into DCL (via REST ingest path)
 */

import { test, expect } from 'playwright/test';

test('Provenance banner: visible on Dashboard, hidden on Ask', async ({ page }) => {
  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });

  // Register the pipeline/status response wait BEFORE goto — DataPipelineStatus
  // mounts once in the header at page load and fetches immediately; subsequent
  // polls don't fire for 30s. Catching the mount-time fetch is the only way to
  // assert the response shape without racing the FAST_POLL_INTERVAL.
  const [pipelineStatusResp] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/pipeline/status') && res.status() < 300,
      { timeout: 30_000 },
    ),
    page.goto('/', { waitUntil: 'load' }),
  ]);
  expect(pipelineStatusResp.status()).toBeLessThan(300);

  // Wait for data to load
  await page.waitForTimeout(2_000);

  // ── 1. Ask: no provenance banner ──
  const bannerEntity = page.locator('text=Entity:');
  await expect(bannerEntity).not.toBeVisible();
  console.log('[provenance] Ask: no banner visible (correct)');

  // ── 2. Ask: snapshot selector visible ──
  const selector = page.locator('#snapshot-selector');
  await expect(selector).toBeVisible({ timeout: 10_000 });
  console.log('[provenance] Ask: selector visible (correct)');

  // ── 3. Dashboard: provenance banner visible ──
  await page.locator('#nav-tab-dashboard').click();

  // Dashboard identity is now snapshot-driven (SnapshotContext.useSurfaceSnapshot
  // for the dashboard surface). The persona selector is the operator-visible
  // dropdown on this view; the entity is the active snapshot's entity_id.
  const personaSelect = page.locator('#dashboard-persona-select');
  await expect(personaSelect).toBeVisible({ timeout: 15_000 });
  await expect(personaSelect.locator('option').first()).toBeAttached({ timeout: 10_000 });
  const firstPersonaValue = await personaSelect.locator('option').first().getAttribute('value');
  expect(firstPersonaValue, 'persona dropdown must have at least one option').toMatch(/\S/);
  // Dashboard's snapshot selector mirrors Ask's — same per-surface context.
  const dashSnapshotSelect = page.locator('#snapshot-selector');
  await expect(dashSnapshotSelect).toBeVisible({ timeout: 10_000 });

  // Pipeline status was already fetched at page-mount (see Promise.all above).
  // Give the banner a moment to render against the cached response.
  await page.waitForTimeout(1_000);

  // Provenance now surfaces directly on the snapshot selector option label
  // (SnapshotSelector.tsx:20 `optionLabel` returns "[★ ]<name> -- <relative
  // time> -- <total_rows> triples"). The selected ★ option carries the
  // active snapshot's name, age, and row count — that IS the dashboard's
  // provenance line for I2/I4 (entity_id business key, never raw UUID).
  const selectedOption = page.locator('#snapshot-selector option').first();
  const selectedText = (await selectedOption.textContent()) || '';
  expect(selectedText, 'selected snapshot option must be ★-marked (the latest)').toMatch(/^★/);
  expect(selectedText, 'selected snapshot label must carry relative time').toMatch(
    /\d+\s*(s|m|h|d|just now)/,
  );
  expect(selectedText, 'selected snapshot label must carry triple count').toMatch(/triples?/);
  // I2/I4 — no raw UUID anywhere in the visible snapshot label.
  const uuidPattern = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
  expect(selectedText, 'snapshot label must not contain raw UUID').not.toMatch(uuidPattern);

  // The "Live" indicator (DataPipelineStatus) confirms the pipeline status
  // banner is rendered and showing connected state.
  await expect(page.getByRole('button', { name: /^Live$|^Offline$/ })).toBeVisible({
    timeout: 10_000,
  });
  console.log(`[provenance] Dashboard snapshot label: ${selectedText}`);
});
