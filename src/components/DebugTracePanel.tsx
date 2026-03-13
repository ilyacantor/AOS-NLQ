/**
 * Debug Trace Panel
 *
 * Displays the [NLQ-DIAG] trace from the most recent query response,
 * plus any error information from debug_info.
 * Each trace line shows the path data took through the backend:
 * endpoint -> catalog fetch -> DCL query -> response.
 */

import { useState } from 'react'

interface DebugTracePanelProps {
  trace: string[] | null
  /** Full debug_info object from the response (may contain error, error_type, etc.) */
  debugInfo?: Record<string, any> | null
}

/** Classify a trace line for icon + color. */
function classify(line: string): { icon: string; color: string } {
  if (line.includes('EXCEPTION') || line.includes('FAILED') || line.includes('UNHANDLED'))
    return { icon: '\u2716', color: 'text-red-400' }       // ✖
  if (line.includes('LOCAL FALLBACK') || line.includes('returned None'))
    return { icon: '\u26A0', color: 'text-amber-400' }     // ⚠
  if (line.includes('CONFIG_ERROR') || line.includes('HTTP_ERROR'))
    return { icon: '\u26A0', color: 'text-orange-400' }    // ⚠
  if (line.includes('status=200') || line.includes('loaded OK'))
    return { icon: '\u2714', color: 'text-emerald-400' }   // ✔
  if (line.includes('GET ') || line.includes('POST '))
    return { icon: '\u2192', color: 'text-cyan-400' }      // →
  return { icon: '\u2022', color: 'text-slate-400' }       // •
}

export function DebugTracePanel({ trace, debugInfo }: DebugTracePanelProps) {
  const [expanded, setExpanded] = useState<number | null>(null)

  const hasError = debugInfo?.error || debugInfo?.error_type
  const hasTrace = trace && trace.length > 0

  if (!hasTrace && !hasError) {
    return (
      <div className="p-4">
        <div className="text-slate-500 text-sm text-center py-8">
          No trace yet — submit a query to see the data path
        </div>
      </div>
    )
  }

  return (
    <div className="p-3 space-y-1">
      {/* Error banner — shown prominently when backend returned an error */}
      {hasError && (
        <div className="mb-3 p-3 rounded-lg border border-red-800/60 bg-red-950/40">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-red-400 text-sm font-semibold">
              {debugInfo?.error_type === 'NETWORK_ERROR' ? 'Connection Error' :
               debugInfo?.error_type === 'CONFIG_ERROR' ? 'Configuration Error' :
               debugInfo?.error_type === 'HTTP_ERROR' ? 'Server Error' :
               'Query Error'}
            </span>
            <span className="text-red-400/60 text-xs font-mono">{debugInfo?.error_type}</span>
          </div>
          <p className="text-red-300/90 text-xs font-mono break-all leading-relaxed">
            {debugInfo?.error}
          </p>
          {debugInfo?.error_type === 'NETWORK_ERROR' && (
            <p className="text-slate-400 text-xs mt-2">
              The frontend cannot reach the backend. In Replit, make sure both the "Start Backend" and "Start Frontend" workflows are running. Check the Replit console for backend errors.
            </p>
          )}
          {debugInfo?.error_type === 'CONFIG_ERROR' && debugInfo?.error?.includes('ANTHROPIC_API_KEY') && (
            <p className="text-slate-400 text-xs mt-2">
              Set the ANTHROPIC_API_KEY secret in Replit (Tools &gt; Secrets) to enable AI-powered queries. Demo-context queries (simple metric lookups) work without it.
            </p>
          )}
        </div>
      )}

      {/* Header */}
      {hasTrace && (
        <>
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Request Trace ({trace!.length} steps)
            </span>
          </div>

          {/* Trace lines */}
          <div className="space-y-0.5">
            {trace!.map((line, i) => {
              const { icon, color } = classify(line)
              // Strip the [NLQ-DIAG] prefix for cleaner display
              const display = line.replace(/^\[NLQ-DIAG\]\s*/, '')
              const isLong = display.length > 90
              const isExpanded = expanded === i

              return (
                <div
                  key={i}
                  onClick={() => isLong && setExpanded(isExpanded ? null : i)}
                  className={`px-2 py-1.5 rounded text-xs font-mono leading-relaxed
                    bg-slate-900/40 border border-slate-800/50
                    ${isLong ? 'cursor-pointer hover:bg-slate-800/50' : ''}
                    transition-colors`}
                >
                  <span className={`${color} mr-1.5`}>{icon}</span>
                  <span className="text-slate-300">
                    {isLong && !isExpanded ? display.slice(0, 88) + '...' : display}
                  </span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
