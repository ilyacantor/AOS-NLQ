/**
 * Insufficient Data Panel Component
 *
 * Displays queries that returned with low confidence (<80%),
 * indicating possible insufficient data conditions.
 *
 * Helps identify data gaps and query patterns that need better coverage.
 */

import React, { useEffect, useState, useCallback } from 'react';

interface InsufficientDataEntry {
  id: string;
  description: string;
  query: string;
  confidence: number;
  reason: string;
  persona: string;
  timestamp: string;
}

interface InsufficientDataStats {
  total_entries: number;
  avg_confidence: number;
  by_reason: Record<string, number>;
  by_persona: Record<string, number>;
  threshold: number;
  supabase_connected: boolean;
}

interface InsufficientDataPanelProps {
  /** Refresh interval in milliseconds (0 to disable auto-refresh) */
  refreshInterval?: number;
  /** Maximum entries to display */
  maxEntries?: number;
  /** Filter by persona */
  persona?: string;
  /** Whether the panel is in collapsed mode */
  collapsed?: boolean;
}

/**
 * Format a timestamp string to a human-readable relative time
 */
function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  return date.toLocaleDateString();
}

/**
 * Get color based on confidence level
 */
function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.7) return 'text-yellow-400';
  if (confidence >= 0.5) return 'text-orange-400';
  return 'text-red-400';
}

/**
 * Get background color based on confidence level
 */
function getConfidenceBgColor(confidence: number): string {
  if (confidence >= 0.7) return 'bg-yellow-400/10';
  if (confidence >= 0.5) return 'bg-orange-400/10';
  return 'bg-red-400/10';
}

/**
 * Get persona color
 */
function getPersonaColor(persona: string): string {
  const colors: Record<string, string> = {
    CFO: 'text-emerald-400',
    CRO: 'text-blue-400',
    COO: 'text-amber-400',
    CTO: 'text-purple-400',
    People: 'text-pink-400',
  };
  return colors[persona] || 'text-slate-400';
}

export const InsufficientDataPanel: React.FC<InsufficientDataPanelProps> = ({
  refreshInterval = 5000,
  maxEntries = 50,
  persona,
  collapsed = false,
}) => {
  const [entries, setEntries] = useState<InsufficientDataEntry[]>([]);
  const [stats, setStats] = useState<InsufficientDataStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const url = new URL('/api/v1/rag/insufficient-data/log', window.location.origin);
      url.searchParams.set('limit', maxEntries.toString());
      if (persona) {
        url.searchParams.set('persona', persona);
      }

      const response = await fetch(url.toString());
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setEntries(data.entries || []);
      setStats(data.stats || null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [maxEntries, persona]);

  // Initial load and refresh interval
  useEffect(() => {
    fetchData();

    if (refreshInterval > 0) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [fetchData, refreshInterval]);

  if (collapsed) {
    // Compact view showing just count
    return (
      <div className="flex items-center gap-2 px-3 py-2">
        <span className="text-amber-400 font-mono">!</span>
        <span className="text-slate-400 text-sm">
          {entries.length} low-confidence
        </span>
      </div>
    );
  }

  if (loading && entries.length === 0) {
    return (
      <div className="p-4 text-center">
        <div className="animate-pulse">
          <div className="h-4 w-32 bg-slate-700 rounded mx-auto mb-3" />
          <div className="h-3 w-48 bg-slate-800 rounded mx-auto" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header with warning indicator */}
      <div className="p-3 border-b border-slate-800 bg-amber-900/10">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-amber-400 text-lg">!</span>
          <span className="text-slate-200 font-medium text-sm">
            Insufficient Data Conditions
          </span>
        </div>
        <p className="text-slate-500 text-xs">
          Queries with &lt;70% confidence may indicate data gaps
        </p>
      </div>

      {/* Stats Summary */}
      {stats && stats.total_entries > 0 && (
        <div className="p-3 border-b border-slate-800 bg-slate-900/50">
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-semibold text-amber-400">
                {stats.total_entries}
              </div>
              <div className="text-[10px] text-slate-500 uppercase">Flagged</div>
            </div>
            <div>
              <div className="text-lg font-semibold text-orange-400">
                {Math.round(stats.avg_confidence * 100)}%
              </div>
              <div className="text-[10px] text-slate-500 uppercase">Avg Conf</div>
            </div>
            <div>
              <div className="text-lg font-semibold text-red-400">
                {Math.round(stats.threshold * 100)}%
              </div>
              <div className="text-[10px] text-slate-500 uppercase">Threshold</div>
            </div>
          </div>

          {/* Breakdown by reason */}
          {Object.keys(stats.by_reason).length > 0 && (
            <div className="mt-3 pt-3 border-t border-slate-800">
              <div className="text-[10px] text-slate-500 uppercase mb-2">By Reason</div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(stats.by_reason).slice(0, 4).map(([reason, count]) => (
                  <span
                    key={reason}
                    className="px-2 py-0.5 bg-slate-800 rounded text-[10px] text-slate-400"
                  >
                    {reason}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="px-3 py-2 bg-red-900/20 border-b border-red-800/50 text-red-400 text-xs">
          {error}
        </div>
      )}

      {/* Log Entries */}
      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-sm">
            <div className="mb-2 text-2xl text-emerald-400">+</div>
            <p>No insufficient data conditions</p>
            <p className="text-xs mt-1 text-slate-600">
              All queries are meeting the 80% confidence threshold
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/50">
            {entries.map((entry) => (
              <div
                key={entry.id}
                className={`p-3 hover:bg-slate-800/30 transition-colors ${getConfidenceBgColor(entry.confidence)}`}
              >
                <div className="flex items-start gap-2">
                  {/* Confidence Badge */}
                  <span
                    className={`${getConfidenceColor(entry.confidence)} font-mono text-sm w-10 flex-shrink-0`}
                  >
                    {Math.round(entry.confidence * 100)}%
                  </span>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    {/* Query */}
                    <p className="text-slate-300 text-sm leading-snug truncate">
                      "{entry.query}"
                    </p>

                    {/* Reason */}
                    <p className="text-slate-500 text-xs mt-1">
                      {entry.reason}
                    </p>

                    {/* Meta */}
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-slate-600 text-[10px]">
                        {formatRelativeTime(entry.timestamp)}
                      </span>
                      <span className={`${getPersonaColor(entry.persona)} text-[10px] font-medium`}>
                        {entry.persona}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer with connection status */}
      {stats && (
        <div className="p-2 border-t border-slate-800 bg-slate-900/30">
          <div className="flex items-center justify-center gap-2 text-[10px] text-slate-600">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                stats.supabase_connected ? 'bg-emerald-400' : 'bg-slate-500'
              }`}
            />
            <span>
              {stats.supabase_connected ? 'Supabase connected' : 'Memory only'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default InsufficientDataPanel;
