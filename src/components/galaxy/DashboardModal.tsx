import React from 'react';
import { IntentNode, DOMAIN_COLORS, Domain } from './types';

interface DashboardModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  textResponse: string;
  nodes: IntentNode[];
}

export const DashboardModal: React.FC<DashboardModalProps> = ({
  isOpen,
  onClose,
  title,
  textResponse,
  nodes,
}) => {
  if (!isOpen) return null;

  // Group nodes by domain for the visual display
  const nodesByDomain = nodes.reduce((acc, node) => {
    const domain = node.domain as Domain;
    if (!acc[domain]) acc[domain] = [];
    acc[domain].push(node);
    return acc;
  }, {} as Record<Domain, IntentNode[]>);

  const domainLabels: Record<Domain, string> = {
    finance: 'CFO',
    growth: 'CRO',
    ops: 'COO',
    product: 'CTO',
    people: 'People',
  };

  // Parse markdown table from text response
  const lines = textResponse.split('\n');
  const tableLines = lines.filter(l => l.startsWith('|'));
  const hasTable = tableLines.length > 2;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <h2 className="text-xl font-semibold text-white">{title}</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors p-1"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-auto max-h-[calc(90vh-80px)]">
          {hasTable ? (
            // Render as proper HTML table
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    {tableLines[0].split('|').filter(c => c.trim()).map((cell, i) => (
                      <th key={i} className="px-4 py-3 text-left text-slate-400 font-medium">
                        {cell.trim()}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tableLines.slice(2).map((row, rowIdx) => {
                    const cells = row.split('|').filter(c => c.trim());
                    const isPersonaRow = cells[0]?.includes('**');
                    return (
                      <tr
                        key={rowIdx}
                        className={`border-b border-slate-800 ${isPersonaRow ? 'bg-slate-800/30' : ''}`}
                      >
                        {cells.map((cell, cellIdx) => {
                          const content = cell.trim().replace(/\*\*/g, '');
                          const isChange = cellIdx === cells.length - 1;
                          const isPositive = content.startsWith('+');
                          const isNeutral = content === '0.0pp' || content === '0%';

                          return (
                            <td
                              key={cellIdx}
                              className={`px-4 py-3 ${
                                cellIdx === 0 && isPersonaRow
                                  ? 'font-semibold text-white'
                                  : isChange
                                    ? isPositive
                                      ? 'text-emerald-400 font-medium'
                                      : isNeutral
                                        ? 'text-slate-400'
                                        : 'text-red-400 font-medium'
                                    : 'text-slate-300'
                              }`}
                            >
                              {content}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            // Fallback to text display
            <pre className="text-slate-300 whitespace-pre-wrap font-sans text-sm leading-relaxed">
              {textResponse}
            </pre>
          )}

          {/* Domain color legend */}
          <div className="mt-6 pt-4 border-t border-slate-700">
            <div className="flex flex-wrap gap-4 justify-center">
              {Object.entries(nodesByDomain).map(([domain, domainNodes]) => (
                <div key={domain} className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: DOMAIN_COLORS[domain as Domain] }}
                  />
                  <span className="text-slate-400 text-sm">
                    {domainLabels[domain as Domain]} ({domainNodes.length} metrics)
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
