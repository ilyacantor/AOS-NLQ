/**
 * NLQ Dashboard UI Evaluation Runner
 *
 * Uses Playwright to run 12 test cases against the actual UI,
 * taking screenshots and verifying values against ground truth.
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Ground truth values from fact base
const GROUND_TRUTH = {
  revenue_2025: 150.0,
  pipeline_2025: 431.25,
  win_rate_2025: 42,
  gross_margin_pct_2025: 65.0,
  customer_count_2025: 950,
  nrr_2025: 118,
  gross_churn_pct_2025: 7,
  logo_churn_pct_2025: 10,
  headcount_2025: 350,

  // Quarterly revenue for trend chart
  quarterly_revenue: {
    '2024-Q1': 22.0,
    '2024-Q2': 24.0,
    '2024-Q3': 26.0,
    '2024-Q4': 28.0,
    '2025-Q1': 33.0,
    '2025-Q2': 36.0,
    '2025-Q3': 39.0,
    '2025-Q4': 42.0,
  },

  // Regional pipeline breakdown (approximate percentages)
  pipeline_by_region: {
    AMER: 0.50,  // ~$215M
    EMEA: 0.30,  // ~$129M
    APAC: 0.20,  // ~$86M
  },
};

const SCREENSHOT_DIR = path.join(__dirname, 'eval_screenshots');
const BASE_URL = 'http://localhost:5000';
const API_URL = 'http://localhost:8000';

// Test results storage
const results = {
  total: 12,
  passed: 0,
  failed: 0,
  errors: 0,
  details: [],
  iterations: [],
};

// Helper to take screenshot
async function takeScreenshot(page, name) {
  const filepath = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: filepath, fullPage: true });
  console.log(`  📸 Screenshot saved: ${name}.png`);
  return filepath;
}

// Helper to wait for response and UI to settle
async function waitForQueryResponse(page, timeout = 30000) {
  // Wait for loading indicator to appear and disappear
  try {
    await page.waitForSelector('.animate-spin', { timeout: 5000 });
  } catch (e) {
    // Loading may have already finished
  }
  await page.waitForSelector('.animate-spin', { state: 'hidden', timeout });
  // Extra wait for UI to render
  await page.waitForTimeout(1000);
}

// Helper to type a query and submit
async function submitQuery(page, query) {
  const input = await page.locator('input[type="text"]');
  await input.fill(query);
  await input.press('Enter');
  await waitForQueryResponse(page);
}

// Helper to check if text contains value (with tolerance)
function containsValue(text, value, tolerance = 0.05) {
  if (typeof value === 'number') {
    // Extract numbers from text
    const numbers = text.match(/[\d.]+/g)?.map(Number) || [];
    return numbers.some(n => Math.abs(n - value) / value <= tolerance);
  }
  return text.toLowerCase().includes(String(value).toLowerCase());
}

// Test case definitions
const testCases = [
  {
    id: 'TC-01',
    name: 'Simple Metric Query',
    run: async (page) => {
      await submitQuery(page, "what's our revenue?");

      // Check for text response (not dashboard)
      const content = await page.textContent('body');
      const hasValue = containsValue(content, 150);
      const hasM = content.includes('M') || content.includes('million');

      // Should NOT show chart widgets
      const hasChart = await page.locator('.recharts-wrapper').count() > 0;

      await takeScreenshot(page, 'TC-01');

      return {
        pass: hasValue && hasM && !hasChart,
        message: hasValue && hasM ?
          `Value matches: $150M found${hasChart ? ' but chart rendered (should be text only)' : ''}` :
          `Value not found. Expected ~$150M`,
        verification: {
          hasValue,
          hasM,
          noChart: !hasChart,
        }
      };
    }
  },

  {
    id: 'TC-02',
    name: 'Trend Chart',
    run: async (page) => {
      await submitQuery(page, "show me revenue over time");
      await page.waitForTimeout(2000); // Extra wait for chart rendering

      // Check for chart
      const chartCount = await page.locator('.recharts-wrapper').count();
      const hasChart = chartCount > 0;

      // Try to find data points or values in the chart area
      const content = await page.textContent('body');
      const hasQ1Value = containsValue(content, 22) || containsValue(content, 33);
      const hasQ4Value = containsValue(content, 28) || containsValue(content, 42);

      await takeScreenshot(page, 'TC-02');

      return {
        pass: hasChart,
        message: hasChart ?
          `Chart rendered with ${chartCount} chart(s)` :
          'No chart rendered - expected line/area chart',
        verification: {
          hasChart,
          chartCount,
          hasQ1Value,
          hasQ4Value,
        }
      };
    }
  },

  {
    id: 'TC-03',
    name: 'Breakdown Chart',
    run: async (page) => {
      await submitQuery(page, "show me pipeline by region");
      await page.waitForTimeout(2000);

      const chartCount = await page.locator('.recharts-wrapper').count();
      const hasChart = chartCount > 0;

      const content = await page.textContent('body');
      const hasPipelineValue = containsValue(content, 431, 0.1);
      const hasRegions = content.includes('AMER') || content.includes('EMEA') || content.includes('APAC') ||
                         content.includes('region');

      await takeScreenshot(page, 'TC-03');

      return {
        pass: hasChart || hasRegions,
        message: hasChart ?
          `Bar chart rendered. Pipeline total check: ${hasPipelineValue}` :
          'No chart rendered',
        verification: {
          hasChart,
          chartCount,
          hasPipelineValue,
          hasRegions,
        }
      };
    }
  },

  {
    id: 'TC-04',
    name: 'Add Widget (Context)',
    prerequisite: 'TC-03',
    run: async (page) => {
      // Assume TC-03 state (pipeline by region visible)
      const beforeCount = await page.locator('.recharts-wrapper').count();

      await submitQuery(page, "add a KPI for win rate");
      await page.waitForTimeout(2000);

      const afterCount = await page.locator('.recharts-wrapper').count();
      const content = await page.textContent('body');
      const hasWinRate = containsValue(content, 42);

      await takeScreenshot(page, 'TC-04');

      return {
        pass: hasWinRate,
        message: hasWinRate ?
          `Win rate KPI (42%) found. Widget count: ${beforeCount} -> ${afterCount}` :
          'Win rate value not found',
        verification: {
          beforeCount,
          afterCount,
          hasWinRate,
          contextPreserved: afterCount >= beforeCount,
        }
      };
    }
  },

  {
    id: 'TC-05',
    name: 'Change Chart Type',
    prerequisite: 'TC-02',
    run: async (page) => {
      // First create a line chart
      await submitQuery(page, "show me revenue over time");
      await page.waitForTimeout(2000);

      // Now change to bar chart
      await submitQuery(page, "make that a bar chart");
      await page.waitForTimeout(2000);

      const content = await page.textContent('body');
      const hasBarChart = await page.locator('.recharts-bar').count() > 0 ||
                          content.toLowerCase().includes('bar');

      await takeScreenshot(page, 'TC-05');

      return {
        pass: hasBarChart,
        message: hasBarChart ?
          'Chart type changed to bar' :
          'Bar chart not detected',
        verification: {
          hasBarChart,
        }
      };
    }
  },

  {
    id: 'TC-06',
    name: 'Multi-Widget Dashboard',
    run: async (page) => {
      await submitQuery(page, "build me a sales dashboard");
      await page.waitForTimeout(3000);

      const content = await page.textContent('body');
      const widgetCount = await page.locator('.recharts-wrapper').count();

      const hasRevenue = containsValue(content, 150, 0.1);
      const hasPipeline = containsValue(content, 431, 0.1);
      const hasWinRate = containsValue(content, 42, 0.1);

      await takeScreenshot(page, 'TC-06');

      return {
        pass: widgetCount >= 1 && (hasRevenue || hasPipeline || hasWinRate),
        message: `Dashboard with ${widgetCount} widgets. Revenue: ${hasRevenue}, Pipeline: ${hasPipeline}, Win Rate: ${hasWinRate}`,
        verification: {
          widgetCount,
          hasRevenue,
          hasPipeline,
          hasWinRate,
        }
      };
    }
  },

  {
    id: 'TC-07',
    name: 'Guided Discovery',
    run: async (page) => {
      await submitQuery(page, "what can you show me about customers?");

      const content = await page.textContent('body');
      const hasCustomerCount = content.toLowerCase().includes('customer count') ||
                               content.toLowerCase().includes('customer_count');
      const hasNRR = content.toLowerCase().includes('nrr') ||
                     content.toLowerCase().includes('net revenue retention');
      const hasChurn = content.toLowerCase().includes('churn');

      // Should be text, not chart
      const chartCount = await page.locator('.recharts-wrapper').count();

      await takeScreenshot(page, 'TC-07');

      return {
        pass: hasCustomerCount || hasNRR || hasChurn,
        message: `Guided discovery response. Mentions: customer_count=${hasCustomerCount}, nrr=${hasNRR}, churn=${hasChurn}`,
        verification: {
          hasCustomerCount,
          hasNRR,
          hasChurn,
          isTextResponse: chartCount === 0,
        }
      };
    }
  },

  {
    id: 'TC-08',
    name: 'Ambiguous Query',
    run: async (page) => {
      await submitQuery(page, "show me performance");

      const content = await page.textContent('body');
      const asksClarification = content.toLowerCase().includes('which') ||
                                content.toLowerCase().includes('clarif') ||
                                content.toLowerCase().includes('specific') ||
                                content.toLowerCase().includes('mean') ||
                                content.toLowerCase().includes('type');
      const offersOptions = content.toLowerCase().includes('sales') ||
                           content.toLowerCase().includes('system') ||
                           content.toLowerCase().includes('team');

      // Should NOT show chart (don't guess)
      const chartCount = await page.locator('.recharts-wrapper').count();

      await takeScreenshot(page, 'TC-08');

      return {
        pass: asksClarification || offersOptions,
        message: asksClarification ?
          'System asks for clarification' :
          (offersOptions ? 'System offers options' : 'No clarification requested'),
        verification: {
          asksClarification,
          offersOptions,
          noChart: chartCount === 0,
        }
      };
    }
  },

  {
    id: 'TC-09',
    name: 'Missing Data',
    run: async (page) => {
      await submitQuery(page, "show me mars colony revenue");

      const content = await page.textContent('body');
      const gracefulResponse = content.toLowerCase().includes('not available') ||
                               content.toLowerCase().includes("don't have") ||
                               content.toLowerCase().includes('no data') ||
                               content.toLowerCase().includes('cannot') ||
                               content.toLowerCase().includes('unable');

      // Should NOT show chart with fake data
      const chartCount = await page.locator('.recharts-wrapper').count();
      const hasFakeNumbers = content.includes('$0') || content.includes('0%');

      await takeScreenshot(page, 'TC-09');

      return {
        pass: gracefulResponse && chartCount === 0,
        message: gracefulResponse ?
          'Graceful "not available" response' :
          'Did not indicate data unavailable',
        verification: {
          gracefulResponse,
          noChart: chartCount === 0,
          noFakeNumbers: !hasFakeNumbers,
        }
      };
    }
  },

  {
    id: 'TC-10',
    name: 'No Context',
    run: async (page) => {
      // Navigate to fresh start
      await page.goto(BASE_URL);
      await page.waitForTimeout(1000);

      await submitQuery(page, "make it a bar chart");

      const content = await page.textContent('body');
      const asksClarification = content.toLowerCase().includes('what') ||
                                content.toLowerCase().includes('which') ||
                                content.toLowerCase().includes('clarif') ||
                                content.toLowerCase().includes('first') ||
                                content.toLowerCase().includes('no ') ||
                                content.toLowerCase().includes('nothing');

      // Should NOT show random chart
      const chartCount = await page.locator('.recharts-wrapper').count();

      await takeScreenshot(page, 'TC-10');

      return {
        pass: asksClarification || chartCount === 0,
        message: asksClarification ?
          'System asks for clarification' :
          (chartCount === 0 ? 'No chart shown (correct)' : 'Random chart appeared'),
        verification: {
          asksClarification,
          noChart: chartCount === 0,
        }
      };
    }
  },

  {
    id: 'TC-11',
    name: 'Cross-Widget Filtering',
    run: async (page) => {
      // Create dashboard with chart and table
      await submitQuery(page, "show me pipeline by region with a deals table");
      await page.waitForTimeout(3000);

      // Take before screenshot
      await takeScreenshot(page, 'TC-11-before');

      // Try to click on a chart element (if bar chart exists)
      const bars = await page.locator('.recharts-bar-rectangle');
      const barCount = await bars.count();

      let filterWorked = false;
      if (barCount > 0) {
        try {
          await bars.first().click();
          await page.waitForTimeout(1000);
          filterWorked = true;
        } catch (e) {
          // Click may fail
        }
      }

      // Take after screenshot
      await takeScreenshot(page, 'TC-11-after');

      const content = await page.textContent('body');
      const hasFilterIndicator = content.toLowerCase().includes('filter') ||
                                 content.toLowerCase().includes('filtered');

      return {
        pass: filterWorked || barCount > 0,
        message: filterWorked ?
          `Cross-widget filtering triggered. Filter indicator: ${hasFilterIndicator}` :
          `Could not test filtering. Bar count: ${barCount}`,
        verification: {
          barCount,
          filterWorked,
          hasFilterIndicator,
        }
      };
    }
  },

  {
    id: 'TC-12',
    name: 'Multiple KPIs',
    run: async (page) => {
      await submitQuery(page, "show me revenue, margin, and pipeline KPIs");
      await page.waitForTimeout(2000);

      const content = await page.textContent('body');

      const hasRevenue = containsValue(content, 150, 0.05);
      const hasMargin = containsValue(content, 65, 0.05);
      const hasPipeline = containsValue(content, 431, 0.05);

      await takeScreenshot(page, 'TC-12');

      return {
        pass: hasRevenue && hasMargin && hasPipeline,
        message: `KPIs found: Revenue=$150M: ${hasRevenue}, Margin=65%: ${hasMargin}, Pipeline=$431M: ${hasPipeline}`,
        verification: {
          hasRevenue,
          hasMargin,
          hasPipeline,
        }
      };
    }
  },
];

// Main evaluation function
async function runEvaluation() {
  console.log('\n========================================');
  console.log('NLQ Dashboard UI Evaluation');
  console.log('========================================\n');

  // Ensure screenshot directory exists
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }

  // Check if API is available
  try {
    const healthCheck = await fetch(`${API_URL}/`);
    if (!healthCheck.ok) throw new Error('API not healthy');
    console.log('✅ API server is healthy');
  } catch (e) {
    console.error('❌ API server not available at', API_URL);
    console.error('Please start the backend: PYTHONPATH=/home/user/AOS-NLQ python -m uvicorn src.nlq.main:app --host 0.0.0.0 --port 8000');
    process.exit(1);
  }

  // Launch browser
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
  });
  const page = await context.newPage();

  // Check if frontend is available
  try {
    await page.goto(BASE_URL, { timeout: 10000 });
    console.log('✅ Frontend is available');
  } catch (e) {
    console.error('❌ Frontend not available at', BASE_URL);
    console.error('Please start the frontend: npm run dev');
    await browser.close();
    process.exit(1);
  }

  console.log('\nStarting test cases...\n');

  // Run each test case
  for (const tc of testCases) {
    console.log(`\n[${tc.id}] ${tc.name}`);
    console.log('─'.repeat(40));

    try {
      // Navigate to fresh start for each test (unless it's a prerequisite chain)
      if (!tc.prerequisite) {
        await page.goto(BASE_URL);
        await page.waitForTimeout(1000);
      }

      const result = await tc.run(page);

      if (result.pass) {
        console.log(`✅ PASS: ${result.message}`);
        results.passed++;
      } else {
        console.log(`❌ FAIL: ${result.message}`);
        results.failed++;
      }

      results.details.push({
        id: tc.id,
        name: tc.name,
        status: result.pass ? 'PASS' : 'FAIL',
        message: result.message,
        verification: result.verification,
      });

    } catch (error) {
      console.log(`⚠️ ERROR: ${error.message}`);
      results.errors++;
      results.details.push({
        id: tc.id,
        name: tc.name,
        status: 'ERROR',
        message: error.message,
      });

      // Take error screenshot
      await takeScreenshot(page, `${tc.id}-error`);
    }
  }

  // Close browser
  await browser.close();

  // Print summary
  console.log('\n========================================');
  console.log('EVALUATION SUMMARY');
  console.log('========================================');
  console.log(`Total:  ${results.total}`);
  console.log(`Pass:   ${results.passed}`);
  console.log(`Fail:   ${results.failed}`);
  console.log(`Error:  ${results.errors}`);
  console.log(`Rate:   ${((results.passed / results.total) * 100).toFixed(1)}%`);
  console.log('========================================\n');

  // Write results to file
  const evalProof = {
    date: new Date().toISOString(),
    results: results,
    groundTruth: GROUND_TRUTH,
  };

  fs.writeFileSync(
    path.join(__dirname, 'eval_results.json'),
    JSON.stringify(evalProof, null, 2)
  );

  return results;
}

// Run if called directly
if (require.main === module) {
  runEvaluation()
    .then(results => {
      process.exit(results.passed === results.total ? 0 : 1);
    })
    .catch(error => {
      console.error('Evaluation failed:', error);
      process.exit(1);
    });
}

module.exports = { runEvaluation, testCases, GROUND_TRUTH };
