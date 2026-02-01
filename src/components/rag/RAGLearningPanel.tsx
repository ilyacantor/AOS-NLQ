/**
 * RAG Learning Panel Component
 *
 * Displays the RAG learning log in an elegant scrollable panel.
 * Shows what the system has learned with timestamps and status indicators.
 * Stats are cumulative across sessions (stored in localStorage).
 */

import React, { useEffect, useState, useCallback, useRef } from 'react';

// localStorage key for cumulative stats
const CUMULATIVE_STATS_KEY = 'aos_rag_cumulative_stats';
const SEEN_ENTRIES_KEY = 'aos_rag_seen_entries';

interface LearningLogEntry {
  id: string;
  description: string;
  success: boolean;
  source: string;
  learned: boolean;
  timestamp: string;
  persona: string;
}

interface LearningStats {
  total_queries: number;
  successful_queries: number;
  queries_learned: number;
  from_cache: number;
  from_llm: number;
  cache_hit_rate: number;
  learning_rate: number;
  supabase_connected: boolean;
}

interface CumulativeStats {
  total_queries: number;
  queries_learned: number;
  from_cache: number;
  from_llm: number;
  last_updated: string;
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
 * Load cumulative stats from localStorage
 */
function loadCumulativeStats(): CumulativeStats {
  try {
    const data = localStorage.getItem(CUMULATIVE_STATS_KEY);
    if (data) {
      return JSON.parse(data);
    }
  } catch (e) {
    console.warn('Failed to load cumulative stats:', e);
  }
  return {
    total_queries: 0,
    queries_learned: 0,
    from_cache: 0,
    from_llm: 0,
    last_updated: new Date().toISOString(),
  };
}

/**
 * Save cumulative stats to localStorage
 */
function saveCumulativeStats(stats: CumulativeStats): void {
  try {
    localStorage.setItem(CUMULATIVE_STATS_KEY, JSON.stringify(stats));
  } catch (e) {
    console.warn('Failed to save cumulative stats:', e);
  }
}

/**
 * Load seen entry IDs from localStorage
 */
function loadSeenEntries(): Set<string> {
  try {
    const data = localStorage.getItem(SEEN_ENTRIES_KEY);
    if (data) {
      return new Set(JSON.parse(data));
    }
  } catch (e) {
    console.warn('Failed to load seen entries:', e);
  }
  return new Set();
}

/**
 * Save seen entry IDs to localStorage (keep last 1000 to prevent unbounded growth)
 */
function saveSeenEntries(entries: Set<string>): void {
  try {
    const arr = Array.from(entries).slice(-1000);
    localStorage.setItem(SEEN_ENTRIES_KEY, JSON.stringify(arr));
  } catch (e) {
    console.warn('Failed to save seen entries:', e);
  }
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
  refreshInterval = 5000,
  maxEntries = 50,
  persona,
}) => {
  const [entries, setEntries] = useState<LearningLogEntry[]>([]);
  const [stats, setStats] = useState<LearningStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Use refs to track cumulative stats and seen entries across renders
  const cumulativeStatsRef = useRef<CumulativeStats>(loadCumulativeStats());
  const seenEntriesRef = useRef<Set<string>>(loadSeenEntries());

  const fetchData = useCallback(async () => {
    try {
      // Fetch ALL entries from DB to get accurate cumulative stats
      // Use a high limit to capture all historical data for seeding
      const url = new URL('/api/v1/rag/learning/log/db', window.location.origin);
      // Fetch more entries for accurate cumulative stats, but only display maxEntries
      url.searchParams.set('limit', '500');
      if (persona) {
        url.searchParams.set('persona', persona);
      }

      const response = await fetch(url.toString());
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      // DB endpoint returns entries in a different format - map to UI format
      const allDbEntries = (data.entries || []).map((e: any) => ({
        id: e.id,
        // Create description from query + context
        description: e.message || `"${e.query}" ${e.learned ? 'learned' : 'processed'}`,
        success: e.success,
        source: e.source,
        learned: e.learned,
        timestamp: e.created_at || e.timestamp,
        persona: e.persona,
        // Extra fields from DB
        similarity: e.similarity,
        llm_confidence: e.llm_confidence,
      }));

      // Only display the most recent maxEntries
      setEntries(allDbEntries.slice(0, maxEntries));

      // Check if we need to seed cumulative stats (first load or empty localStorage)
      const isFirstLoad = cumulativeStatsRef.current.total_queries === 0 && seenEntriesRef.current.size === 0;

      if (isFirstLoad && allDbEntries.length > 0) {
        // Seed cumulative stats from all existing DB entries
        for (const entry of allDbEntries) {
          seenEntriesRef.current.add(entry.id);
          cumulativeStatsRef.current.total_queries += 1;
          if (entry.learned) {
            cumulativeStatsRef.current.queries_learned += 1;
          }
          if (entry.source === 'cache') {
            cumulativeStatsRef.current.from_cache += 1;
          }
          if (entry.source === 'llm') {
            cumulativeStatsRef.current.from_llm += 1;
          }
        }
        cumulativeStatsRef.current.last_updated = new Date().toISOString();
        saveCumulativeStats(cumulativeStatsRef.current);
        saveSeenEntries(seenEntriesRef.current);
      } else {
        // Update cumulative stats with new entries we haven't seen before
        let statsUpdated = false;
        for (const entry of allDbEntries) {
          if (!seenEntriesRef.current.has(entry.id)) {
            // This is a new entry - add to cumulative stats
            seenEntriesRef.current.add(entry.id);
            cumulativeStatsRef.current.total_queries += 1;
            if (entry.learned) {
              cumulativeStatsRef.current.queries_learned += 1;
            }
            if (entry.source === 'cache') {
              cumulativeStatsRef.current.from_cache += 1;
            }
            if (entry.source === 'llm') {
              cumulativeStatsRef.current.from_llm += 1;
            }
            statsUpdated = true;
          }
        }

        // Save updated cumulative stats if changed
        if (statsUpdated) {
          cumulativeStatsRef.current.last_updated = new Date().toISOString();
          saveCumulativeStats(cumulativeStatsRef.current);
          saveSeenEntries(seenEntriesRef.current);
        }
      }

      // Use cumulative stats for display
      const cumStats = cumulativeStatsRef.current;
      const totalQueries = cumStats.total_queries;
      const fromCache = cumStats.from_cache;
      const queriesLearned = cumStats.queries_learned;

      setStats({
        total_queries: totalQueries,
        successful_queries: totalQueries, // Assume all counted are successful
        queries_learned: queriesLearned,
        from_cache: fromCache,
        from_llm: cumStats.from_llm,
        cache_hit_rate: totalQueries > 0 ? fromCache / totalQueries : 0,
        learning_rate: totalQueries > 0 ? queriesLearned / totalQueries : 0,
        supabase_connected: true,
      });
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
      {/* Stats Header - Cumulative (persists across sessions) */}
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
