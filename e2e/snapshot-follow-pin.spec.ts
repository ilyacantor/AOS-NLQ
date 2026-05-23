// Operator-visible outcome: On NLQ the Snapshot selector (#snapshot-selector) defaults to the latest snapshot — its first option is prefixed "★" and the adjacent [data-role=snapshot-follow-state] badge reads "following latest". Selecting a different (non-★) snapshot flips the badge to "pinned" and sets the <select> value to that snapshot's dcl_ingest_id. Re-selecting the ★ option restores "following latest". Pinning the Ask surface leaves the Dashboard surface independently on "following latest", and the Ask pin survives a round-trip through Dashboard.

import { test, expect } from 'playwright/test'

test('Snapshot selector: follow-latest default → pin on manual select → re-follow on ★', async ({ page }) => {
  await page.goto('/', { waitUntil: 'load' })

  const select = page.locator('#snapshot-selector')
  await expect(select).toBeVisible({ timeout: 20_000 })
  const badge = page.locator('[data-role="snapshot-follow-state"]').first()

  // Need >= 2 snapshots to exercise pin vs follow.
  const optionCount = await select.locator('option').count()
  expect(optionCount, 'need at least 2 snapshots to test pin/follow').toBeGreaterThan(1)

  // 1. Default = follow-latest; option 0 is the latest, marked with ★.
  await expect(badge).toHaveText('following latest', { timeout: 10_000 })
  const starOption = select.locator('option').first()
  expect((await starOption.textContent()) || '', 'latest option is ★-marked').toMatch(/^★/)
  const latestValue = (await starOption.getAttribute('value')) || ''
  expect(latestValue, 'latest option has a dcl_ingest_id value').not.toBe('')
  await expect(select).toHaveValue(latestValue)

  // 2. Select a different (non-★) snapshot → pins this surface.
  const pinnedValue = (await select.locator('option').nth(1).getAttribute('value')) || ''
  expect(pinnedValue, 'second option has a dcl_ingest_id value').not.toBe('')
  await select.selectOption(pinnedValue)
  await expect(badge).toHaveText('pinned', { timeout: 10_000 })
  await expect(select).toHaveValue(pinnedValue)

  // 3. Re-select the ★ (latest) snapshot → re-engages follow-latest.
  await select.selectOption(latestValue)
  await expect(badge).toHaveText('following latest', { timeout: 10_000 })
  await expect(select).toHaveValue(latestValue)
})

test('Snapshot selector: Ask and Dashboard pin independently', async ({ page }) => {
  await page.goto('/', { waitUntil: 'load' })

  const askSelect = page.locator('#snapshot-selector')
  await expect(askSelect).toBeVisible({ timeout: 20_000 })
  const askBadge = page.locator('[data-role="snapshot-follow-state"]').first()

  // Pin the Ask surface to a non-latest snapshot.
  const pinnedValue = (await askSelect.locator('option').nth(1).getAttribute('value')) || ''
  expect(pinnedValue, 'second snapshot option has a value').not.toBe('')
  await askSelect.selectOption(pinnedValue)
  await expect(askBadge).toHaveText('pinned', { timeout: 10_000 })

  // Switch to Dashboard — a separate surface; it must still be following latest.
  await page.locator('#nav-tab-dashboard').click()
  const dashSelect = page.locator('#snapshot-selector')
  await expect(dashSelect).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('[data-role="snapshot-follow-state"]').first()).toHaveText(
    'following latest',
    { timeout: 10_000 },
  )

  // Back to Ask — its pin survived the round-trip (per-surface state).
  await page.locator('#nav-tab-galaxy').click()
  const askSelect2 = page.locator('#snapshot-selector')
  await expect(askSelect2).toBeVisible({ timeout: 20_000 })
  await expect(askSelect2).toHaveValue(pinnedValue)
  await expect(page.locator('[data-role="snapshot-follow-state"]').first()).toHaveText('pinned', {
    timeout: 10_000,
  })
})
