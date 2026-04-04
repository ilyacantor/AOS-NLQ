import { usePeriod } from '../contexts/PeriodContext'

export function PeriodSelector() {
  const { periods, selectedPeriod, setSelectedPeriod, loading, error } = usePeriod()

  if (loading) {
    return (
      <div className="text-slate-500 text-xs px-2 py-1">
        Loading periods...
      </div>
    )
  }

  if (error || periods.length === 0) {
    return null
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-slate-500 text-xs hidden lg:inline">Period:</span>
      <select
        id="period-selector"
        value={selectedPeriod?.year || ''}
        onChange={(e) => {
          const p = periods.find(p => p.year === e.target.value)
          if (p) setSelectedPeriod(p)
        }}
        className="bg-slate-800 border border-slate-700 rounded-md text-slate-300 text-xs px-2 py-1 focus:outline-none focus:ring-1 focus:ring-cyan-500/50"
      >
        {periods.map((p) => (
          <option key={p.year} value={p.year}>
            FY {p.label}
          </option>
        ))}
      </select>
    </div>
  )
}
