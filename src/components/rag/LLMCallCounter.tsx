/**
 * LLM Call Counter Component
 *
 * Displays the number of LLM API calls made during the current browser session.
 * Refreshes on-demand after queries complete (no polling).
 */

import React, { useEffect, useState, useCallback } from 'react';

interface SessionStats {
  session_id: string;
  llm_calls: number;
  cached_queries: number;
  learned_queries: number;
  first_call_at: string | null;
  last_call_at: string | null;
}

interface LLMCallCounterProps {
  detailed?: boolean;
  className?: string;
}

/**
 * Generate or retrieve a persistent session ID
 */
function getSessionId(): string {
  const key = 'aos_nlq_session_id';
  let sessionId = sessionStorage.getItem(key);

  if (!sessionId) {
    sessionId = `ses_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    sessionStorage.setItem(key, sessionId);
  }

  return sessionId;
}

/**
 * Notify all LLMCallCounter instances to refresh stats.
 * Call this after any query/API call completes.
 */
export function refreshLLMStats() {
  window.dispatchEvent(new CustomEvent('llm-stats-refresh'));
}

export const LLMCallCounter: React.FC<LLMCallCounterProps> = ({
  detailed = false,
  className = '',
}) => {
  const [stats, setStats] = useState<SessionStats | null>(null);
  const [sessionId] = useState(getSessionId);

  const fetchStats = useCallback(async () => {
    try {
      const url = new URL('/api/v1/rag/session/stats', window.location.origin);
      url.searchParams.set('session_id', sessionId);

      const response = await fetch(url.toString());
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (err) {
      console.debug('Failed to fetch LLM call stats:', err);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchStats();

    const handler = () => fetchStats();
    window.addEventListener('llm-stats-refresh', handler);
    return () => window.removeEventListener('llm-stats-refresh', handler);
  }, [fetchStats]);

  if (!stats) {
    return null;
  }

  const { llm_calls, cached_queries, learned_queries } = stats;

  if (detailed) {
    return (
      <div className={`flex items-center gap-4 text-xs ${className}`}>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-purple-400" />
          <span className="text-slate-400">AI Calls:</span>
          <span className="text-purple-400 font-mono font-medium">{llm_calls}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-cyan-400" />
          <span className="text-slate-400">Cached:</span>
          <span className="text-cyan-400 font-mono font-medium">{cached_queries}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-emerald-400" />
          <span className="text-slate-400">Learned:</span>
          <span className="text-emerald-400 font-mono font-medium">{learned_queries}</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`flex items-center gap-2 px-3 py-1.5 bg-slate-800/50 rounded-lg ${className}`}
      title={`${llm_calls} AI calls | ${cached_queries} cached | ${learned_queries} learned`}
    >
      <svg
        className="w-4 h-4 text-purple-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
        />
      </svg>
      <span className="text-sm">
        <span className="text-purple-400 font-mono font-medium">{llm_calls}</span>
        <span className="text-slate-500 ml-1">AI</span>
      </span>
      {cached_queries > 0 && (
        <>
          <span className="text-slate-600">|</span>
          <span className="text-sm">
            <span className="text-cyan-400 font-mono font-medium">{cached_queries}</span>
            <span className="text-slate-500 ml-1">cache</span>
          </span>
        </>
      )}
    </div>
  );
};

/**
 * Hook to get the session ID for API calls
 */
export function useSessionId(): string {
  return getSessionId();
}

export default LLMCallCounter;
