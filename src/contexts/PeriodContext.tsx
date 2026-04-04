import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'

export interface Period {
  year: string
  label: string
}

interface PeriodContextValue {
  periods: Period[]
  selectedPeriod: Period | null
  setSelectedPeriod: (period: Period) => void
  loading: boolean
  error: string | null
}

const PeriodContext = createContext<PeriodContextValue | null>(null)

export function usePeriod(): PeriodContextValue {
  const ctx = useContext(PeriodContext)
  if (!ctx) {
    throw new Error('usePeriod must be used within a PeriodProvider')
  }
  return ctx
}

export function PeriodProvider({ children }: { children: React.ReactNode }) {
  const [periods, setPeriods] = useState<Period[]>([])
  const [selectedPeriod, setSelectedPeriod] = useState<Period | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchPeriods = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/v1/periods')
      if (!res.ok) {
        const errText = await res.text().catch(() => 'Unknown error')
        throw new Error(
          `Period fetch failed (HTTP ${res.status}): ${errText.slice(0, 500)}`
        )
      }
      const data = await res.json()
      const list: Period[] = data.periods || []
      setPeriods(list)
      if (list.length > 0) {
        setSelectedPeriod(list[0])
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      console.error('Failed to fetch periods:', msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchPeriods()
  }, [fetchPeriods])

  return (
    <PeriodContext.Provider
      value={{ periods, selectedPeriod, setSelectedPeriod, loading, error }}
    >
      {children}
    </PeriodContext.Provider>
  )
}
