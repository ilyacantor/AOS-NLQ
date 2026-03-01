import React, { useState, useEffect, useCallback, useRef } from 'react';

interface PipelineStatus {
  dcl_connected: boolean;
  dcl_mode: string | null;
  metric_count: number;
  last_run_id: string | null;
  last_run_timestamp: string | null;
  last_source_systems: string[] | null;
  freshness: string | null;
}

interface Props {
  dataMode?: 'live' | 'demo';
}

// Polling intervals
const FAST_POLL_INTERVAL = 30_000;   // 30s during first 2 minutes (cold-start recovery)
const NORMAL_POLL_INTERVAL = 60_000; // 60s after initial warm-up period
const FAST_POLL_WINDOW = 120_000;    // 2 minutes of fast polling after mount

// Retry backoffs for initial fetch (ms)
const MOUNT_RETRY_BACKOFFS = [2_000, 4_000, 8_000];

export const DataPipelineStatus: React.FC<Props> = ({ dataMode = 'live' }) => {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const mountTimeRef = useRef(Date.now());

  const fetchStatus = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch(`/api/v1/pipeline/status?data_mode=${dataMode}`);
      if (res.ok) {
        const data = await res.json();
        // Detect offline -> connected transition
        if (!status?.dcl_connected && data.dcl_connected) {
          setConnecting(true);
          setTimeout(() => setConnecting(false), 2_000);
        }
        setStatus(data);
        setError(false);
        return true;
      } else {
        setError(true);
        return false;
      }
    } catch {
      setError(true);
      return false;
    }
  }, [dataMode, status?.dcl_connected]);

  // Initial mount: retry with backoff to survive cold starts
  useEffect(() => {
    let cancelled = false;

    const fetchWithRetry = async () => {
      const success = await fetchStatus();
      if (success || cancelled) return;

      // Retry with exponential backoff
      for (const delay of MOUNT_RETRY_BACKOFFS) {
        if (cancelled) return;
        await new Promise(r => setTimeout(r, delay));
        if (cancelled) return;
        const ok = await fetchStatus();
        if (ok || cancelled) return;
      }
    };

    fetchWithRetry();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataMode]);

  // Polling: fast for first 2 min (cold-start recovery), then normal
  useEffect(() => {
    if (dataMode === 'demo') return;

    const getPollInterval = () => {
      const elapsed = Date.now() - mountTimeRef.current;
      return elapsed < FAST_POLL_WINDOW ? FAST_POLL_INTERVAL : NORMAL_POLL_INTERVAL;
    };

    let timer: ReturnType<typeof setTimeout>;
    const schedulePoll = () => {
      timer = setTimeout(async () => {
        await fetchStatus();
        schedulePoll();
      }, getPollInterval());
    };

    schedulePoll();
    return () => clearTimeout(timer);
  }, [fetchStatus, dataMode]);

  const isDemo = dataMode === 'demo';

  const mode = status?.dcl_mode?.toLowerCase() ?? null;
  const isLive = !isDemo && (mode === 'farm' || mode === 'ingest' || mode === 'live');
  const isConnectedDemo = !isDemo && status?.dcl_connected && !isLive;

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

  const light = isDemo
    ? { color: 'bg-slate-500', ring: 'ring-slate-500/20', label: 'Demo', pulse: false }
    : connecting
      ? { color: 'bg-amber-400', ring: 'ring-amber-400/30', label: 'Connecting...', pulse: true }
      : isLive
        ? { color: 'bg-emerald-400', ring: 'ring-emerald-400/30', label: 'Live', pulse: true }
        : isConnectedDemo
          ? { color: 'bg-amber-400', ring: 'ring-amber-400/30', label: 'Connected', pulse: false }
          : { color: 'bg-slate-500', ring: 'ring-slate-500/20', label: 'Offline', pulse: false };

  return (
    <div className="relative">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-slate-800/50 transition-colors"
        title={`Pipeline: ${light.label}`}
      >
        <span className="relative flex h-2.5 w-2.5">
          {light.pulse && (
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${light.color} opacity-50`} />
          )}
          <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${light.color} ring-2 ${light.ring}`} />
        </span>
        <span className="text-xs text-slate-400 hidden lg:inline">{light.label}</span>
      </button>

      {expanded && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setExpanded(false)} />

          <div className="absolute right-0 top-full mt-1 z-50 w-72 bg-slate-900 border border-slate-700 rounded-lg shadow-xl">
            <div className="px-4 py-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <span className={`inline-flex rounded-full h-2.5 w-2.5 ${light.color}`} />
                <span className="text-sm font-medium text-white">
                  {isDemo ? 'Demo Mode'
                    : connecting ? 'Connecting to DCL...'
                    : isLive ? 'Pipeline Active'
                    : isConnectedDemo ? 'DCL Connected'
                    : 'DCL Offline'}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {isDemo
                  ? `Using fact_base.json (${status?.metric_count ?? 96} metrics)`
                  : connecting
                    ? 'Establishing connection to DCL...'
                  : isLive
                    ? 'Live data flowing through DCL'
                    : isConnectedDemo
                      ? `DCL reachable — serving ${status?.metric_count ?? 0} metrics (no ingested data yet)`
                      : 'Cannot reach DCL — check that DCL backend is running on port 8004'}
              </p>
            </div>

            <div className="px-4 py-3 space-y-2.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">DCL</span>
                <span className={`flex items-center gap-1.5 ${isDemo ? 'text-slate-500' : status?.dcl_connected ? 'text-emerald-400' : 'text-slate-500'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${isDemo ? 'bg-slate-500' : status?.dcl_connected ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                  {isDemo ? 'Bypassed' : status?.dcl_connected ? 'Connected' : 'Local Fallback'}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-500">Mode</span>
                <span className="text-slate-300">{light.label}</span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-500">Metrics</span>
                <span className="text-slate-300">{status?.metric_count ?? 0} loaded</span>
              </div>

              {!isDemo && status?.last_run_id && (
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
