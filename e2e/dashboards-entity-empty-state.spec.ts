/**
 * Dashboards view — entity dropdown populates from /api/v1/entities and
 * auto-selects the current run's entity on mount. SE mode = one entity
 * per run; no "Pick an entity" prompt, no silent fallback.
 *
 * B17 gate — this is the Dashboards-side UI contract for the current-run
 * auto-selection behavior.
 *
 * One test per file — Chrome `--single-process` cannot relaunch the browser
 * context between tests in the same spec. The Ask-view auto-resolution
 * test lives in e2e/entity-unresolved.spec.ts.
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test('Dashboards dropdown populates and auto-selects the current-run entity', async ({ page }) => {
  // Capture the entity list for assertions.
  const api = await pwRequest.newContext();
  const entitiesResp = await api.get('http://localhost:8005/api/v1/entities');
  const registered = ((await entitiesResp.json()).entities || []) as Array<{
    entity_id: string;
    display_name?: string;
  }>;
  expect(registered.length, 'no entities registered in current run').toBeGreaterThan(0);
  const currentEntity = registered[0].entity_id;
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

  // Entity selector dropdown must be present and populated.
  const dropdown = page.locator('#dashboard-entity-selector');
  await expect(dropdown, 'dashboard entity dropdown must render').toBeVisible({
    timeout: 10_000,
  });

  // Dropdown must contain exactly one <option> per registered entity —
  // no placeholder. Use toHaveCount so Playwright polls until the
  // fetch-on-mount populates the state.
  const options = dropdown.locator('option');
  await expect(
    options,
    `dropdown must have exactly ${registered.length} entity options`,
  ).toHaveCount(registered.length, { timeout: 10_000 });

  // Auto-selection: the dropdown must settle on the current run's entity,
  // not the placeholder. This is the behavior that makes Ask view work
  // without the user typing an entity name.
  await expect(
    dropdown,
    `dropdown must auto-select current-run entity ${currentEntity}`,
  ).toHaveValue(currentEntity, { timeout: 10_000 });

  // The "No entities available" empty state must NOT be visible.
  await expect(
    page.getByText('No entities available.', { exact: true }),
  ).toHaveCount(0);

  await page.screenshot({
    path: 'test-results/dashboards-entity-auto-select.png',
    fullPage: true,
  });
});
