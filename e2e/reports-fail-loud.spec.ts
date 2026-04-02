/**
 * Reports fail loud — verifies ME reports return 503 when Convergence is down,
 * not silently falling back to DCL data (A1 violation).
 *
 * All checks in a single browser session to avoid WSL2 Chromium
 * --single-process crashes on context teardown.
 *
 * Requirements:
 *   - NLQ (8005/3005) + DCL (8004) running
 *   - Convergence (8010) NOT running
 */

import { test, expect } from 'playwright/test';

test('ME reports return 503 without Convergence (no silent DCL fallback)', async ({ page }) => {
  // All ME endpoints should return 503 when Convergence is not configured/running

  // ── 1. Combining statement ──
  const combining = await page.request.get('/api/reports/combining-is?period=FY+2025+Actual');
  expect(combining.status()).toBe(503);
  expect((await combining.text()).toLowerCase()).toContain('convergence');
  console.log(`[reports-fail-loud] Combining: HTTP ${combining.status()}`);

  // ── 2. Entity overlap ──
  const overlap = await page.request.get('/api/reports/entity-overlap');
  expect(overlap.status()).toBe(503);
  expect((await overlap.text()).toLowerCase()).toContain('convergence');
  console.log(`[reports-fail-loud] Entity overlap: HTTP ${overlap.status()}`);

  // ── 3. QoE ──
  const qoe = await page.request.get('/api/reports/qoe');
  expect(qoe.status()).toBe(503);
  expect((await qoe.text()).toLowerCase()).toContain('convergence');
  console.log(`[reports-fail-loud] QoE: HTTP ${qoe.status()}`);

  // ── 4. Cross-sell ──
  const crossSell = await page.request.get('/api/reports/cross-sell');
  expect(crossSell.status()).toBe(503);
  expect((await crossSell.text()).toLowerCase()).toContain('convergence');
  console.log(`[reports-fail-loud] Cross-sell: HTTP ${crossSell.status()}`);

  // ── 5. EBITDA bridge ──
  const bridge = await page.request.get('/api/reports/ebitda-bridge');
  expect(bridge.status()).toBe(503);
  expect((await bridge.text()).toLowerCase()).toContain('convergence');
  console.log(`[reports-fail-loud] EBITDA bridge: HTTP ${bridge.status()}`);

  // ── 6. What-if ──
  const whatIf = await page.request.post('/api/reports/what-if', {
    data: { preset: 'base' },
    headers: { 'Content-Type': 'application/json' },
  });
  expect(whatIf.status()).toBe(503);
  expect((await whatIf.text()).toLowerCase()).toContain('convergence');
  console.log(`[reports-fail-loud] What-if: HTTP ${whatIf.status()}`);
});
