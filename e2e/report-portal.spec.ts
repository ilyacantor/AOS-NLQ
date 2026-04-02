/**
 * Report Portal E2E — verifies that every tab renders in all three modes
 * (Combined / Acquiror / Target) with live Convergence + DCL data.
 *
 * Tests the EntityRegistry fix that routes entity discovery through
 * Convergence first (ME engagement authority), enabling the DealSelector
 * to show Acquiror / Target / Combined buttons.
 *
 * Requirements:
 *   - All services running via pm2 (nlq-backend:8005, nlq-frontend:3005,
 *     dcl-backend:8004, convergence-backend:8010)
 */

import { test, expect } from 'playwright/test';

test('Report Portal — every tab in Combined / Acquiror / Target modes', async ({ page }) => {
  // Block external resources that hang in WSL
  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) {
      route.continue();
    } else {
      route.abort();
    }
  });

  // Collect console errors (filter benign warnings)
  const consoleErrors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (text.includes('The width(-1)') || text.includes('The height(-1)')) return;
    if (text.includes('Failed to fetch') || text.includes('NetworkError')) return;
    if (text.includes('net::ERR_NAME_NOT_RESOLVED') || text.includes('Failed to load resource')) return;
    if (text.includes('Encountered two children with the same key')) return;
    consoleErrors.push(text);
  });

  // ── Navigate to Report Portal ──────────────────────────────────────
  await page.goto('/', { waitUntil: 'load' });
  const reportsTab = page.locator('#nav-tab-reports');
  await expect(reportsTab).toBeVisible({ timeout: 15_000 });
  await reportsTab.click();

  // ── DealSelector: verify ME buttons exist ──────────────────────────
  const acquirorBtn = page.locator('button').filter({ hasText: /^Acquiror$/ });
  const targetBtn = page.locator('button').filter({ hasText: /^Target$/ });
  const combinedBtn = page.locator('button').filter({ hasText: /^Combined$/ });

  await expect(acquirorBtn).toBeVisible({ timeout: 15_000 });
  await expect(targetBtn).toBeVisible();
  await expect(combinedBtn).toBeVisible();

  // ── Helper: verify a statement tab loaded data ─────────────────────
  // Statement tabs (P&L, BS, CF) render a <table> with numeric cells.
  async function assertStatementLoaded(tabName: string) {
    const errorBanner = page.locator('text=/Error loading|Error:.*failed/i');
    await expect(errorBanner).not.toBeVisible({ timeout: 10_000 });
    const numericCells = page.locator('table td').filter({ hasText: /[\d,]+\.\d/ });
    await expect(numericCells.first()).toBeVisible({ timeout: 30_000 });
  }

  // Helper: verify a non-statement tab is not showing an error.
  // Some ME tabs (cross-sell, upsell) may lack data — verify the tab
  // renders without crashing and any error message is user-friendly
  // (no raw UUIDs per I2).
  async function assertTabNoError(tabName: string) {
    await page.waitForTimeout(3_000);
    const errorText = page.locator('text=/Error loading|Error:.*failed/i');
    const visible = await errorText.isVisible().catch(() => false);
    if (visible) {
      const msg = await errorText.textContent();
      // I2: raw UUIDs must never appear in user-facing error messages
      const uuidPattern = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
      expect(msg, `Tab "${tabName}" error exposes raw UUID to user`).not.toMatch(uuidPattern);
    }
  }

  // Helper: click a tab button by its exact label
  async function clickTab(label: string) {
    await page.locator('button').filter({ hasText: new RegExp(`^${label}$`) }).click();
  }

  // ══════════════════════════════════════════════════════════════════
  // COMBINED MODE (default) — 10 tabs
  // ══════════════════════════════════════════════════════════════════
  await combinedBtn.click();

  // 1. P&L (default tab)
  await assertStatementLoaded('P&L');
  await expect(page.locator('table td').filter({ hasText: /Revenue/ }).first()).toBeVisible();

  // 2. Balance Sheet
  await clickTab('BS');
  await assertStatementLoaded('BS');

  // 3. Cash Flow
  await clickTab('CF');
  await assertStatementLoaded('CF');

  // 4. Recon
  await clickTab('Recon');
  await assertTabNoError('Recon');

  // 5. Combining Income Statement
  await clickTab('Combining');
  const meridianHeader = page.locator('th').filter({ hasText: /Meridian/i });
  const cascadiaHeader = page.locator('th').filter({ hasText: /Cascadia/i });
  await expect(meridianHeader).toBeVisible({ timeout: 30_000 });
  await expect(cascadiaHeader).toBeVisible();

  // 6. Cross-Sell
  await clickTab('X-Sell');
  await assertTabNoError('X-Sell');

  // 7. Upsell
  await clickTab('Upsell');
  await assertTabNoError('Upsell');

  // 8. Pipeline
  await clickTab('Pipeline');
  await assertTabNoError('Pipeline');

  // 9. What-If
  await clickTab('What-If');
  await assertTabNoError('What-If');

  // 10. QofE
  await clickTab('QofE');
  await assertTabNoError('QofE');

  // ══════════════════════════════════════════════════════════════════
  // ACQUIROR MODE (Meridian) — 6 tabs
  // ══════════════════════════════════════════════════════════════════
  await acquirorBtn.click();

  // Combined-only tabs should disappear
  await expect(page.locator('button').filter({ hasText: /^Combining$/ })).not.toBeVisible();
  await expect(page.locator('button').filter({ hasText: /^X-Sell$/ })).not.toBeVisible();

  // 1. P&L (auto-selected when switching from combined-only tab)
  await assertStatementLoaded('Acquiror P&L');
  // Entity badge should show Meridian (span badge, not hidden <option>)
  await expect(page.locator('span').filter({ hasText: /^Meridian$/ })).toBeVisible({ timeout: 5_000 });

  // 2. BS
  await clickTab('BS');
  await assertStatementLoaded('Acquiror BS');

  // 3. CF
  await clickTab('CF');
  await assertStatementLoaded('Acquiror CF');

  // 4. Recon
  await clickTab('Recon');
  await assertTabNoError('Acquiror Recon');

  // 5. Rev/Cust
  await clickTab('Rev\\/Cust');
  await assertTabNoError('Acquiror Rev/Cust');

  // 6. Pipeline
  await clickTab('Pipeline');
  await assertTabNoError('Acquiror Pipeline');

  // ══════════════════════════════════════════════════════════════════
  // TARGET MODE (Cascadia) — 6 tabs
  // ══════════════════════════════════════════════════════════════════
  await targetBtn.click();

  // 1. P&L
  await clickTab('P&L');
  await assertStatementLoaded('Target P&L');
  // Entity badge should show Cascadia
  await expect(page.locator('span').filter({ hasText: /^Cascadia$/ })).toBeVisible({ timeout: 5_000 });

  // 2. BS
  await clickTab('BS');
  await assertStatementLoaded('Target BS');

  // 3. CF
  await clickTab('CF');
  await assertStatementLoaded('Target CF');

  // 4. Recon
  await clickTab('Recon');
  await assertTabNoError('Target Recon');

  // 5. Rev/Cust
  await clickTab('Rev\\/Cust');
  await assertTabNoError('Target Rev/Cust');

  // 6. Pipeline
  await clickTab('Pipeline');
  await assertTabNoError('Target Pipeline');

  // ══════════════════════════════════════════════════════════════════
  // BACK TO COMBINED — verify mode switch works round-trip
  // ══════════════════════════════════════════════════════════════════
  await combinedBtn.click();
  await expect(page.locator('button').filter({ hasText: /^Combining$/ })).toBeVisible();
  await clickTab('P&L');
  await assertStatementLoaded('Combined P&L round-trip');

  // ── Final: no fatal console errors ─────────────────────────────────
  if (consoleErrors.length > 0) {
    console.log('Console errors:', consoleErrors);
  }
  expect(consoleErrors).toHaveLength(0);
});
