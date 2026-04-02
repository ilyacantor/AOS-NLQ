import { useSnapshot } from '../contexts/SnapshotContext'

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

export function SnapshotSelector() {
  const { snapshots, selectedSnapshot, setSelectedSnapshot, loading, error } = useSnapshot()

  if (loading) {
    return (
      <div className="text-slate-500 text-xs px-2 py-1">
        Loading snapshots...
      </div>
    )
  }

  if (error || snapshots.length === 0) {
    return null
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-slate-500 text-xs hidden lg:inline">Snapshot:</span>
      <select
        id="snapshot-selector"
        value={selectedSnapshot?.dcl_ingest_id || ''}
        onChange={(e) => {
          const snap = snapshots.find(s => s.dcl_ingest_id === e.target.value)
          if (snap) setSelectedSnapshot(snap)
        }}
        className="bg-slate-800 border border-slate-700 rounded-md text-slate-300 text-xs px-2 py-1 focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
      >
        {snapshots.map((snap) => (
          <option key={snap.dcl_ingest_id} value={snap.dcl_ingest_id}>
            {snap.snapshot_name} -- {formatRelativeTime(snap.run_timestamp)} -- {snap.total_rows.toLocaleString()} triples
          </option>
        ))}
      </select>
    </div>
  )
}
