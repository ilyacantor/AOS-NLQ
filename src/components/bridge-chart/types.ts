export interface BridgeChartBar {
  label: string
  value: number | null
  type: 'total' | 'increase' | 'decrease'
  running_total: number | null
}

export interface BridgeChartData {
  bridge_type: string
  title: string
  subtitle: string
  period_start: string
  period_end: string
  start_value: number | null
  end_value: number | null
  unit: string
  format: string
  bars: BridgeChartBar[]
  data_source: string | null
  downloadable: boolean
}
