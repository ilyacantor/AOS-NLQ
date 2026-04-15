/**
 * SalesFunnel — SVG pipeline funnel visualization.
 *
 * Renders pipeline stages as a tapering funnel (wide at top, narrow at
 * bottom). The funnel outline tapers linearly regardless of data values —
 * the shape is the metaphor, the numbers are the data.
 * Responsive: hides side labels in compact containers (<280px).
 */
import { useState, useEffect, useRef } from 'react'

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

const FUNNEL_COLORS = [
  '#0BCAD9', // cyan
  '#3B82F6', // blue
  '#14B8A6', // teal
  '#10B981', // green
  '#8B5CF6', // purple
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

/** Fraction of top width that the bottom of the funnel narrows to. */
const TAPER_BOTTOM = 0.3

export default function SalesFunnel({ data }: SalesFunnelProps) {
  const { title, subtitle, stages } = data
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [height, setHeight] = useState(0)
  const [hovered, setHovered] = useState<number | null>(null)
  const [tipPos, setTipPos] = useState({ x: 0, y: 0 })

  useEffect(() => {
    const el = wrapperRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setWidth(entry.contentRect.width)
        setHeight(entry.contentRect.height)
      }
    })
    ro.observe(el)
    setWidth(el.clientWidth)
    setHeight(el.clientHeight)
    return () => ro.disconnect()
  }, [])

  if (!stages || stages.length === 0) {
    return (
      <div className="w-full p-6 text-center text-slate-400">
        Pipeline data not available
      </div>
    )
  }

  // Layout constants — three tiers based on measured container width
  const compact = width > 0 && width < 180          // dashboard widget
  const medium = !compact && width > 0 && width < 400 // report portal card
  const defaultStageH = compact ? 32 : medium ? 38 : 44
  const gap = 3
  // Scale stage height down when the container constrains height
  const uncappedSvgH = stages.length * (defaultStageH + gap) - gap
  const stageH = height > 0 && uncappedSvgH > height
    ? Math.max(Math.floor((height + gap) / stages.length - gap), 16)
    : defaultStageH
  const labelW = compact ? 0 : medium ? 72 : 110
  const pctW = compact ? 0 : medium ? 40 : 56
  const funnelW = Math.max(width - labelW - pctW, 40)
  const cx = labelW + funnelW / 2
  const svgH = stages.length * (stageH + gap) - gap

  /** Width of the funnel at a given y coordinate (linear taper). */
  function funnelWidthAtY(y: number): number {
    const t = svgH > 0 ? y / svgH : 0
    return (1 + (TAPER_BOTTOM - 1) * t) * funnelW
  }

  /** SVG path for the i-th stage band within the funnel. */
  function bandPath(i: number): string {
    const yTop = i * (stageH + gap)
    const yBot = yTop + stageH
    const wTop = funnelWidthAtY(yTop)
    const wBot = funnelWidthAtY(yBot)
    return [
      `M ${cx - wTop / 2},${yTop}`,
      `L ${cx + wTop / 2},${yTop}`,
      `L ${cx + wBot / 2},${yBot}`,
      `L ${cx - wBot / 2},${yBot}`,
      'Z',
    ].join(' ')
  }

  function handleMouseEnter(i: number, e: React.MouseEvent) {
    setHovered(i)
    updateTip(e)
  }

  function updateTip(e: React.MouseEvent) {
    const rect = wrapperRef.current?.getBoundingClientRect()
    if (rect) {
      setTipPos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
    }
  }

  // Place tooltip on whichever side of the cursor has more room
  const tipLeft = width > 0 && tipPos.x > width / 2
    ? Math.max(tipPos.x - 180, 0)
    : tipPos.x + 12

  return (
    <div className="w-full max-w-3xl mx-auto px-4 py-3 h-full flex flex-col overflow-hidden">
      {title && (
        <div className="mb-3 shrink-0">
          <h3 className="text-base font-semibold text-slate-100">{title}</h3>
          {subtitle && (
            <p className="text-xs text-slate-400">{subtitle}</p>
          )}
        </div>
      )}

      <div ref={wrapperRef} className="relative w-full flex-1 min-h-0">
        {width > 0 && (
          <svg
            width={width}
            height={svgH}
            viewBox={`0 0 ${width} ${svgH}`}
            role="img"
            aria-label={`Sales pipeline funnel: ${stages.map(s => `${s.label} ${formatCurrency(s.value)}`).join(', ')}`}
          >
            {stages.map((stage, i) => {
              const yTop = i * (stageH + gap)
              const midY = yTop + stageH / 2

              return (
                <g
                  key={stage.label}
                  style={{
                    animation: 'fadeIn 0.4s ease forwards',
                    animationDelay: `${i * 80}ms`,
                    opacity: 0,
                  }}
                  onMouseEnter={(e) => handleMouseEnter(i, e)}
                  onMouseMove={updateTip}
                  onMouseLeave={() => setHovered(null)}
                >
                  <path
                    d={bandPath(i)}
                    fill={FUNNEL_COLORS[i % FUNNEL_COLORS.length]}
                    className="cursor-pointer transition-opacity duration-150"
                    opacity={hovered === null || hovered === i ? 1 : 0.6}
                  />

                  {/* Stage label — left of funnel */}
                  {!compact && (
                    <text
                      x={labelW - 8}
                      y={midY}
                      textAnchor="end"
                      dominantBaseline="central"
                      fill="#cbd5e1"
                      fontSize={medium ? 15 : 15}
                      fontFamily="system-ui, -apple-system, sans-serif"
                    >
                      {stage.label}
                    </text>
                  )}

                  {/* Dollar value — centered inside band */}
                  <text
                    x={cx}
                    y={midY}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill="#ffffff"
                    fontSize={compact ? 15 : medium ? 14 : 16}
                    fontWeight={600}
                    fontFamily="system-ui, -apple-system, sans-serif"
                  >
                    {formatCurrency(stage.value)}
                  </text>

                  {/* Conversion percent — right of funnel */}
                  {!compact && (
                    <text
                      x={labelW + funnelW + 8}
                      y={midY}
                      textAnchor="start"
                      dominantBaseline="central"
                      fill="#64748b"
                      fontSize={medium ? 14 : 14}
                      fontFamily="system-ui, -apple-system, sans-serif"
                    >
                      {stage.percent.toFixed(0)}%
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        )}

        {/* Hover tooltip */}
        {hovered !== null && (
          <div
            className="pointer-events-none"
            style={{
              position: 'absolute',
              left: tipLeft,
              top: Math.max(tipPos.y - 10, 0),
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 8,
              padding: '8px 12px',
              zIndex: 50,
              whiteSpace: 'nowrap',
            }}
          >
            <div style={{ fontSize: 15, fontWeight: 600, color: '#f1f5f9' }}>
              {stages[hovered].label}
            </div>
            <div style={{ fontSize: 14, color: '#94a3b8', marginTop: 2 }}>
              {formatCurrency(stages[hovered].value)} &mdash; {stages[hovered].percent.toFixed(1)}% conversion
            </div>
          </div>
        )}
      </div>

      {data.data_source && (
        <p className="mt-3 text-xs text-slate-600 shrink-0">
          Source: {data.data_source}
        </p>
      )}
    </div>
  )
}
