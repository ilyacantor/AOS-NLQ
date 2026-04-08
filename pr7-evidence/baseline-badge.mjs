// PR 7 B17 baseline capture — Trust Badge screenshot.
// Run via: node pr7-evidence/baseline-badge.mjs <before|after>
//
// Opens the NLQ Ask view, types a revenue query with VeloLabs-NDFK entity,
// waits for the answer to render, captures full-page screenshot plus a
// zoomed screenshot of the badge area.

import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const PHASE = process.argv[2] || 'before';
if (!['before', 'after'].includes(PHASE)) {
  console.error('Usage: node baseline-badge.mjs <before|after>');
  process.exit(2);
}

const BROWSER_PATH = '/home/ilyac/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome';
const OUT_DIR = '/home/ilyac/code/nlq/pr7-evidence';

const LAUNCH_ARGS = [
  '--no-sandbox',
  '--disable-setuid-sandbox',
  '--disable-gpu',
  '--disable-dev-shm-usage',
  '--disable-software-rasterizer',
  '--single-process',
];

const QUESTION = 'What is VeloLabs revenue for 2026 Q2?';

async function main() {
  const browser = await chromium.launch({
    executablePath: BROWSER_PATH,
    headless: true,
    args: LAUNCH_ARGS,
  });

  try {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();

    page.on('pageerror', (err) => console.log(`[pageerror] ${err}`));
    page.on('console', (msg) => {
      if (msg.type() === 'error') console.log(`[console.error] ${msg.text()}`);
    });

    await page.goto('http://localhost:3005/', { waitUntil: 'domcontentloaded', timeout: 60_000 });

    // Wait for React to mount AND for the backend readiness poll to flip
    // from "Offline" / "Loading snapshots" to "Live". Submitting while the
    // UI is still Offline makes the query hang with "Waiting for DCL live
    // data pipeline".
    try {
      await page.waitForFunction(
        () => !document.body.innerText.includes('Loading snapshots'),
        { timeout: 20_000 },
      );
      await page.waitForFunction(
        () => !document.body.innerText.includes('Offline'),
        { timeout: 20_000 },
      );
      console.log('  UI reports Live');
    } catch (err) {
      console.log(`  readiness wait: ${err.message}`);
    }
    await page.waitForTimeout(500);

    // Type the question. Try a few likely selectors.
    const selectors = [
      'textarea[placeholder*="Ask"]',
      'textarea[placeholder*="question"]',
      'textarea',
      'input[placeholder*="Ask"]',
      'input[type="text"]',
    ];
    let inputEl = null;
    for (const sel of selectors) {
      inputEl = await page.$(sel);
      if (inputEl) {
        console.log(`  typing into selector: ${sel}`);
        break;
      }
    }
    if (!inputEl) {
      throw new Error('Could not find input/textarea for the question');
    }
    await inputEl.fill(QUESTION);

    // Submit: press Enter. If that does nothing, try clicking a submit button.
    await inputEl.press('Enter');

    // Wait for the /api/v1/query response to come back
    try {
      await page.waitForResponse(
        (res) => res.url().includes('/api/v1/query') && res.request().method() === 'POST',
        { timeout: 45_000 },
      );
      console.log('  /api/v1/query POST completed');
    } catch (err) {
      console.log(`  wait-for-response timed out: ${err.message}`);
    }

    // Give the UI a moment to render after response
    await page.waitForTimeout(3_000);

    // Full-page screenshot
    const fullPath = `${OUT_DIR}/${PHASE}_fullpage.png`;
    await page.screenshot({ path: fullPath, fullPage: true });
    console.log(`  full page screenshot -> ${fullPath}`);

    // Try to find and zoom in on the badge.
    const badgeSelectors = [
      'text=Verified',
      'text=Simulation',
      'text=No Data',
      '[title*="Sourced"]',
      '[title*="Data Verified"]',
      '[title*="No live data"]',
    ];
    let badgeInfo = { found: false, text: null, label: null, selector: null };
    for (const sel of badgeSelectors) {
      const el = await page.$(sel);
      if (el) {
        const text = await el.textContent().catch(() => null);
        const title = await el.getAttribute('title').catch(() => null);
        badgeInfo = { found: true, text, title, selector: sel };
        console.log(`  badge found via ${sel}: text="${text}" title="${title}"`);
        break;
      }
    }

    // DOM dump of the detail panel area (if present) for provenance debugging
    const panelHTML = await page.evaluate(() => {
      const candidates = [
        document.querySelector('[class*="NodeDetailPanel"]'),
        document.querySelector('[class*="galaxy"]'),
        document.querySelector('main'),
        document.body,
      ].filter(Boolean);
      return candidates[0] ? candidates[0].outerHTML.slice(0, 50_000) : '(no panel)';
    });
    writeFileSync(`${OUT_DIR}/${PHASE}_panel.html`, panelHTML);
    console.log(`  panel HTML dump -> ${OUT_DIR}/${PHASE}_panel.html`);

    // Summary JSON
    writeFileSync(
      `${OUT_DIR}/${PHASE}_summary.json`,
      JSON.stringify({ phase: PHASE, question: QUESTION, badgeInfo }, null, 2),
    );
    console.log(`  summary -> ${OUT_DIR}/${PHASE}_summary.json`);

    console.log(`\n[${PHASE}] badge state: ${badgeInfo.found ? badgeInfo.text : 'NOT FOUND'}`);
  } finally {
    try { await browser.close(); } catch (_) {}
  }
}

main().catch((err) => {
  console.error('FAIL:', err);
  process.exit(1);
});
