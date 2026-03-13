import React, { useState } from 'react';
import type { RunProvenance } from './types';

interface ProvenanceBadgeProps {
  provenance?: RunProvenance | null;
  compact?: boolean;
}

/**
 * Trust Badge showing data provenance from DCL ingestion pipeline.
 *
 * Three states based on metadata.mode:
 *   - Verified (green): mode == "Ingest" or "Live" — live Runner data with run_id
 *   - Run (blue): mode == "Demo" or "Farm" — graph-build / test oracle data
 *   - Local (grey): mode missing or null — local fact_base.json fallback
 *
 * Compact mode: inline badge next to answer header.
 * Full mode: expandable accordion in NodeDetailPanel with drill-down to run_id.
 */
export const ProvenanceBadge: React.FC<ProvenanceBadgeProps> = ({
  provenance,
  compact = false,
}) => {
  const [expanded, setExpanded] = useState(false);

  // Determine badge state from mode + run_id
  const mode = provenance?.mode?.toLowerCase() ?? null;
  const isVerified = mode === 'ingest' || mode === 'live';
  const isRun = mode === 'demo' || mode === 'farm';
  const isLocal = !isVerified && !isRun;
  const hasSourceSystems = provenance?.source_systems && provenance.source_systems.length > 0;

  // Format ISO timestamp to relative "Updated X mins ago"
  const formatRelativeTime = (iso: string | null | undefined): string => {
    if (!iso) return '';
    try {
      const then = new Date(iso).getTime();
      const now = Date.now();
      const diffMs = now - then;
      if (diffMs < 0) return 'just now';
      const mins = Math.floor(diffMs / 60000);
      if (mins < 1) return 'Updated just now';
      if (mins < 60) return `Updated ${mins}m ago`;
      const hours = Math.floor(mins / 60);
      if (hours < 24) return `Updated ${hours}h ago`;
      const days = Math.floor(hours / 24);
      return `Updated ${days}d ago`;
    } catch {
      return '';
    }
  };

  // Format timestamp to PST for expanded detail
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

  // Freshness display: prefer run_timestamp for relative, fall back to freshness field
  const freshnessDisplay = provenance?.run_timestamp
    ? formatRelativeTime(provenance.run_timestamp)
    : provenance?.freshness
      ? `Updated ${provenance.freshness} ago`
      : '';

  // Badge styling per state
  const badgeConfig = isVerified
    ? {
        compactClass: 'bg-emerald-900/30 text-emerald-400 border border-emerald-800/40',
        fullClass: 'bg-emerald-900/20 border border-emerald-800/30 hover:bg-emerald-900/30',
        labelClass: 'text-emerald-400 font-medium',
        chevronClass: 'text-emerald-500',
        label: 'Verified',
        compactLabel: 'Verified',
        tooltip: `Data Verified from Run ${provenance?.run_id ?? 'N/A'}`,
      }
    : isRun
      ? {
          compactClass: 'bg-blue-900/30 text-blue-400 border border-blue-800/40',
          fullClass: 'bg-blue-900/20 border border-blue-800/30 hover:bg-blue-900/30',
          labelClass: 'text-blue-400 font-medium',
          chevronClass: 'text-blue-500',
          label: 'Simulation',
          compactLabel: 'Simulation',
          tooltip: 'Sourced from Graph Build',
        }
      : {
          compactClass: 'bg-slate-800/50 text-slate-500 border border-slate-700/40',
          fullClass: 'bg-slate-800/30 border border-slate-700/30 hover:bg-slate-800/50',
          labelClass: 'text-slate-500',
          chevronClass: 'text-slate-600',
          label: 'Local Data',
          compactLabel: 'Local',
          tooltip: 'Local dev data (fact_base.json)',
        };

  if (compact) {
    // Inline badge for the answer header area
    return (
      <span className="inline-flex items-center gap-1.5">
        <span
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium cursor-default ${badgeConfig.compactClass}`}
          title={badgeConfig.tooltip}
        >
          {isVerified ? (
            <>
              <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              {badgeConfig.compactLabel}
            </>
          ) : isRun ? (
            <>
              <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clipRule="evenodd" />
              </svg>
              {badgeConfig.compactLabel}
            </>
          ) : (
            <>
              <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
              {badgeConfig.compactLabel}
            </>
          )}
        </span>
        {freshnessDisplay && (
          <span className="text-[10px] text-slate-500">{freshnessDisplay}</span>
        )}
      </span>
    );
  }

  // Full badge with expandable detail (for NodeDetailPanel)
  return (
    <div className="mt-4">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-colors ${badgeConfig.fullClass}`}
      >
        <div className="flex items-center gap-2">
          {isVerified ? (
            <svg className="w-3.5 h-3.5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
          ) : isRun ? (
            <svg className="w-3.5 h-3.5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clipRule="evenodd" />
            </svg>
          ) : (
            <svg className="w-3.5 h-3.5 text-slate-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
          )}
          <span className={badgeConfig.labelClass}>{badgeConfig.label}</span>
          {freshnessDisplay && (
            <span className="text-slate-500 ml-1">{freshnessDisplay}</span>
          )}
        </div>
        <svg
          className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''} ${badgeConfig.chevronClass}`}
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
            </>
          ) : isRun ? (
            <div className="text-blue-400/80">
              Sourced from Graph Build ({provenance?.mode ?? 'Demo'} mode).
              {provenance?.quality_score != null && (
                <span className="ml-1">Quality: {Math.round(provenance.quality_score * 100)}%</span>
              )}
            </div>
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
