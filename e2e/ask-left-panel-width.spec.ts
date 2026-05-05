// Operator-visible outcome: After asking "whats the margin" (a VAGUE_METRIC route that returns 5 candidate Data Points rows + an answer paragraph), the Ask page's left panel renders so that (1) panel.width − tableEl.borderBoxWidth equals 25px ±4px (24px wrapper p-3 padding + 1px panel border-r), proving the panel sizes to the table and not to the answer text; (2) all four column headers — Metric, Value, Period, Conf — are visible inside the panel (each header's right edge ≤ panel right edge + 1px); (3) the Answer paragraph wraps to within the panel: paragraph.clientWidth ≤ panel.clientWidth and paragraph.scrollWidth ≤ paragraph.clientWidth + 1 (no horizontal text overflow). The pre-fix regression (commit 581f35e) makes panel.width = 640 (max-w cap) regardless of table — a diff far above 29 — and this test fails on that state.
/**
 * Regression locked: commit 581f35e moved the left panel from a fixed
 * w-[293px] to w-fit min-w-[293px] max-w-[640px] so it could grow to fit
 * the Data Points table. Side effect: the answer paragraph's max-content
 * (full unwrapped text) propagated through its section wrapper and pushed
 * the panel out toward 640px regardless of the actual table width. A
 * subsequent attempt using `w-0 min-w-full` collapsed the answer to a
 * single-word-per-line channel because min-width: 100% resolved against
 * the parent's intrinsic width, which itself collapsed when the answer
 * stopped contributing. This test pins the correct end-state: panel
 * width = table width; answer wraps to that width; table fully visible.
 *
 * Requirements:
 *   - NLQ frontend (3005), NLQ backend (8005), DCL (8004) running
 *   - At least one entity in /api/v1/entities with P&L triples
 */

import { test, expect, request as pwRequest } from 'playwright/test';

test.describe('Ask view — left panel width = Data Points table width', () => {
  test('long answer + 13-row table: panel sized to table, answer wraps, headers visible', async ({ page }) => {
    const apiContext = await pwRequest.newContext();
    const entitiesResp = await apiContext.get('http://localhost:8005/api/v1/entities');
    expect(entitiesResp.status()).toBe(200);
    const entitiesBody = await entitiesResp.json();
    const entities: Array<{ entity_id: string }> = entitiesBody.entities || [];
    expect(entities.length).toBeGreaterThanOrEqual(1);
    await apiContext.dispose();

    await page.goto('/', { waitUntil: 'load' });
    await page.waitForResponse(
      (res) => res.url().includes('/api/v1/entities') && res.request().method() === 'GET',
      { timeout: 15_000 },
    );

    const searchInput = page.locator('#nlq-search-input');
    await searchInput.fill('whats the margin');
    await expect(searchInput).toHaveValue('whats the margin');

    const [queryResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/v1/query') && res.request().method() === 'POST',
        { timeout: 60_000 },
      ),
      searchInput.press('Enter'),
    ]);
    expect(queryResponse.status()).toBe(200);
    const body = await queryResponse.json();
    const relatedMetrics: Array<{ metric: string }> = body.related_metrics || [];
    // Sanity: backend gave us the multi-row shape (5 candidate metrics for the ambiguous "margin" question).
    expect(relatedMetrics.length).toBeGreaterThanOrEqual(5);
    const expectedRows = relatedMetrics.length;

    // Wait for the Data Points table to render with the exact row count from the API
    // and the four canonical column headers from DataTable.tsx.
    const tableHeading = page.locator('h4', { hasText: 'Data Points' });
    await expect(tableHeading).toHaveText('Data Points', { timeout: 15_000 });
    const dataTable = page.locator('.data-table').first();
    const tableRows = dataTable.locator('tbody tr').filter({ hasNotText: /^(finance|other)$/i });
    await expect(tableRows).toHaveCount(expectedRows);
    await expect(dataTable.locator('thead th')).toHaveText(['Metric', 'Value', 'Period', 'Conf']);

    // ResizeObserver writes panel width async — give layout one frame to settle.
    await page.waitForTimeout(150);

    // The left panel is the parent block that contains both the Answer and the Data Points table.
    const panel = page.locator(':is(div):has(.data-table):has(h3:has-text("Answer"))').first();
    await expect(panel.locator('h3', { hasText: 'Answer' }).first()).toHaveText('Answer');

    const measurements = await page.evaluate(() => {
      const tableEl = document.querySelector('.data-table') as HTMLElement | null;
      if (!tableEl) return null;
      // Walk up to the panel (the flex-col block that also contains the Answer h3).
      let panelEl: HTMLElement | null = tableEl.parentElement;
      while (panelEl && !panelEl.querySelector('h3')) panelEl = panelEl.parentElement;
      if (!panelEl) return null;
      const answerP = panelEl.querySelector('h3 + * , p') as HTMLElement | null
        || (panelEl.querySelector('p.text-slate-200') as HTMLElement | null);
      const headers = Array.from(panelEl.querySelectorAll('th')) as HTMLElement[];
      const panelRect = panelEl.getBoundingClientRect();
      const tableRect = tableEl.getBoundingClientRect();
      return {
        panelWidth: panelRect.width,
        panelRight: panelRect.right,
        tableWidth: tableRect.width,
        headers: headers.map((h) => ({ text: (h.textContent || '').trim(), right: h.getBoundingClientRect().right })),
        answer: answerP
          ? {
              clientWidth: answerP.clientWidth,
              scrollWidth: answerP.scrollWidth,
              text: (answerP.textContent || '').slice(0, 60),
            }
          : null,
      };
    });

    // Measurement guard: presence-only checks would be weak; assert a positive shape instead.
    expect(measurements?.headers?.length).toBe(4);
    expect(measurements?.panelWidth ?? 0).toBeGreaterThan(0);
    expect(measurements?.tableWidth ?? 0).toBeGreaterThan(0);
    const m = measurements!;

    // Constants of the panel chrome around the table:
    //   - flex-1 wrapper has p-3 → 12px left + 12px right = 24
    //   - panel itself has border-r → 1px
    //   = 25px total. Add ±4px tolerance for sub-pixel rounding.
    const PANEL_CHROME_PX = 25;
    // (1) Panel width = table natural width + chrome (panel sized to the table, not to text).
    expect(m.panelWidth - m.tableWidth).toBeGreaterThanOrEqual(PANEL_CHROME_PX - 4);
    expect(m.panelWidth - m.tableWidth).toBeLessThanOrEqual(PANEL_CHROME_PX + 4);

    // (2) All four headers (Metric, Value, Period, Conf) are visible — none clipped past the panel's right edge.
    const headerTexts = m.headers.map((h) => h.text);
    expect(headerTexts).toEqual(expect.arrayContaining(['Metric', 'Value', 'Period', 'Conf']));
    for (const h of m.headers) {
      // ≤ panel right + 1px slack for sub-pixel rounding.
      expect(h.right).toBeLessThanOrEqual(m.panelRight + 1);
    }

    // (3) Answer paragraph wraps to (≤) the panel inner width and does not horizontally overflow.
    expect(m.answer?.clientWidth ?? 0).toBeGreaterThan(0);
    expect(m.answer!.clientWidth).toBeLessThanOrEqual(m.panelWidth);
    expect(m.answer!.scrollWidth).toBeLessThanOrEqual(m.answer!.clientWidth + 1);

    await page.screenshot({ path: 'test-results/ask-left-panel-width-real.png', fullPage: false });
  });
});
