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
  EntitySelection,
  CombiningStatementData,
  OverlapData,
  CrossSellData,
  RevenueByCustomerData,
  EBITDABridgeData,
  WhatIfResult,
  QofEData,
  DashboardData,
  MaestraStatus,
} from './types'

const NLQ_BASE = '/api/v1'

// ── Report Dimensions ────────────────────────────────────────────────────────

export interface PeriodDimension {
  label: string
  year: number
  quarter: number
  period_type: 'actual' | 'forecast'
  has_data: Record<string, boolean>
}

export interface ReportDimensions {
  periods: PeriodDimension[]
  segments: string[]
}

export async function fetchReportDimensions(): Promise<ReportDimensions> {
  const res = await fetch(`${NLQ_BASE}/report-dimensions`)
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(
      `Report dimensions fetch failed (HTTP ${res.status}): ${errText.slice(0, 500)}`
    )
  }
  return res.json()
}

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
  periodIndex: number,
  index: number,
  totalItems: number,
): ReportLine {
  const period = periods[periodIndex]
  const amount = period ? (item.values[period] ?? null) : null

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
    drillable: item.format !== 'percent' && (amount !== null || item.is_subtotal),
    highlight: item.key === 'bench_cost' || item.key === 'bench_cost_total',
  }
}

function transformToReportData(
  fsData: FinancialStatementData,
  segment: string | null,
  periodIndex = 0,
): ReportData {
  const lines = fsData.line_items.map((item, i) =>
    transformFSLineItem(item, fsData.periods, periodIndex, i, fsData.line_items.length)
  )

  const periodLabel = fsData.periods[periodIndex] || ''
  const hasForecast = periodLabel.toLowerCase().includes('forecast') ||
    periodLabel.toLowerCase().includes('cf') ||
    periodLabel.toLowerCase().includes('(act+cf)')

  return {
    lines,
    metadata: {
      entity: fsData.entity,
      quarter: periodLabel,
      segment,
      periodType: hasForecast ? 'forecast' : 'actual',
      unit: fsData.unit,
    },
  }
}

export async function fetchReport(
  statement: 'income_statement' | 'balance_sheet' | 'cash_flow',
  variant: ReportVariant,
  quarter?: string,
  segment?: string | null,
  entity?: EntitySelection,
): Promise<{ reportData: ReportData; pyReportData: ReportData | null; rawFSData: FinancialStatementData }> {
  const query = variantToQuery(statement, variant, quarter, segment)

  const body: Record<string, unknown> = { question: query, persona: 'CFO' }
  if (entity === 'combined') {
    body.consolidate = true
  } else if (entity) {
    body.entity_id = entity
  }

  const res = await fetch(`${NLQ_BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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
  const seg = segment ?? null

  // Backend returns both CY and PY in a single response.
  // periods[0] = CY (e.g. "FY 2025 Actual"), periods[1] = PY (e.g. "FY 2024 Actual")
  // Extract PY from the same response — no need for a second API call.
  const hasPY = fsData.periods.length >= 2 &&
    !fsData.periods[1].toLowerCase().includes('variance')
  const pyReportData = hasPY ? transformToReportData(fsData, seg, 1) : null

  return {
    reportData: transformToReportData(fsData, seg),
    pyReportData,
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

// ── Combining Statement ───────────────────────────────────────────────────

export async function fetchCombiningStatement(
  period: string,
  segment?: string | null,
): Promise<CombiningStatementData> {
  const params = new URLSearchParams({ period })
  if (segment) params.set('segment', segment)

  const res = await fetch(`/api/reports/combining-is?${params}`)

  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(
      `Combining statement query failed (HTTP ${res.status}) for period=${period}: ${errText.slice(0, 500)}`
    )
  }

  return res.json()
}

// ── Entity Overlap ────────────────────────────────────────────────────────

export async function fetchOverlapData(): Promise<OverlapData> {
  const res = await fetch('/api/reports/entity-overlap')

  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(
      `Entity overlap query failed (HTTP ${res.status}): ${errText.slice(0, 500)}`
    )
  }

  return res.json()
}

// ── Cross-Sell Pipeline ──────────────────────────────────────────────────────

export async function fetchCrossSell(): Promise<CrossSellData> {
  const res = await fetch('/api/reports/cross-sell')
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(`Cross-sell query failed (HTTP ${res.status}): ${errText.slice(0, 500)}`)
  }
  return res.json()
}

// ── Revenue by Customer ──────────────────────────────────────────────────────

export async function fetchRevenueByCustomer(entityId: string): Promise<RevenueByCustomerData> {
  const res = await fetch(`/api/reports/revenue-by-customer?entity_id=${encodeURIComponent(entityId)}`)
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(`Revenue by customer query failed (HTTP ${res.status}): ${errText.slice(0, 500)}`)
  }
  return res.json()
}

// ── EBITDA Bridge ────────────────────────────────────────────────────────────

export async function fetchEBITDABridge(): Promise<EBITDABridgeData> {
  const res = await fetch('/api/reports/ebitda-bridge')
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(`EBITDA bridge query failed (HTTP ${res.status}): ${errText.slice(0, 500)}`)
  }
  return res.json()
}

// ── What-If Engine ───────────────────────────────────────────────────────────

export async function fetchWhatIf(levers?: Record<string, number>, preset?: string): Promise<WhatIfResult> {
  const body: Record<string, unknown> = {}
  if (preset) body.preset = preset
  else if (levers) body.levers = levers

  const res = await fetch('/api/reports/what-if', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(`What-if query failed (HTTP ${res.status}): ${errText.slice(0, 500)}`)
  }
  return res.json()
}

// ── Quality of Earnings ──────────────────────────────────────────────────────

export async function fetchQofE(): Promise<QofEData> {
  const res = await fetch('/api/reports/qoe')
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(`QofE query failed (HTTP ${res.status}): ${errText.slice(0, 500)}`)
  }
  return res.json()
}

// ── Executive Dashboard ──────────────────────────────────────────────────────

export async function fetchDashboard(persona: string): Promise<DashboardData> {
  const res = await fetch(`/api/reports/dashboard/${persona}`)
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(`Dashboard query failed (HTTP ${res.status}): ${errText.slice(0, 500)}`)
  }
  return res.json()
}

// ── Maestra (live endpoints — sessions 2-5) ─────────────────────────────────

const MAESTRA_CUSTOMER_ID = '00000000-0000-0000-0000-000000000001'

export interface MaestraChatResponse {
  text: string
  session_id: string
  action_result?: unknown
  plan_created?: { plan_id: string; title: string; status: string }
}

export async function sendMaestraChat(
  message: string,
  sessionId?: string,
): Promise<MaestraChatResponse> {
  const res = await fetch('/maestra/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      customer_id: MAESTRA_CUSTOMER_ID,
      message,
      session_id: sessionId,
    }),
  })
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(`Maestra chat failed (HTTP ${res.status}): ${errText.slice(0, 500)}`)
  }
  return res.json()
}

export async function fetchMaestraStats(): Promise<MaestraStatus> {
  const res = await fetch(`/maestra/stats/${MAESTRA_CUSTOMER_ID}`)
  if (!res.ok) {
    const errText = await res.text().catch(() => 'Unknown error')
    throw new Error(`Maestra stats failed (HTTP ${res.status}): ${errText.slice(0, 500)}`)
  }
  return res.json()
}
