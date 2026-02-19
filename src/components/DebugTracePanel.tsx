/**
 * Debug Trace Panel
 *
 * Displays the [NLQ-DIAG] trace from the most recent query response.
 * Each trace line shows the path data took through the backend:
 * endpoint -> catalog fetch -> DCL query -> response.
 */

import React, { useState } from 'react'

interface DebugTracePanelProps {
  trace: string[] | null
}

/** Classify a trace line for icon + color. */
function classify(line: string): { icon: string; color: string } {
  if (line.includes('EXCEPTION') || line.includes('FAILED'))
    return { icon: '\u2716', color: 'text-red-400' }       // ✖
  if (line.includes('LOCAL FALLBACK') || line.includes('returned None'))
    return { icon: '\u26A0', color: 'text-amber-400' }     // ⚠
  if (line.includes('status=200') || line.includes('loaded OK'))
    return { icon: '\u2714', color: 'text-emerald-400' }   // ✔
  if (line.includes('GET ') || line.includes('POST '))
    return { icon: '\u2192', color: 'text-cyan-400' }      // →
  return { icon: '\u2022', color: 'text-slate-400' }       // •
}

export function DebugTracePanel({ trace }: DebugTracePanelProps) {
  const [expanded, setExpanded] = useState<number | null>(null)

  if (!trace || trace.length === 0) {
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
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
          Request Trace ({trace.length} steps)
        </span>
      </div>

      {/* Trace lines */}
      <div className="space-y-0.5">
        {trace.map((line, i) => {
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
    </div>
  )
}
