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
    unit?: string
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

export interface CustomerMatch {
  meridian_name: string
  cascadia_name: string
  canonical_name: string
  match_type: string
  confidence: number
  meridian_revenue_M: number
  cascadia_revenue_M: number
  combined_revenue_M: number
  combined_pct_of_total: number
  concentration_flag: boolean
  industry: string
  notes: string
  engagement_detail: { entity: string; service_types: string[]; [key: string]: unknown }[]
}

export interface VendorMatch {
  meridian_name: string
  cascadia_name: string
  canonical_name: string
  match_type: string
  category: string
  meridian_spend_M: number
  cascadia_spend_M: number
  combined_spend_M: number
  consolidation_opportunity: boolean
  consolidation_detail: unknown
}

export interface PeopleRoleDetail {
  title: string
  meridian_count: number
  cascadia_count: number
  combined_count: number
  consolidation_action: string
}

export interface PeopleFunction {
  function: string
  meridian_headcount: number
  cascadia_headcount: number
  combined_headcount: number
  role_overlap_examples: string[]
  definitional_note: string
  role_detail: PeopleRoleDetail[]
}

export interface OverlapData {
  customer_overlap: {
    total_overlapping: number
    overlap_pct_of_combined: number
    overlap_pct_of_meridian: number
    overlap_pct_of_cascadia: number
    matches: CustomerMatch[]
    concentration_threshold_crossings: unknown[]
  }
  vendor_overlap: {
    total_overlapping: number
    overlap_pct_of_combined: number
    overlap_pct_of_meridian: number
    overlap_pct_of_cascadia: number
    matches: VendorMatch[]
  }
  people_overlap: {
    functions: PeopleFunction[]
    total_meridian_corporate: number
    total_cascadia_corporate: number
    total_combined_corporate: number
  }
}

// ── Cross-Sell Pipeline ────────────────────────────────────────────────────

export interface CrossSellCandidate {
  customer_id: string
  customer_name: string
  entity_id: string
  recommended_service: string
  propensity_score: number
  estimated_acv: number
  industry_match: number
  size_match: number
  behavioral_score: number
  engagement_fit: number
  relationship_strength: number
  rationale: string
  comparable_customers: string[]
  buyer_persona: string
  customer_engagement_M: number
  years_as_client: number
  industry: string
  segment: string
}

export interface CrossSellSummary {
  m_to_c_candidates: number
  m_to_c_total_acv: number
  m_to_c_high_conf_count: number
  m_to_c_high_conf_acv: number
  c_to_m_candidates: number
  c_to_m_total_acv: number
  c_to_m_high_conf_count: number
  c_to_m_high_conf_acv: number
  total_candidates: number
  total_pipeline_acv: number
  total_high_conf_acv: number
}

export interface CrossSellData {
  m_to_c: CrossSellCandidate[]
  c_to_m: CrossSellCandidate[]
  summary: CrossSellSummary
}

// ── Revenue by Customer ───────────────────────────────────────────────────

export interface RevenueByCustomerRow {
  name: string
  total: number
  [quarter: string]: string | number  // e.g. "2024-Q1": 1.75
}

export interface RevenueByCustomerData {
  entity_id: string
  quarters: string[]
  customers: RevenueByCustomerRow[]
  total_revenue: number
  customer_count: number
  provenance: {
    run_id?: string | null
    mode?: string | null
    source?: string | null
    run_timestamp?: string | null
    entity_id?: string | null
  }
}

// ── EBITDA Bridge ──────────────────────────────────────────────────────────

export interface BridgeAdjustment {
  name: string
  category: string
  entity: string
  confidence: string
  amount: number
  amount_low: number
  amount_high: number
  lever: string | null
  support_reference: string
  rationale: string
}

export interface EBITDABridgeData {
  reported_ebitda: { meridian: number; cascadia: number; combined_reported: number }
  entity_adjustments: BridgeAdjustment[]
  entity_adjusted_ebitda: { meridian: number; cascadia: number; combined: number }
  combination_synergies: BridgeAdjustment[]
  pro_forma_ebitda: {
    year_1: { low: number; high: number; current: number }
    steady_state: { low: number; high: number; current: number }
  }
  ev_impact: {
    multiple: number
    year_1_ev: { low: number; high: number; current: number }
    steady_state_ev: { low: number; high: number; current: number }
  }
}

// ── What-If ────────────────────────────────────────────────────────────────

export interface LeverDefinition {
  name: string
  label: string
  min: number
  max: number
  default: number
  unit: string
  impact_per_point_M: number | null
}

