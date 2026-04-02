import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'

export interface Snapshot {
  dcl_ingest_id: string
  snapshot_name: string
  run_timestamp: string
  total_rows: number
  pipe_count: number
}

interface SnapshotContextValue {
  snapshots: Snapshot[]
  selectedSnapshot: Snapshot | null
  setSelectedSnapshot: (snapshot: Snapshot) => void
  loading: boolean
  error: string | null
}

const SnapshotContext = createContext<SnapshotContextValue | null>(null)

export function useSnapshot(): SnapshotContextValue {
  const ctx = useContext(SnapshotContext)
  if (!ctx) {
    throw new Error('useSnapshot must be used within a SnapshotProvider')
  }
  return ctx
}

export function SnapshotProvider({ children }: { children: React.ReactNode }) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [selectedSnapshot, setSelectedSnapshot] = useState<Snapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchSnapshots = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/v1/snapshots')
      if (!res.ok) {
        const errText = await res.text().catch(() => 'Unknown error')
        throw new Error(
          `Snapshot fetch failed (HTTP ${res.status}): ${errText.slice(0, 500)}`
        )
      }
      const data = await res.json()
      const list: Snapshot[] = data.snapshots || []
      setSnapshots(list)
      if (list.length > 0) {
        setSelectedSnapshot(list[0])
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      console.error('Failed to fetch snapshots:', msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSnapshots()
  }, [fetchSnapshots])

  return (
    <SnapshotContext.Provider
      value={{ snapshots, selectedSnapshot, setSelectedSnapshot, loading, error }}
    >
      {children}
    </SnapshotContext.Provider>
  )
}
