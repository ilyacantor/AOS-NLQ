import React from 'react';
import { IntentNode } from './types';

interface DataTableProps {
  nodes: IntentNode[];
  title?: string;
}

export const DataTable: React.FC<DataTableProps> = ({ nodes, title }) => {
  if (!nodes || nodes.length === 0) return null;

  // Group nodes by domain for better organization
  const groupedNodes = nodes.reduce((acc, node) => {
    const domain = node.domain || 'other';
    if (!acc[domain]) acc[domain] = [];
    acc[domain].push(node);
    return acc;
  }, {} as Record<string, IntentNode[]>);

  return (
    <div className="data-table bg-slate-900/50 rounded-lg border border-slate-700/50 overflow-hidden">
      {title && (
        <div className="px-3 py-2 bg-slate-800/50 border-b border-slate-700/50">
          <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
            {title}
          </h4>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-800/30">
              <th className="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                Metric
              </th>
              <th className="px-3 py-2 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">
                Value
              </th>
              <th className="px-3 py-2 text-center text-xs font-medium text-slate-400 uppercase tracking-wider">
                Period
              </th>
              <th className="px-3 py-2 text-center text-xs font-medium text-slate-400 uppercase tracking-wider">
                Conf
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700/30">
            {Object.entries(groupedNodes).map(([domain, domainNodes]) => (
              <React.Fragment key={domain}>
                {domainNodes.length > 1 && Object.keys(groupedNodes).length > 1 && (
                  <tr className="bg-slate-800/20">
                    <td colSpan={4} className="px-3 py-1">
                      <span className="text-xs font-medium text-slate-500 capitalize">
                        {domain}
                      </span>
                    </td>
                  </tr>
                )}
                {domainNodes.map((node, idx) => (
                  <tr
                    key={node.id}
                    className={`
                      hover:bg-slate-800/30 transition-colors
                      ${node.match_type === 'exact' ? 'bg-emerald-900/10' : ''}
                    `}
                  >
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{
                            backgroundColor: node.match_type === 'exact'
                              ? '#10b981'
                              : node.match_type === 'potential'
                              ? '#f59e0b'
                              : '#6b7280'
                          }}
                        />
                        <span className="text-slate-300 truncate">
                          {node.semantic_label || node.display_name}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className="text-white font-medium">
                        {node.formatted_value || formatValue(node.value, node.unit)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className="text-slate-400 text-xs">
                        {node.period || '-'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className={`
                        text-xs font-medium px-1.5 py-0.5 rounded
                        ${node.confidence >= 0.9 ? 'bg-emerald-900/50 text-emerald-400' :
                          node.confidence >= 0.7 ? 'bg-amber-900/50 text-amber-400' :
                          'bg-slate-700/50 text-slate-400'}
                      `}>
                        {Math.round(node.confidence * 100)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

function formatValue(value: number | string | null | undefined, unit?: string): string {
  if (value === null || value === undefined) return '-';

  if (typeof value === 'number') {
    if (unit === '%') return `${value.toFixed(1)}%`;
    if (unit === '$M' || unit === 'USD_MILLIONS') return `$${value.toFixed(1)}M`;
    if (unit === '$' || unit === 'USD') return `$${value.toLocaleString()}`;
    return value.toLocaleString();
  }

  return String(value);
}
