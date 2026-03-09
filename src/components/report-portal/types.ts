export interface ReportLine {
  id: string
  name: string
  amount: number | null
  level: number
  isTotal?: boolean
  isHeader?: boolean
  isSub?: boolean
  bold?: boolean
  isFinal?: boolean
  isPercent?: boolean
  drillable?: boolean
  highlight?: boolean
}

export interface ReportData {
  lines: ReportLine[]
  metadata: {
    entity: string
    quarter: string
    segment: string | null
    periodType: 'actual' | 'forecast'
  }
}

export interface DrillThroughItem {
  name: string
  revenue: number
  children: boolean
  customers?: number
  projects?: number
}

export interface ReconMismatch {
  metric: string
  period: string
  expected: number | null
  actual: number | null
  delta: number | null
  pct_delta: number | null
  status: 'mismatch' | 'missing' | 'error'
  error?: string
}

export interface ReconCheck {
  statement: string
  period: string
  total: number
  green: number
  red: number
  mismatches: ReconMismatch[]
}

export interface ReconReport {
  checks: ReconCheck[]
  totalChecks: number
  totalGreen: number
  totalRed: number
  timestamp: string
}

export type StatementTab = 'pl' | 'bs' | 'socf' | 'drill' | 'recon'

export type ReportVariant =
  | 'full_year_act_vs_py'
  | 'quarterly_act_vs_py'
  | 'full_year_cf_vs_py_act'
  | 'quarterly_cf_vs_py'

export interface FinancialStatementLineItem {
  label: string
  key: string
  indent: number
  format: 'currency' | 'percent'
  is_subtotal: boolean
  values: Record<string, number | null>
}

export interface FinancialStatementData {
  title: string
  entity: string
  periods: string[]
  line_items: FinancialStatementLineItem[]
  currency: string
  unit: string
}

// ── Entity Selection ────────────────────────────────────────────────────────

export type EntitySelection = 'meridian' | 'cascadia' | 'combined'

// ── Combining Statement ─────────────────────────────────────────────────────

export interface CombiningLineItem {
  line_item: string
  meridian: number
  cascadia: number
  adjustments: number
  combined: number
}

export interface CombiningStatementData {
  period: string
  line_items: CombiningLineItem[]
}

// ── Overlap Report ──────────────────────────────────────────────────────────

export interface OverlapCustomer {
  count: number
  pct_of_combined: number
  match_types: { exact: number; fuzzy: number; manual: number }
}

export interface OverlapVendor {
  count: number
  pct_of_combined: number
}

export interface OverlapPerson {
  function: string
  meridian: number
  cascadia: number
  overlap: number
}

export interface OverlapData {
  customers: OverlapCustomer
  vendors: OverlapVendor
  people: OverlapPerson[]
}
