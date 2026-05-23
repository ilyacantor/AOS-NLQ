import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'

export interface Snapshot {
  dcl_ingest_id: string
  snapshot_name: string | null
  entity_id: string | null
  run_timestamp: string
  total_rows: number
}

interface SnapshotContextValue {
  snapshots: Snapshot[]
  /** The `*` — the latest generated AND DCL-processed snapshot (max run_timestamp). */
  latest: Snapshot | null
  loading: boolean
  error: string | null
}

const SnapshotContext = createContext<SnapshotContextValue | null>(null)

/** Poll interval for the snapshot list. Follow-latest surfaces advance within this window. */
const POLL_MS = 12_000

/** `*` = the latest snapshot, by max run_timestamp. NOT DCL's `is_current` (that field
 *  tracks tenant_runs.current_run_id and does not reliably point at the newest run). */
function computeLatest(list: Snapshot[]): Snapshot | null {
  if (list.length === 0) return null
  return list.reduce((newest, s) =>
    new Date(s.run_timestamp).getTime() > new Date(newest.run_timestamp).getTime() ? s : newest
  )
}

export function useSnapshot(): SnapshotContextValue {
  const ctx = useContext(SnapshotContext)
  if (!ctx) {
    throw new Error('useSnapshot must be used within a SnapshotProvider')
  }
  return ctx
}

export function SnapshotProvider({ children }: { children: React.ReactNode }) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [latest, setLatest] = useState<Snapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchSnapshots = useCallback(async () => {
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
      setLatest(computeLatest(list))
      setError(null)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      console.error('Failed to fetch snapshots:', msg)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch + poll so follow-latest surfaces advance when a new snapshot
  // is ingested. Polling (not SSE) — no server-push infra in NLQ/DCL.
  useEffect(() => {
    fetchSnapshots()
    const id = setInterval(fetchSnapshots, POLL_MS)
    return () => clearInterval(id)
  }, [fetchSnapshots])

  return (
    <SnapshotContext.Provider value={{ snapshots, latest, loading, error }}>
      {children}
    </SnapshotContext.Provider>
  )
}

/**
 * Per-surface snapshot selection. The shared context supplies the snapshot list
 * and `*` (latest); each surface holds its own pin. Effective = `pinned ?? latest`:
 *  - default (no pin) = follow-latest: the surface tracks `*` as it advances.
 *  - selecting a non-`*` snapshot pins this surface only — other surfaces unaffected.
 *  - selecting `*` clears the pin and re-engages follow-latest.
 */
export interface SurfaceSnapshot {
  snapshots: Snapshot[]
  latest: Snapshot | null
  effective: Snapshot | null
  isPinned: boolean
  loading: boolean
  error: string | null
  select: (snapshot: Snapshot) => void
  followLatest: () => void
}

export function useSurfaceSnapshot(): SurfaceSnapshot {
  const { snapshots, latest, loading, error } = useSnapshot()
  const [pinnedId, setPinnedId] = useState<string | null>(null)

  // Resolve the pin against the live list each render — a pinned snapshot that
  // is no longer present falls back to follow-latest rather than going stale.
  const pinned = pinnedId
    ? snapshots.find((s) => s.dcl_ingest_id === pinnedId) ?? null
    : null
  const effective = pinned ?? latest

  const select = useCallback(
    (snapshot: Snapshot) => {
      // Selecting `*` re-engages follow-latest; anything else pins this surface.
      setPinnedId(
        latest && snapshot.dcl_ingest_id === latest.dcl_ingest_id
          ? null
          : snapshot.dcl_ingest_id
      )
    },
    [latest]
  )

  const followLatest = useCallback(() => setPinnedId(null), [])

  return {
    snapshots,
    latest,
    effective,
    isPinned: pinned !== null,
    loading,
    error,
    select,
    followLatest,
  }
}
