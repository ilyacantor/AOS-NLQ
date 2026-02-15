import React, { useState } from 'react';
import type { RunProvenance } from './types';

interface ProvenanceBadgeProps {
  provenance?: RunProvenance | null;
  compact?: boolean;
}

/**
 * Trust Badge showing data provenance from DCL ingestion pipeline.
 *
 * Displays a small "Verified" / "Local" indicator next to query results.
 * On hover/click, expands to show run details:
 *   - Data Source (source systems)
 *   - Run ID
 *   - Extraction timestamp
 *   - Snapshot/tenant name
 */
export const ProvenanceBadge: React.FC<ProvenanceBadgeProps> = ({
  provenance,
  compact = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  const isVerified = provenance?.run_id != null;
  const hasSourceSystems = provenance?.source_systems && provenance.source_systems.length > 0;

  // Format timestamp to PST for display
  const formatTimestamp = (iso: string | null | undefined): string => {
    if (!iso) return '';
    try {
      const date = new Date(iso);
      return date.toLocaleString('en-US', {
        timeZone: 'America/Los_Angeles',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZoneName: 'short',
      });
    } catch {
      return iso;
    }
  };

  if (compact) {
    // Inline badge for the answer header area
    return (
      <span
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium cursor-default ${
          isVerified
            ? 'bg-emerald-900/30 text-emerald-400 border border-emerald-800/40'
            : 'bg-slate-800/50 text-slate-500 border border-slate-700/40'
        }`}
        title={
          isVerified
            ? `DCL Run: ${provenance?.run_id}\nSource: ${provenance?.source_systems?.join(', ') || 'N/A'}`
            : 'Local dev data (fact_base.json)'
        }
      >
        {isVerified ? (
          <>
            <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
            DCL
          </>
        ) : (
          <>
            <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            Local
          </>
        )}
      </span>
    );
  }

  // Full badge with expandable detail (for NodeDetailPanel)
  return (
    <div className="mt-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-colors ${
          isVerified
            ? 'bg-emerald-900/20 border border-emerald-800/30 hover:bg-emerald-900/30'
            : 'bg-slate-800/30 border border-slate-700/30 hover:bg-slate-800/50'
        }`}
      >
        <div className="flex items-center gap-2">
          {isVerified ? (
            <svg className="w-3.5 h-3.5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5 text-slate-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
          )}
          <span className={isVerified ? 'text-emerald-400 font-medium' : 'text-slate-500'}>
            {isVerified ? 'Verified (DCL)' : 'Local Data'}
          </span>
        </div>
        <svg
          className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''} ${
            isVerified ? 'text-emerald-500' : 'text-slate-600'
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="mt-1 px-3 py-2 bg-slate-800/30 rounded-lg border border-slate-700/20 space-y-2 text-xs">
          {isVerified ? (
            <>
              {hasSourceSystems && (
                <div>
                  <span className="text-slate-500">Source: </span>
                  <span className="text-slate-300">{provenance!.source_systems!.join(', ')}</span>
                </div>
              )}
              <div>
                <span className="text-slate-500">Run ID: </span>
                <span className="text-slate-400 font-mono">{provenance!.run_id}</span>
              </div>
              {provenance?.run_timestamp && (
                <div>
                  <span className="text-slate-500">Extracted: </span>
                  <span className="text-slate-300">{formatTimestamp(provenance.run_timestamp)}</span>
                </div>
              )}
              {provenance?.snapshot_name && (
                <div>
                  <span className="text-slate-500">Snapshot: </span>
                  <span className="text-slate-300">{provenance.snapshot_name}</span>
                </div>
              )}
              {provenance?.tenant_id && (
                <div>
                  <span className="text-slate-500">Tenant: </span>
                  <span className="text-slate-300">{provenance.tenant_id}</span>
                </div>
              )}
              {provenance?.freshness && (
                <div>
                  <span className="text-slate-500">Freshness: </span>
                  <span className="text-emerald-400">{provenance.freshness} ago</span>
                </div>
              )}
            </>
          ) : (
            <div className="text-slate-500">
              Using local fact_base.json. Set DCL_API_URL to connect to live DCL.
            </div>
          )}
        </div>
      )}
    </div>
  );
};
