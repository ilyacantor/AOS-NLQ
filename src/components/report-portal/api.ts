/**
 * API adapter functions for the Report Portal.
 *
 * Fetches data from NLQ and DCL endpoints and transforms responses
 * into the shapes expected by the portal components.
 */

import type {
  ReportData,
  ReportLine,
  DrillThroughItem,
  ReconReport,
  ReportVariant,
  FinancialStatementData,
  FinancialStatementLineItem,
} from './types'

const NLQ_BASE = '/api/v1'

// ── Report (P&L, BS, SOCF) ──────────────────────────────────────────────────

function variantToQuery(
  statement: 'income_statement' | 'balance_sheet' | 'cash_flow',
  variant: ReportVariant,
  quarter?: string,
  segment?: string | null,
): string {
  const stmtName =
    statement === 'income_statement' ? 'P&L' :
    statement === 'balance_sheet' ? 'Balance Sheet' :
    'Statement of Cash Flows'

  let query = ''
  switch (variant) {
    case 'full_year_act_vs_py':
      query = `Show me the ${stmtName} actual vs prior year`
      break
    case 'quarterly_act_vs_py':
      query = `Show me the ${stmtName} for ${quarter || 'Q3 2025'} vs prior year`
      break
    case 'full_year_cf_vs_py_act':
      query = `Show me the ${stmtName} current forecast vs prior year`
      break
    case 'quarterly_cf_vs_py':
      query = `Show me the ${stmtName} forecast for ${quarter || 'Q2 2026'} vs prior year`
      break
  }
  if (segment) {
    query += ` for ${segment}`
  }
  return query
}

function transformFSLineItem(
  item: FinancialStatementLineItem,
  periods: string[],
  index: number,
  totalItems: number,
): ReportLine {
  // Use the first period's value as the primary amount
  const primaryPeriod = periods[0]
  const amount = item.values[primaryPeriod] ?? null

  return {
    id: item.key || `line-${index}`,
    name: item.label,
    amount,
    level: item.indent,
    isTotal: item.is_subtotal && item.label.toLowerCase().includes('total'),
    isHeader: amount === null && !item.is_subtotal && item.indent === 0,
    isSub: item.is_subtotal && !item.label.toLowerCase().includes('total'),
    bold: item.is_subtotal,
    isFinal: index === totalItems - 1 && item.is_subtotal,
    isPercent: item.format === 'percent',
    drillable: item.key === 'revenue' || item.key === 'total_revenue',
    highlight: item.key === 'bench_cost' || item.key === 'bench_cost_total',
  }
}

function transformToReportData(
  fsData: FinancialStatementData,
  segment: string | null,
): ReportData {
  const lines = fsData.line_items.map((item, i) =>
    transformFSLineItem(item, fsData.periods, i, fsData.line_items.length)
  )

  // Determine period type from the title/periods
  const hasForecast = fsData.periods.some(p =>
    p.toLowerCase().includes('forecast') || p.toLowerCase().includes('cf')
  )

  return {
    lines,
    metadata: {
      entity: fsData.entity,
      quarter: fsData.periods[0] || '',
      segment,
      periodType: hasForecast ? 'forecast' : 'actual',
    },
  }
}

export async function fetchReport(
  statement: 'income_statement' | 'balance_sheet' | 'cash_flow',
  variant: ReportVariant,
  quarter?: string,
  segment?: string | null,
): Promise<{ reportData: ReportData; rawFSData: FinancialStatementData }> {
  const query = variantToQuery(statement, variant, quarter, segment)

  const res = await fetch(`${NLQ_BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: query, persona: 'CFO' }),
  })

  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(
      `Report query failed (HTTP ${res.status}): ${errText.slice(0, 500)}`
    )
  }

  const data = await res.json()

  if (!data.financial_statement_data) {
    throw new Error(
      `NLQ did not return financial statement data for query: "${query}". ` +
      `Response type: ${data.response_type || 'unknown'}, answer: ${(data.answer || '').slice(0, 200)}`
    )
  }

  const fsData: FinancialStatementData = data.financial_statement_data
  return {
    reportData: transformToReportData(fsData, segment ?? null),
    rawFSData: fsData,
  }
}

// ── Drill-Through ────────────────────────────────────────────────────────────

export async function fetchDrillThrough(
  level: 'region' | 'rep' | 'customer' | 'project',
  parent?: string,
  quarter?: string,
): Promise<DrillThroughItem[]> {
  const params = new URLSearchParams({ level })
  if (parent) params.set('parent', parent)
  if (quarter) params.set('quarter', quarter)

  const res = await fetch(`${NLQ_BASE}/drill-through?${params}`)

  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(
      `Drill-through query failed (HTTP ${res.status}) for level=${level}, parent=${parent || 'none'}: ${errText.slice(0, 500)}`
    )
  }

  return res.json()
}

// ── Reconciliation ───────────────────────────────────────────────────────────

export async function fetchReconciliation(): Promise<ReconReport> {
  const res = await fetch(`${NLQ_BASE}/reconciliation`)

  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(
      `Reconciliation query failed (HTTP ${res.status}): ${errText.slice(0, 500)}`
    )
  }

  return res.json()
}
