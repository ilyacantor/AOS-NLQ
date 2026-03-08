import { useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import type { BridgeChartData } from './types'

interface Props {
  data: BridgeChartData
  sessionId: string
}

const COLORS = {
  total: '#6B7280',
  increase: '#10B981',
  decrease: '#EF4444',
}

function formatLabel(value: number | null, type: string): string {
  if (value === null || value === undefined) return 'N/A'
  if (type === 'total') return `$${value.toFixed(1)}M`
  const sign = value >= 0 ? '+' : ''
  return `${sign}$${value.toFixed(1)}M`
}

interface ChartBar {
  label: string
  base: number
  value: number
  rawValue: number | null
  type: string
}

export function BridgeChart({ data, sessionId }: Props) {
  const [downloading, setDownloading] = useState(false)

  const handleDownload = async () => {
    setDownloading(true)
    try {
      const res = await fetch(`/api/v1/export/bridge?session_id=${encodeURIComponent(sessionId)}&format=xlsx`)
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Download failed' }))
        console.error('Export failed:', err)
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'revenue_bridge.xlsx'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Download error:', err)
    } finally {
      setDownloading(false)
    }
  }

  // Transform bars into stacked chart data
  const chartData: ChartBar[] = data.bars.map((bar) => {
    if (bar.type === 'total') {
      return {
        label: bar.label,
        base: 0,
        value: bar.value ?? 0,
        rawValue: bar.value,
        type: bar.type,
      }
    }
    const val = bar.value ?? 0
    const running = bar.running_total ?? 0
    const base = val >= 0 ? running - val : running
    return {
      label: bar.label,
      base: Math.max(0, base),
      value: Math.abs(val),
      rawValue: bar.value,
      type: bar.type,
    }
  })

  // Calculate domain max for X axis
  const maxVal = Math.max(
    ...data.bars.map((b) => b.running_total ?? b.value ?? 0),
    data.start_value ?? 0,
    data.end_value ?? 0,
  )

  return (
    <div className="w-full h-full flex items-start justify-center overflow-auto p-4">
      <div className="bg-white rounded-lg shadow-lg p-6 w-full max-w-4xl">
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{data.title}</h2>
            <p className="text-sm text-gray-500">{data.subtitle}</p>
          </div>
          <div className="flex items-center gap-3">
            {data.data_source && (
              <span className="text-xs text-gray-400">Source: {data.data_source}</span>
            )}
            <button
              onClick={handleDownload}
              disabled={downloading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-green-700 bg-green-50 border border-green-200 rounded-md hover:bg-green-100 disabled:opacity-50 transition-colors"
            >
              {downloading ? (
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              )}
              Download Excel
            </button>
          </div>
        </div>

        {/* Vertical waterfall chart */}
        <div className="w-full" style={{ height: '380px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{ top: 30, right: 20, left: 20, bottom: 5 }}
              barSize={48}
            >
              <XAxis
                type="category"
                dataKey="label"
                tick={{ fontSize: 11, fill: '#374151' }}
                axisLine={{ stroke: '#D1D5DB' }}
                tickLine={false}
                interval={0}
              />
              <YAxis
                type="number"
                domain={[0, Math.ceil(maxVal * 1.1)]}
                tickFormatter={(v: number) => `$${v.toFixed(0)}M`}
                tick={{ fontSize: 11, fill: '#6B7280' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                {...{ formatter: (_val: any, name: string, props: any) => {
                  if (name === 'base') return [null, null]
                  const bar = props.payload
                  return [formatLabel(bar.rawValue, bar.type), bar.label]
                }} as any}
                contentStyle={{ borderRadius: 8, border: '1px solid #E5E7EB', fontSize: 13 }}
              />
              {/* Invisible base bar */}
              <Bar dataKey="base" stackId="stack" fill="transparent" isAnimationActive={false} />
              {/* Visible value bar with per-bar colors */}
              <Bar dataKey="value" stackId="stack" radius={[4, 4, 0, 0]} isAnimationActive={false}
                label={({ x, y, width, index }: any) => {
                  const bar = chartData[index]
                  if (!bar) return null
                  return (
                    <text
                      x={x + width / 2}
                      y={y - 8}
                      textAnchor="middle"
                      fill={bar.type === 'total' ? '#374151' : bar.rawValue != null && bar.rawValue >= 0 ? '#059669' : '#DC2626'}
                      fontSize={12}
                      fontWeight={bar.type === 'total' ? 600 : 400}
                      fontFamily="ui-monospace, monospace"
                    >
                      {formatLabel(bar.rawValue, bar.type)}
                    </text>
                  )
                }}
              >
                {chartData.map((bar, index) => (
                  <Cell
                    key={index}
                    fill={bar.type === 'total' ? COLORS.total : (bar.rawValue ?? 0) >= 0 ? COLORS.increase : COLORS.decrease}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Summary line */}
        {data.start_value != null && data.end_value != null && (
          <div className="mt-4 pt-3 border-t border-gray-200 text-sm text-gray-600 text-center">
            Total revenue change: <span className={`font-semibold ${data.end_value - data.start_value >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {data.end_value - data.start_value >= 0 ? '+' : ''}${(data.end_value - data.start_value).toFixed(1)}M
            </span>
            {' '}({((data.end_value - data.start_value) / data.start_value * 100).toFixed(1)}% YoY)
          </div>
        )}
      </div>
    </div>
  )
}
