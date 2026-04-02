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

  await page.goto('/', { waitUntil: 'load' });

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

  // Wait for pipeline_status response (banner depends on it)
  await page.waitForResponse(
    (res) => res.url().includes('/pipeline/status') && res.status() === 200,
    { timeout: 15_000 },
  );
  await page.waitForTimeout(1_000);

  // Banner shows snapshot name (human-readable per I2/I4) and timestamp
  // snapshot_name may be null if DCL snapshots are unavailable — check Updated: as baseline
  await expect(page.locator('text=Updated:')).toBeVisible({ timeout: 10_000 });
  const snapshotLabel = page.locator('text=Snapshot:');
  if (await snapshotLabel.isVisible()) {
    // Verify no raw UUID is displayed (I2/I4 compliance)
    const snapshotText = await snapshotLabel.locator('..').textContent();
    const uuidPattern = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
    expect(snapshotText, 'Snapshot label must not contain raw UUID').not.toMatch(uuidPattern);
    console.log('[provenance] Dashboard banner: snapshot_name visible, no UUID');
  } else {
    console.log('[provenance] Dashboard banner: snapshot_name not available (DCL snapshots empty)');
  }
  console.log('[provenance] Dashboard banner visible with provenance data');
});
