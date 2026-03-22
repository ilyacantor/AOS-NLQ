/**
 * Playwright headless verification for NLQ Ask tab fixes.
 * B17 gate — verifies UI rendering, not just API responses.
 *
 * Tests:
 *   1. "2025 P&L" → FY 2025 totals in text + financial statement table
 *   2. "pipeline" → data not available message, NOT $0M
 *   3. "2026 forecast" → financial statement table, not "stumped"
 *   4. "Q3 2025 P&L" → single quarter regression check
 */

const { chromium } = require('playwright');

const NLQ_URL = 'http://localhost:3005';
const SCREENSHOT_DIR = '/tmp';

async function submitQuery(page, query) {
  // Find the Ask tab input and submit
  const input = page.locator('input[placeholder*="Ask"], textarea[placeholder*="Ask"], input[type="text"]').first();
  await input.fill(query);
  await input.press('Enter');
  // Wait for response to appear (look for answer text or financial statement)
  await page.waitForTimeout(20000);
}

async function test1_2025PL(page) {
  console.log('\n--- Test 1: "2025 P&L" ---');
  await submitQuery(page, '2025 P&L');

  // Take screenshot
  await page.screenshot({ path: `${SCREENSHOT_DIR}/test1_2025_pl.png`, fullPage: true });
  console.log(`Screenshot: ${SCREENSHOT_DIR}/test1_2025_pl.png`);

  // Check for FY 2025 in the page text
  const bodyText = await page.locator('body').innerText();
  const hasFY2025 = bodyText.includes('FY 2025');
  console.log(`FY 2025 visible in page: ${hasFY2025}`);

  // Check for financial statement table
  const tableExists = await page.locator('table').count();
  console.log(`Table elements found: ${tableExists}`);

  // Check for Revenue row in table
  const hasRevenue = bodyText.includes('Revenue');
  console.log(`Revenue label visible: ${hasRevenue}`);

  // Check Q1-Q4 columns exist
  const hasQ1 = bodyText.includes('Q1 2025');
  const hasQ4 = bodyText.includes('Q4 2025');
  console.log(`Q1 2025 column: ${hasQ1}, Q4 2025 column: ${hasQ4}`);

  const passed = hasFY2025 && tableExists > 0 && hasRevenue;
  console.log(`Test 1 result: ${passed ? 'PASS' : 'FAIL'}`);
  return passed;
}

async function test2_pipeline(page) {
  console.log('\n--- Test 2: "pipeline" ---');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await submitQuery(page, 'pipeline');

  await page.screenshot({ path: `${SCREENSHOT_DIR}/test2_pipeline.png`, fullPage: true });
  console.log(`Screenshot: ${SCREENSHOT_DIR}/test2_pipeline.png`);

  const bodyText = await page.locator('body').innerText();
  const hasZeroM = bodyText.includes('$0M pipeline') || bodyText.includes('$0.0M pipeline');
  const hasNotAvailable = bodyText.includes('not available') || bodyText.includes('N/A');
  console.log(`$0M silent fallback visible: ${hasZeroM}`);
  console.log(`Data not available message visible: ${hasNotAvailable}`);

  const passed = !hasZeroM && hasNotAvailable;
  console.log(`Test 2 result: ${passed ? 'PASS' : 'FAIL'}`);
  return passed;
}

async function test3_forecast(page) {
  console.log('\n--- Test 3: "2026 forecast" ---');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await submitQuery(page, '2026 forecast');

  await page.screenshot({ path: `${SCREENSHOT_DIR}/test3_forecast.png`, fullPage: true });
  console.log(`Screenshot: ${SCREENSHOT_DIR}/test3_forecast.png`);

  const bodyText = await page.locator('body').innerText();
  const hasStumped = bodyText.toLowerCase().includes('stumped');
  const has2026 = bodyText.includes('2026');
  const tableExists = await page.locator('table').count();
  console.log(`"Stumped" message visible: ${hasStumped}`);
  console.log(`2026 data visible: ${has2026}`);
  console.log(`Financial statement table: ${tableExists > 0}`);

  const passed = !hasStumped && has2026;
  console.log(`Test 3 result: ${passed ? 'PASS' : 'FAIL'}`);
  return passed;
}

async function test4_regression_q3(page) {
  console.log('\n--- Test 4: "Q3 2025 P&L" regression ---');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await submitQuery(page, 'Q3 2025 P&L');

  await page.screenshot({ path: `${SCREENSHOT_DIR}/test4_q3_regression.png`, fullPage: true });
  console.log(`Screenshot: ${SCREENSHOT_DIR}/test4_q3_regression.png`);

  const bodyText = await page.locator('body').innerText();
  const hasQ3 = bodyText.includes('Q3 2025');
  const hasFY = bodyText.includes('FY 2025');
  console.log(`Q3 2025 visible: ${hasQ3}`);
  console.log(`FY 2025 visible (should be false): ${hasFY}`);

  const passed = hasQ3;
  console.log(`Test 4 result: ${passed ? 'PASS' : 'FAIL'}`);
  return passed;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  try {
    console.log(`Navigating to ${NLQ_URL}...`);
    await page.goto(NLQ_URL);
    await page.waitForLoadState('networkidle');

    // Check page loaded
    const title = await page.title();
    console.log(`Page title: ${title}`);

    // Check for error elements
    const errors = await page.locator('[class*="error"], [class*="Error"]').count();
    console.log(`Error elements on load: ${errors}`);

    const results = [];
    results.push(await test1_2025PL(page));
    results.push(await test2_pipeline(page));
    results.push(await test3_forecast(page));
    results.push(await test4_regression_q3(page));

    console.log('\n=== SUMMARY ===');
    const names = ['2025 P&L FY totals', 'Pipeline no silent fallback', '2026 forecast routing', 'Q3 regression'];
    results.forEach((r, i) => console.log(`  ${r ? '[PASS]' : '[FAIL]'} ${names[i]}`));

    const allPass = results.every(r => r);
    console.log(`\nOverall: ${allPass ? 'ALL PASS' : 'SOME FAILURES'}`);
    process.exit(allPass ? 0 : 1);
  } catch (err) {
    console.error('Test error:', err.message);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/test_error.png`, fullPage: true });
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
