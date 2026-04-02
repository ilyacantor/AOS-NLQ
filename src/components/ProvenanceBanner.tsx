import { useState, useEffect } from 'react'

interface PipelineProvenance {
  dcl_connected: boolean
  dcl_mode: string | null
  metric_count: number
  last_dcl_ingest_id: string | null
  last_run_timestamp: string | null
  last_source_systems: string[] | null
}

function formatTimestamp(ts: string): string {
  const date = new Date(ts)
  if (isNaN(date.getTime())) return ts
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function ProvenanceBanner() {
  const [provenance, setProvenance] = useState<PipelineProvenance | null>(null)

  useEffect(() => {
    let cancelled = false
    async function fetchProvenance() {
      try {
        const res = await fetch('/api/v1/pipeline/status')
        if (!res.ok) return
        const data = await res.json()
        if (!cancelled) setProvenance(data)
      } catch {
        // Pipeline status unavailable — banner stays hidden
      }
    }
    fetchProvenance()
    return () => { cancelled = true }
  }, [])

  if (!provenance || !provenance.dcl_connected) return null

  const entities = provenance.last_source_systems
  const entityDisplay = entities && entities.length > 0
    ? entities.join(', ')
    : null

  return (
    <div className="px-4 py-2 bg-slate-900/60 border-b border-slate-800/50 flex items-center gap-4 text-xs text-slate-400">
      {entityDisplay && (
        <span>
          <span className="text-slate-500">Entity:</span>{' '}
          <span className="text-slate-300">{entityDisplay}</span>
        </span>
      )}
      {provenance.last_dcl_ingest_id && (
        <span>
          <span className="text-slate-500">Snapshot:</span>{' '}
          <span className="text-slate-300 font-mono">{provenance.last_dcl_ingest_id.slice(0, 12)}</span>
        </span>
      )}
      {provenance.last_run_timestamp && (
        <span>
          <span className="text-slate-500">Updated:</span>{' '}
          <span className="text-slate-300">{formatTimestamp(provenance.last_run_timestamp)}</span>
        </span>
      )}
      {provenance.metric_count > 0 && (
        <span>
          <span className="text-slate-500">Metrics:</span>{' '}
          <span className="text-slate-300">{provenance.metric_count}</span>
        </span>
      )}
    </div>
  )
}