export interface WhatIfResult {
  levers: Record<string, number>
  lever_definitions: LeverDefinition[]
  reported_ebitda: number
  entity_adjusted_ebitda: number
  adjustments: BridgeAdjustment[]
  synergies: BridgeAdjustment[]
  pro_forma_ebitda: { year_1: number; steady_state: number }
  ev_impact: { year_1: number; steady_state: number }
  presets: Record<string, Record<string, number>>
}

// ── Dashboards ─────────────────────────────────────────────────────────────

export type DashboardPersona = 'cfo' | 'cro' | 'coo' | 'cto' | 'chro'

export interface DashboardData {
  persona: string
  title: string
  kpis: Record<string, number>
  [key: string]: unknown
}

// ── Quality of Earnings ──────────────────────────────────────────────────

export interface QofEAdjustmentRow {
  name: string
  category: string
  entity: string
  confidence: string
  current_amount: number
  diligence_amount: number | null
  prior_amount: number | null
  amount_low: number
  amount_high: number
  lever: string | null
  support_reference: string
  rationale: string
  status: 'active' | 'resolved' | 'new' | 'changed'
  lifecycle_stage: string
  trend: 'improving' | 'stable' | 'worsening'
}

export interface QofESustainabilityScore {
  overall: number
  components: { name: string; score: number; weight: number; max_points: number }[]
  grade: string
}

export interface QofEData {
  period: string
  is_initial_diligence: boolean
  ebitda_bridge: QofEAdjustmentRow[]
  adjustment_lifecycle: {
    lifecycle_stages: Record<string, { count: number; items: string[] }>
    status_counts: Record<string, number>
    total_adjustments: number
  }
  revenue_quality: {
    customer_concentration: {
      hhi: number
      top_10_pct: number
      top_20_pct: number
      top_50_pct: number
      threshold_alerts: { customer: string; pct: number; threshold: string }[]
      total_customers: number
    }
    contract_quality: {
      msa_pct: number
      sow_pct: number
      t_and_m_pct: number
      avg_tenure_years: number
    }
    revenue_mix: {
      recurring_pct: number
      non_recurring_pct: number
      advisory_consulting_M: number
      managed_services_M: number
      per_fte_M: number
      per_transaction_M: number
    }
    cohort_retention: { years_as_client: number; total_revenue_M: number }[]
    cross_sell_penetration: {
      total_candidates: number
      total_pipeline_acv_M: number
      converted_count: number
      converted_acv_M: number
      conversion_rate_pct: number
    }
  }
  sustainability_score: QofESustainabilityScore
  working_capital: {
    dso_trend: { period: string; value: number }[]
    dpo_trend: { period: string; value: number }[]
    bench_cost_trend: { period: string; value: number }[]
    working_capital_pct_trend: { period: string; value: number }[]
    margin_trend: { period: string; gross_margin_pct: number; ebitda_margin_pct: number }[]
  }
  new_items: {
    type: string
    description: string
    amount: number
    category: string
    classification_suggestion: string
    recommended_action: string
  }[]
  summary: {
    reported_ebitda: number
    entity_adjusted_ebitda: number
    pro_forma_year_1: number
    pro_forma_steady_state: number
    total_adjustments: number
    active_adjustments: number
    resolved_adjustments: number
    new_adjustments: number
    changed_adjustments: number
    sustainability_score: number
    sustainability_grade: string
  }
}

// ── Maestra ────────────────────────────────────────────────────────────────

export interface MaestraEngagement {
  engagement_id: string
  phase: string
  deal_name: string
  workstreams: number
  risks: number
  session_ids: string[]
  entities: { id: string; name: string }[]
}

export interface MaestraRichContent {
  type: 'table' | 'hierarchy' | 'comparison' | 'navigation'
  title?: string
  // table
  headers?: string[]
  rows?: string[][]
  // hierarchy
  root?: { name: string; children?: MaestraHierarchyNode[] }
  // comparison
  dimension?: string
  systems?: { system: string; value: string; is_match?: boolean }[]
  // navigation
  tab?: string
  entity?: string
}

export interface MaestraHierarchyNode {
  name: string
  children?: MaestraHierarchyNode[]
}

export interface MaestraMessage {
  response: string
  rich_content?: MaestraRichContent[]
  actions_taken: string[]
  suggestions: string[]
  phase: string
  section?: string
  completeness?: number
  navigation?: { tab: string; sub_view?: string }
}

export interface MaestraStatus {
  phase: string
  deal_name: string
  overall_progress_pct: number
  workstream_summary: { name: string; status: string; progress_pct: number }[]
  open_risks: number
  synergy_realization_pct: number
  days_since_start: number
  next_milestones: { workstream: string; milestone: string; target_date: string }[]
  entity_completeness?: Record<string, number>
}
