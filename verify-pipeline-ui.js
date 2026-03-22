const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const results = [];
  let allPassed = true;

  function check(name, passed, detail) {
    results.push({ name, passed, detail });
    if (!passed) allPassed = false;
    console.log(`  ${passed ? '[PASS]' : '[FAIL]'} ${name}${detail ? ' — ' + detail : ''}`);
  }

  // TEST 1: Report Portal Pipeline tab with real data
  console.log('\n=== TEST 1: Report Portal — Pipeline tab ===');
  const reportPage = await context.newPage();
  try {
    await reportPage.goto('http://localhost:3005', { waitUntil: 'networkidle', timeout: 15000 });
    const reportsBtn = reportPage.locator('button:visible:has-text("Reports")').first();
    await reportsBtn.click();
    await reportPage.waitForTimeout(2000);

    const pipelineTab = reportPage.locator('button:visible:has-text("Pipeline")').first();
    const pipelineVisible = await pipelineTab.isVisible({ timeout: 5000 }).catch(() => false);
    check('Pipeline tab visible', pipelineVisible);

    if (pipelineVisible) {
      await pipelineTab.click();
      await reportPage.waitForTimeout(5000);
      await reportPage.screenshot({ path: '/tmp/pipeline-report-tab.png', fullPage: true });

      const bodyText = await reportPage.locator('body').innerText();
      const hasStages = bodyText.includes('Lead') && bodyText.includes('Qualified') && bodyText.includes('Proposal');
      check('Pipeline tab shows stage data (Lead, Qualified, Proposal)', hasStages,
        hasStages ? 'All stages rendered' : 'Missing stages');

      const hasDollarAmounts = /\$\d/.test(bodyText);
      check('Pipeline tab shows dollar amounts', hasDollarAmounts);

      const hasEntityPanels = bodyText.includes('Meridian') || bodyText.includes('Cascadia') || bodyText.includes('Combined');
      check('Pipeline tab shows entity panels', hasEntityPanels);
    }
  } catch (err) {
    check('Report Portal Pipeline tab', false, err.message.slice(0, 200));
  }
  await reportPage.close();

  // TEST 2: Ask tab pipeline query
  console.log('\n=== TEST 2: Ask tab — pipeline query ===');
  const askPage = await context.newPage();
  try {
    await askPage.goto('http://localhost:3005', { waitUntil: 'networkidle', timeout: 15000 });
    const askInput = askPage.locator('input[type="text"], textarea').first();
    await askInput.fill('pipeline');
    await askInput.press('Enter');
    await askPage.waitForTimeout(8000);
    await askPage.screenshot({ path: '/tmp/pipeline-ask-query.png', fullPage: true });

    const bodyText = await askPage.locator('body').innerText();
    const funnelDiv = await askPage.locator('#sales-funnel-visual').count();
    const hasStages = bodyText.includes('Lead') || bodyText.includes('Qualified');
    check('Ask tab renders pipeline response', funnelDiv > 0 || hasStages,
      funnelDiv > 0 ? 'SalesFunnel component rendered with stages' : hasStages ? 'Stage names in response' : 'No pipeline data');
  } catch (err) {
    check('Ask tab pipeline query', false, err.message.slice(0, 200));
  }
  await askPage.close();

  // TEST 3: CFO Dashboard pipeline widget
  console.log('\n=== TEST 3: CFO Dashboard — pipeline widget ===');
  const dashPage = await context.newPage();
  try {
    await dashPage.goto('http://localhost:3005', { waitUntil: 'networkidle', timeout: 15000 });
    const askInput = dashPage.locator('input[type="text"], textarea').first();
    await askInput.fill('CFO dashboard');
    await askInput.press('Enter');
    await dashPage.waitForTimeout(10000);
    await dashPage.screenshot({ path: '/tmp/pipeline-cfo-dashboard.png', fullPage: true });

    const bodyText = await dashPage.locator('body').innerText();
    const hasPipeline = bodyText.includes('Sales Pipeline');
    check('CFO dashboard has Sales Pipeline widget', hasPipeline);

    const hasStageData = bodyText.includes('Lead') || bodyText.includes('Qualified');
    const hasNotAvailable = bodyText.includes('Pipeline data not available');
    check('Sales Pipeline widget shows stage data (not "not available")',
      hasStageData && !hasNotAvailable,
      hasStageData ? 'Stage data rendered' : 'Still showing "not available"');
  } catch (err) {
    check('CFO Dashboard pipeline', false, err.message.slice(0, 200));
  }
  await dashPage.close();

  // Summary
  console.log('\n=== SUMMARY ===');
  const passed = results.filter(r => r.passed).length;
  const failed = results.filter(r => !r.passed).length;
  console.log(`${passed} passed, ${failed} failed out of ${results.length} checks`);
  if (!allPassed) {
    console.log('\nFailed:');
    results.filter(r => !r.passed).forEach(r => console.log(`  - ${r.name}: ${r.detail || ''}`));
  }
  console.log('\nScreenshots: /tmp/pipeline-{report-tab,ask-query,cfo-dashboard}.png');

  await browser.close();
  process.exit(allPassed ? 0 : 1);
})();
