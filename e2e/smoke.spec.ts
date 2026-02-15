/**
 * Smoke Test — "Front-End Truth"
 *
 * This test scripts a real browser session against the running app.
 * It exercises the two primary views (Galaxy → Dashboard) and verifies
 * that the dashboard grid actually renders interactive widgets.
 *
 * If this test fails, the refactor has broken something user-visible.
 *
 * Requirements:
 *   - Backend running on localhost:8000  (uvicorn src.nlq.main:app)
 *   - Frontend built + preview on localhost:5000  (npx vite preview)
 *     OR Vite dev server on localhost:5000  (npx vite)
 */

import { test, expect } from 'playwright/test';

test.describe('AOS-NLQ Smoke Test', () => {

  test('full app lifecycle: Galaxy → Dashboard → widget interaction', async ({ page }) => {
    // ── Collect console errors (not warnings) throughout ──
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text();
        // Ignore known benign Recharts dimension warnings during initial layout
        if (text.includes('The width(-1)') || text.includes('The height(-1)')) return;
        // Ignore network errors from optional services (RAG polling, etc.)
        if (text.includes('Failed to fetch') || text.includes('NetworkError')) return;
        // Ignore DNS / resource load failures for external CDNs
        if (text.includes('net::ERR_NAME_NOT_RESOLVED')) return;
        if (text.includes('Failed to load resource')) return;
        consoleErrors.push(text);
      }
    });

    // ── Abort non-localhost requests ──
    // External stylesheet loads (Google Fonts, unpkg Leaflet CSS) are
    // script-blocking. In CI/sandbox where DNS doesn't resolve, they
    // hang indefinitely and prevent the JS bundle from executing.
    // Aborting them lets the app load instantly.
    await page.route('**/*', (route, request) => {
      if (request.url().includes('localhost')) {
        route.continue();
      } else {
        route.abort();
      }
    });

    // ── Step 1: Load the app — should land on Galaxy View ──
    await page.goto('/', { waitUntil: 'load' });

    // The NLQ branding should be visible in the header
    const header = page.locator('header');
    await expect(header).toBeVisible();

    // The search input should be present (Galaxy view has the chatbox)
    const searchInput = page.locator('#nlq-search-input');
    await expect(searchInput).toBeVisible({ timeout: 10_000 });

    // The Galaxy tab should be the active one (desktop header)
    const galaxyTab = page.locator('#nav-tab-galaxy');
    await expect(galaxyTab).toBeVisible();

    // ── Step 2: Click the Dashboard tab ──
    const dashboardTab = page.locator('#nav-tab-dashboard');
    await expect(dashboardTab).toBeVisible();
    await dashboardTab.click();

    // ── Step 3: Wait for the dashboard grid to render ──
    // Clicking Dashboard triggers generateDashboard → /api/v1/query/dashboard.
    // The proxy in vite.config.ts forwards /api → localhost:8000.
    // For production preview, the backend runs directly on port 8000, and the
    // app's fetchWithRetry hits /api/v1/... which the preview server serves
    // from the vite proxy config or the browser hits directly.
    //
    // We wait for .react-grid-layout which only mounts when schema is loaded.
    const gridLayout = page.locator('.react-grid-layout');
    await expect(gridLayout).toBeVisible({ timeout: 30_000 });

    // Verify that actual widgets rendered inside the grid.
    // react-grid-layout wraps each child in a .react-grid-item div.
    const gridItems = gridLayout.locator('.react-grid-item');
    const itemCount = await gridItems.count();
    expect(itemCount).toBeGreaterThan(0);

    // ── Step 4: Verify widget content is real (not empty placeholders) ──
    // Each widget should have a title rendered as an h3
    const firstWidgetTitle = gridItems.first().locator('h3');
    await expect(firstWidgetTitle).toBeVisible({ timeout: 10_000 });
    const titleText = await firstWidgetTitle.textContent();
    expect(titleText).toBeTruthy();
    expect(titleText!.length).toBeGreaterThan(0);

    // ── Step 5: Click a widget to test interactivity ──
    const firstItem = gridItems.first();
    await firstItem.click();
    // The click should not crash the app. The grid should still be visible.
    await expect(gridLayout).toBeVisible();

    // ── Step 6: Verify no fatal console errors accumulated ──
    if (consoleErrors.length > 0) {
      console.log('Console errors collected:', consoleErrors);
    }
    expect(consoleErrors).toHaveLength(0);
  });
});
