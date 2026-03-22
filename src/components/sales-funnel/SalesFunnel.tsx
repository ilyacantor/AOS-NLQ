/**
 * SalesFunnel — horizontal pipeline funnel visualization.
 *
 * Renders pipeline stages as narrowing bars (left-to-right or top-to-bottom
 * depending on container width). Each bar shows stage label, dollar amount,
 * and conversion percentage relative to the first stage.
 *
 * Pure Tailwind — no charting library.
 */
export interface SalesFunnelStage {
  label: string
  value: number
  percent: number
}

export interface SalesFunnelData {
  title: string
  subtitle?: string
  stages: SalesFunnelStage[]
  unit?: string
  format?: string
  entity_id?: string | null
  period?: string | null
  data_source?: string | null
}

interface SalesFunnelProps {
  data: SalesFunnelData
}

const STAGE_COLORS = [
  'bg-cyan-500',
  'bg-cyan-600',
  'bg-teal-500',
  'bg-teal-600',
  'bg-emerald-600',
]

function formatCurrency(value: number): string {
  if (Math.abs(value) >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}B`
  }
  if (Math.abs(value) >= 1) {
    return `$${value.toFixed(0)}M`
  }
  return `$${(value * 1_000).toFixed(0)}K`
}

export default function SalesFunnel({ data }: SalesFunnelProps) {
  const { title, subtitle, stages } = data

  if (!stages || stages.length === 0) {
    return (
      <div className="w-full p-6 text-center text-slate-400">
        Pipeline data not available
      </div>
    )
  }

  const maxValue = Math.max(...stages.map((s) => s.value))

  return (
    <div className="w-full max-w-3xl mx-auto p-6">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-slate-100">{title}</h3>
        {subtitle && (
          <p className="text-sm text-slate-400">{subtitle}</p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        {stages.map((stage, i) => {
          const widthPct = maxValue > 0 ? (stage.value / maxValue) * 100 : 0
          const colorClass = STAGE_COLORS[i % STAGE_COLORS.length]

          return (
            <div key={stage.label} className="flex items-center gap-3">
              {/* Stage label */}
              <div className="w-28 shrink-0 text-right text-sm text-slate-300">
                {stage.label}
              </div>

              {/* Bar container */}
              <div className="flex-1 relative h-9">
                <div
                  className={`${colorClass} h-full rounded-r-md transition-all duration-500 flex items-center`}
                  style={{ width: `${Math.max(widthPct, 4)}%` }}
                >
                  <span className="px-3 text-sm font-medium text-white whitespace-nowrap">
                    {formatCurrency(stage.value)}
                  </span>
                </div>
              </div>

              {/* Conversion percentage */}
              <div className="w-14 shrink-0 text-right text-xs text-slate-500">
                {stage.percent.toFixed(0)}%
              </div>
            </div>
          )
        })}
      </div>

      {data.data_source && (
        <p className="mt-3 text-xs text-slate-600">
          Source: {data.data_source}
        </p>
      )}
    </div>
  )
}
