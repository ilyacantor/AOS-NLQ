/**
 * PR 2 — Dashboards view shows the "Pick an entity" empty state before a
 * selection is made, and the entity dropdown is populated from the live
 * /api/v1/entities response.
 *
 * B17 gate — this is the Dashboards-side UI contract for the silent-fallback
 * removal. I4 compliance: operators never type IDs — they pick from a
 * dropdown populated from what exists.
 *
 * One test per file — Chrome `--single-process` cannot relaunch the browser
 * context between tests in the same spec. The Ask-view 422 test lives in
 * e2e/entity-unresolved.spec.ts.
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test('PR 2 — Dashboards view shows empty state and populates entity dropdown', async ({ page }) => {
  // Capture the entity list for assertions.
  const api = await pwRequest.newContext();
  const entitiesResp = await api.get('http://localhost:8005/api/v1/entities');
  const registered = ((await entitiesResp.json()).entities || []) as Array<{
    entity_id: string;
    display_name?: string;
  }>;
  expect(registered.length, 'no entities registered').toBeGreaterThan(0);
  await api.dispose();

  await page.route('**/*', (route, request) => {
    if (request.url().includes('localhost')) route.continue();
    else route.abort();
  });
  await page.goto('/', { waitUntil: 'load' });

  // Switch to Dashboards view.
  const dashTab = page.locator('#nav-tab-dashboard');
  await expect(dashTab).toBeVisible({ timeout: 15_000 });
  await dashTab.click();

  // Empty-state prompt must be visible before a selection is made.
  await expect(
    page.getByText('Pick an entity to generate a dashboard.', { exact: true }),
    'Dashboards view must show empty state before entity selection',
  ).toBeVisible({ timeout: 10_000 });

  // Entity selector dropdown must be present and populated.
  const dropdown = page.locator('#dashboard-entity-selector');
  await expect(dropdown, 'dashboard entity dropdown must render').toBeVisible({
    timeout: 10_000,
  });

  // Dropdown must contain an <option> for every registered entity plus the
  // placeholder. Use toHaveCount so Playwright polls until the fetch-on-mount
  // populates the state.
  const options = dropdown.locator('option');
  await expect(
    options,
    `dropdown must have ${registered.length} entities + 1 placeholder`,
  ).toHaveCount(registered.length + 1, { timeout: 10_000 });

  // Default selection is the placeholder (empty string).
  await expect(dropdown).toHaveValue('');

  await page.screenshot({
    path: 'test-results/pr2-dashboards-empty-state.png',
    fullPage: true,
  });
});
