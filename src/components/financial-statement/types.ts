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
