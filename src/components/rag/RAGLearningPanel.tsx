/**
 * RAG Learning Panel Component
 *
 * Displays the RAG learning log in an elegant scrollable panel.
 * Shows what the system has learned with timestamps and status indicators.
 * Cumulative stats are sourced from Supabase (survives browser clears).
 */

import React, { useEffect, useState, useCallback } from 'react';

interface LearningLogEntry {
  id: string;
  description: string;
  success: boolean;
  source: string;
  learned: boolean;
  timestamp: string;
  persona: string;
}

interface CumulativeDbStats {
  total_queries: number;
  from_cache: number;
  from_llm: number;
  from_bypass: number;
  queries_learned: number;
  cache_hit_rate: number;
  learning_rate: number;
  supabase_connected: boolean;
}

interface RAGLearningPanelProps {
  /** Refresh interval in milliseconds (0 to disable auto-refresh) */
  refreshInterval?: number;
  /** Maximum entries to display */
  maxEntries?: number;
  /** Filter by persona */
  persona?: string;
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
 * Get icon and color for a log entry based on source and success
 */
function getEntryStyle(entry: LearningLogEntry): { icon: string; color: string; bgColor: string } {
  if (!entry.success) {
    return { icon: '!', color: 'text-red-400', bgColor: 'bg-red-400/10' };
  }
  if (entry.learned) {
    return { icon: '+', color: 'text-emerald-400', bgColor: 'bg-emerald-400/10' };
  }
  if (entry.source === 'cache') {
    return { icon: '>', color: 'text-cyan-400', bgColor: 'bg-cyan-400/10' };
  }
  if (entry.source === 'llm') {
    return { icon: '*', color: 'text-purple-400', bgColor: 'bg-purple-400/10' };
  }
  return { icon: '-', color: 'text-slate-400', bgColor: 'bg-slate-400/10' };
}

export const RAGLearningPanel: React.FC<RAGLearningPanelProps> = ({
  refreshInterval = 0,
  maxEntries = 50,
  persona,
}) => {
  const [entries, setEntries] = useState<LearningLogEntry[]>([]);
  const [stats, setStats] = useState<CumulativeDbStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      // Fetch log entries from DB
      const entriesUrl = new URL('/api/v1/rag/learning/log/db', window.location.origin);
      entriesUrl.searchParams.set('limit', String(maxEntries));
      if (persona) {
        entriesUrl.searchParams.set('persona', persona);
      }

      // Fetch cumulative stats from DB (replaces localStorage accumulation)
      const [entriesRes, statsRes] = await Promise.all([
        fetch(entriesUrl.toString()),
        fetch('/api/v1/rag/learning/stats/db'),
      ]);

      // Process entries
      if (!entriesRes.ok) {
        throw new Error(`Entries: HTTP ${entriesRes.status}`);
      }
      const entriesData = await entriesRes.json();
      const allDbEntries = (entriesData.entries || []).map((e: any) => ({
        id: e.id,
        description: e.message || `"${e.query}" ${e.learned ? 'learned' : 'processed'}`,
        success: e.success,
        source: e.source,
        learned: e.learned,
        timestamp: e.created_at || e.timestamp,
        persona: e.persona,
      }));
      setEntries(allDbEntries.slice(0, maxEntries));

      // Process cumulative stats
      if (statsRes.ok) {
        const statsData: CumulativeDbStats = await statsRes.json();
        setStats(statsData);
      } else if (statsRes.status === 503) {
        // Supabase unavailable — show what we have from entries
        setStats(null);
        setError('Stats unavailable (Supabase down)');
      }

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
      {/* Stats Header - Cumulative from DB (persists across browser clears) */}
      {stats && (
        <div className="p-3 border-b border-slate-800 bg-slate-900/50">
          <div className="text-[9px] text-slate-600 uppercase tracking-wider text-center mb-2">
            Cumulative Stats (All Time)
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-semibold text-cyan-400">
                {Math.round(stats.cache_hit_rate * 100)}%
              </div>
              <div className="text-[10px] text-slate-500 uppercase">Cache Hit</div>
            </div>
            <div>
              <div className="text-lg font-semibold text-emerald-400">
                {stats.queries_learned}
              </div>
              <div className="text-[10px] text-slate-500 uppercase">Learned</div>
            </div>
            <div>
              <div className="text-lg font-semibold text-purple-400">
                {stats.from_llm}
              </div>
              <div className="text-[10px] text-slate-500 uppercase">AI Calls</div>
            </div>
          </div>
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
            <div className="mb-2 text-2xl">~</div>
            <p>No learning activity yet</p>
            <p className="text-xs mt-1 text-slate-600">
              Ask questions to start learning
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/50">
            {entries.map((entry) => {
              const style = getEntryStyle(entry);
              return (
                <div
                  key={entry.id}
                  className={`p-3 hover:bg-slate-800/30 transition-colors ${style.bgColor}`}
                >
                  <div className="flex items-start gap-2">
                    {/* Status Icon */}
                    <span className={`${style.color} font-mono text-sm w-4 flex-shrink-0`}>
                      {style.icon}
                    </span>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <p className="text-slate-300 text-sm leading-snug">
                        {entry.description}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-slate-600 text-[10px]">
                          {formatRelativeTime(entry.timestamp)}
                        </span>
                        {entry.learned && (
                          <span className="text-emerald-400/70 text-[10px] font-medium">
                            LEARNED
                          </span>
                        )}
                        {entry.source === 'cache' && entry.success && (
                          <span className="text-cyan-400/70 text-[10px] font-medium">
                            CACHED
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
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

export default RAGLearningPanel;
