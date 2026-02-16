import React, { useState, useEffect, useCallback } from 'react';

interface PipelineStatus {
  dcl_connected: boolean;
  dcl_mode: string | null;
  metric_count: number;
  last_run_id: string | null;
  last_run_timestamp: string | null;
  last_source_systems: string[] | null;
  freshness: string | null;
}

const POLL_INTERVAL = 30000; // 30s

/**
 * Permanent data pipeline status light in the app header.
 *
 * Shows a persistent indicator of the 3-light chain:
 *   Green dot  = Live/Ingest mode — verified Runner data flowing
 *   Blue dot   = Demo/Farm mode — simulation data
 *   Grey dot   = Disconnected or local fallback
 *
 * Clicking expands a dropdown with pipeline details.
 * Auto-refreshes every 30s.
 */
export const DataPipelineStatus: React.FC = () => {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/pipeline/status');
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
        setError(false);
      } else {
        setError(true);
      }
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // Determine state
  const mode = status?.dcl_mode?.toLowerCase() ?? null;
  const isLive = mode === 'farm' || mode === 'ingest' || mode === 'live';
  const isRunner = mode === 'aam';
  const isDemo = mode === 'demo';

  // Format relative time
  const formatRelative = (iso: string | null): string => {
    if (!iso) return '';
    try {
      const diff = Date.now() - new Date(iso).getTime();
      if (diff < 0) return 'just now';
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return 'just now';
      if (mins < 60) return `${mins}m ago`;
      const hours = Math.floor(mins / 60);
      if (hours < 24) return `${hours}h ago`;
      return `${Math.floor(hours / 24)}d ago`;
    } catch {
      return '';
    }
  };

  // Light config
  const light = isLive
    ? { color: 'bg-emerald-400', ring: 'ring-emerald-400/30', label: 'Live', pulse: true }
    : isRunner
      ? { color: 'bg-cyan-400', ring: 'ring-cyan-400/30', label: 'Runner', pulse: false }
      : isDemo
        ? { color: 'bg-blue-400', ring: 'ring-blue-400/30', label: 'Demo', pulse: false }
        : { color: 'bg-slate-500', ring: 'ring-slate-500/20', label: 'Local', pulse: false };

  return (
    <div className="relative">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-slate-800/50 transition-colors"
        title={`Pipeline: ${light.label}`}
      >
        {/* The dot */}
        <span className="relative flex h-2.5 w-2.5">
          {light.pulse && (
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${light.color} opacity-50`} />
          )}
          <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${light.color} ring-2 ${light.ring}`} />
        </span>
        <span className="text-xs text-slate-400 hidden lg:inline">{light.label}</span>
      </button>

      {/* Dropdown panel */}
      {expanded && (
        <>
          {/* Backdrop to close */}
          <div className="fixed inset-0 z-40" onClick={() => setExpanded(false)} />

          <div className="absolute right-0 top-full mt-1 z-50 w-72 bg-slate-900 border border-slate-700 rounded-lg shadow-xl">
            {/* Header */}
            <div className="px-4 py-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className={`inline-flex rounded-full h-2.5 w-2.5 ${light.color}`} />
                <span className="text-sm font-medium text-white">
                  {isLive ? 'Pipeline Active' : isRunner ? 'Runner Mode' : isDemo ? 'Demo Mode' : 'Local Mode'}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {isLive
                  ? 'Farm → DCL → NLQ — live data flowing'
                  : isRunner
                    ? 'AAM Runner loading metrics into DCL'
                    : isDemo
                      ? 'Using demo data from DCL'
                      : 'No DCL connection — using local data'}
              </p>
            </div>

            {/* Status rows */}
            <div className="px-4 py-3 space-y-2.5 text-xs">
              {/* DCL Connection */}
              <div className="flex items-center justify-between">
                <span className="text-slate-500">DCL</span>
                <span className={`flex items-center gap-1.5 ${status?.dcl_connected ? 'text-emerald-400' : 'text-slate-500'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${status?.dcl_connected ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                  {status?.dcl_connected ? 'Connected' : 'Local Fallback'}
                </span>
              </div>

              {/* Mode */}
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Mode</span>
                <span className="text-slate-300">{light.label}</span>
              </div>

              {/* Metrics */}
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Metrics</span>
                <span className="text-slate-300">{status?.metric_count ?? 0} loaded</span>
              </div>

              {/* Last Run (only if available) */}
              {status?.last_run_id && (
                <>
                  <div className="border-t border-slate-800 pt-2.5 mt-2.5">
                    <span className="text-slate-500 text-[10px] uppercase tracking-wider">Last Ingestion</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Run ID</span>
                    <span className="text-slate-400 font-mono text-[10px] truncate max-w-[140px]">{status.last_run_id}</span>
                  </div>
                  {status.last_source_systems && status.last_source_systems.length > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Source</span>
                      <span className="text-slate-300">{status.last_source_systems.join(', ')}</span>
                    </div>
                  )}
                  {status.last_run_timestamp && (
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Updated</span>
                      <span className="text-slate-300">{formatRelative(status.last_run_timestamp)}</span>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
