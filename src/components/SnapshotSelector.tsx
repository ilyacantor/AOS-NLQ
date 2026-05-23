import type { SurfaceSnapshot, Snapshot } from '../contexts/SnapshotContext'

function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp)
  if (isNaN(date.getTime())) return timestamp
  const now = Date.now()
  const diffMs = now - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHrs = Math.floor(diffMin / 60)
  if (diffHrs < 24) return `${diffHrs}h ago`
  const diffDays = Math.floor(diffHrs / 24)
  return `${diffDays}d ago`
}

function optionLabel(snap: Snapshot, isLatest: boolean): string {
  const name = snap.snapshot_name || snap.dcl_ingest_id?.slice(0, 12) || 'Unknown'
  // ★ marks the latest snapshot (`*`). Selecting it re-engages follow-latest.
  const star = isLatest ? '★ ' : ''
  return `${star}${name} -- ${formatRelativeTime(snap.run_timestamp)} -- ${snap.total_rows.toLocaleString()} triples`
}

/**
 * Snapshot selector for one surface. `surface` carries that surface's own
 * follow-latest/pin state (see useSurfaceSnapshot) — render one per surface so
 * pinning one surface leaves the others untouched.
 */
export function SnapshotSelector({ surface }: { surface: SurfaceSnapshot }) {
  const { snapshots, latest, effective, isPinned, loading, error, select } = surface

  if (loading) {
    return <div className="text-slate-500 text-xs px-2 py-1">Loading snapshots...</div>
  }
  if (error || snapshots.length === 0) {
    return null
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-slate-500 text-xs hidden lg:inline">Snapshot:</span>
      <select
        id="snapshot-selector"
        value={effective?.dcl_ingest_id || ''}
        onChange={(e) => {
          const snap = snapshots.find((s) => s.dcl_ingest_id === e.target.value)
          if (snap) select(snap)
        }}
        className="bg-slate-800 border border-slate-700 rounded-md text-slate-300 text-xs px-2 py-1 focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
      >
        {snapshots.map((snap) => (
          <option key={snap.dcl_ingest_id} value={snap.dcl_ingest_id}>
            {optionLabel(snap, latest?.dcl_ingest_id === snap.dcl_ingest_id)}
          </option>
        ))}
      </select>
      <span
        data-role="snapshot-follow-state"
        className={`text-[10px] px-1.5 py-0.5 rounded ${
          isPinned ? 'bg-amber-500/15 text-amber-400' : 'bg-cyan-500/15 text-cyan-400'
        }`}
        title={
          isPinned
            ? 'Pinned to this snapshot — select the ★ (latest) option to follow latest again'
            : 'Following the latest snapshot'
        }
      >
        {isPinned ? 'pinned' : 'following latest'}
      </span>
    </div>
  )
}
