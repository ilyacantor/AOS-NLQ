import { useState } from 'react'
import type { FinancialStatementData } from './types'

interface Props {
  data: FinancialStatementData
  sessionId: string
}

function formatValue(value: number | null, format: string): string {
  if (value === null || value === undefined) return '--'
  if (format === 'percent') {
    return `${value.toFixed(1)}%`
  }
  // Currency: negative in parentheses
  if (value < 0) {
    return `($${Math.abs(value).toFixed(1)})`
  }
  return `$${value.toFixed(1)}`
}

export function FinancialStatementView({ data, sessionId }: Props) {
  const [downloading, setDownloading] = useState(false)

  const handleDownload = async () => {
    setDownloading(true)
    try {
      const res = await fetch(`/api/v1/export/financial-statement?session_id=${encodeURIComponent(sessionId)}&format=xlsx`)
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Download failed' }))
        console.error('Export failed:', err)
        return
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'income_statement.xlsx'
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

  return (
    <div className="w-full h-full flex items-start justify-center overflow-auto p-4">
      <div className="bg-white rounded-lg shadow-lg p-6 max-w-[90vw]">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{data.title}</h2>
            <p className="text-sm text-gray-500">{data.entity}</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400">All amounts in ${data.unit === 'millions' ? 'M' : data.unit}</span>
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

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b-2 border-gray-300">
                <th className="text-left py-2 pr-4 text-sm font-semibold text-gray-700 sticky left-0 bg-white z-10 min-w-[200px]">
                  &nbsp;
                </th>
                {data.periods.map(period => (
                  <th
                    key={period}
                    className={`text-right py-2 px-3 text-sm font-semibold text-gray-700 whitespace-nowrap ${
                      period.startsWith('FY') ? 'bg-gray-50 border-l border-gray-200' : ''
                    }`}
                  >
                    {period}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.line_items.map((item, idx) => (
                <tr
                  key={item.key}
                  className={`
                    ${item.is_subtotal ? 'border-t border-gray-400 font-semibold' : ''}
                    ${idx % 2 === 0 && !item.is_subtotal ? 'bg-gray-50/50' : ''}
                  `}
                >
                  <td
                    className={`py-1.5 pr-4 text-sm text-gray-900 sticky left-0 bg-inherit z-10 whitespace-nowrap ${
                      item.is_subtotal ? 'font-semibold' : ''
                    }`}
                    style={{ paddingLeft: `${item.indent * 1.5 + 0.5}rem` }}
                  >
                    {item.label}
                  </td>
                  {data.periods.map(period => {
                    const val = item.values[period]
                    const isNegative = val !== null && val !== undefined && val < 0
                    return (
                      <td
                        key={period}
                        className={`py-1.5 px-3 text-sm text-right font-mono whitespace-nowrap ${
                          item.is_subtotal ? 'font-semibold' : ''
                        } ${isNegative ? 'text-red-600' : 'text-gray-900'} ${
                          period.startsWith('FY') ? 'bg-gray-50 border-l border-gray-200' : ''
                        }`}
                      >
                        {formatValue(val, item.format)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
