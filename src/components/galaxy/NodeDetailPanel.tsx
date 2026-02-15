import React from 'react';
import { IntentNode, RunProvenance, DOMAIN_COLORS, getFreshnessColor } from './types';
import { ProvenanceBadge } from './ProvenanceBadge';

interface NodeDetailPanelProps {
  node: IntentNode;
  isPrimary: boolean;
  onClose: () => void;
  provenance?: RunProvenance | null;
}

export const NodeDetailPanel: React.FC<NodeDetailPanelProps> = ({
  node,
  isPrimary,
  onClose,
  provenance,
}) => {
  const domainColor = DOMAIN_COLORS[node.domain] || DOMAIN_COLORS.finance;
  const freshnessColor = getFreshnessColor(node.freshness);

  // Determine freshness label
  const getFreshnessLabel = (freshness: string): string => {
    if (freshness === 'N/A') return 'N/A';
    const hours = parseInt(freshness.replace('h', '')) || 999;
    if (hours <= 6) return 'Fresh';
    if (hours <= 24) return 'Stale';
    return 'Old';
  };

  // Match type to ring name
  const ringName = {
    exact: 'Inner Ring (Exact)',
    potential: 'Middle Ring (Potential)',
    hypothesis: 'Outer Ring (Hypothesis)',
  }[node.match_type];

  return (
    <div className="w-80 border-l border-slate-800 bg-slate-900/80 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: domainColor }}
          />
          <h3 className="text-white font-semibold">{node.display_name}</h3>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* Primary badge */}
        {isPrimary && (
          <div className="mb-4">
            <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs font-medium rounded">
              Primary Answer
            </span>
          </div>
        )}

        {/* Value display */}
        <div className="mb-6 p-4 bg-slate-800/50 rounded-lg">
          <div className="text-slate-500 text-xs mb-1">Value</div>
          <div className="text-2xl font-bold text-white">
            {node.formatted_value || (node.value !== null ? String(node.value) : 'N/A')}
          </div>
          {node.period && (
            <div className="text-slate-400 text-sm mt-1">{node.period}</div>
          )}
        </div>

        {/* Metrics grid */}
        <dl className="space-y-4">
          {/* Confidence */}
          <div>
            <dt className="text-slate-500 text-xs mb-1">Confidence</dt>
            <dd className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all"
                  style={{ width: `${node.confidence * 100}%` }}
                />
              </div>
              <span className="text-white font-medium text-sm w-12 text-right">
                {Math.round(node.confidence * 100)}%
              </span>
            </dd>
          </div>

          {/* Data Quality */}
          <div>
            <dt className="text-slate-500 text-xs mb-1">Data Quality</dt>
            <dd className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full transition-all"
                  style={{ width: `${node.data_quality * 100}%` }}
                />
              </div>
              <span className="text-white font-medium text-sm w-12 text-right">
                {Math.round(node.data_quality * 100)}%
              </span>
            </dd>
          </div>

          {/* Freshness */}
          <div>
            <dt className="text-slate-500 text-xs mb-1">Freshness</dt>
            <dd className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: freshnessColor }}
              />
              <span className="text-white">
                {node.freshness} ({getFreshnessLabel(node.freshness)})
              </span>
            </dd>
          </div>

          {/* Match Type / Ring */}
          <div>
            <dt className="text-slate-500 text-xs mb-1">Ring Position</dt>
            <dd className="text-white">{ringName}</dd>
          </div>

          {/* Semantic Label */}
          {node.semantic_label && (
            <div>
              <dt className="text-slate-500 text-xs mb-1">Classification</dt>
              <dd className="text-white">{node.semantic_label}</dd>
            </div>
          )}

          {/* Domain */}
          <div>
            <dt className="text-slate-500 text-xs mb-1">Domain</dt>
            <dd className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: domainColor }}
              />
              <span className="text-white capitalize">{node.domain}</span>
            </dd>
          </div>

          {/* Metric ID */}
          <div>
            <dt className="text-slate-500 text-xs mb-1">Metric</dt>
            <dd className="text-slate-300 font-mono text-sm">{node.metric}</dd>
          </div>

          {/* Rationale */}
          {node.rationale && (
            <div>
              <dt className="text-slate-500 text-xs mb-1">Rationale</dt>
              <dd className="text-slate-300 text-sm">{node.rationale}</dd>
            </div>
          )}

          {/* Source System */}
          {node.source_system && (
            <div>
              <dt className="text-slate-500 text-xs mb-1">Source</dt>
              <dd className="text-slate-300 text-sm">{node.source_system}</dd>
            </div>
          )}
        </dl>

        {/* Data Provenance (Trust Badge) */}
        <ProvenanceBadge provenance={provenance} />
      </div>
    </div>
  );
};
