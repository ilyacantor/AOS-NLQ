import React from 'react';
import { IntentNode, DOMAIN_COLORS, getFreshnessColor } from './types';

interface NodeTooltipProps {
  node: IntentNode;
  isPrimary: boolean;
  x: number;
  y: number;
  svgWidth: number;
  svgHeight: number;
}

export const NodeTooltip: React.FC<NodeTooltipProps> = ({
  node,
  isPrimary,
  x,
  y,
  svgWidth,
  svgHeight,
}) => {
  const tooltipWidth = 280;
  const tooltipHeight = 240;

  // Position tooltip to avoid overflow
  let tooltipX = x + 20;
  let tooltipY = y - tooltipHeight / 2;

  // Adjust if tooltip would go off right edge
  if (tooltipX + tooltipWidth > svgWidth - 20) {
    tooltipX = x - tooltipWidth - 20;
  }

  // Adjust if tooltip would go off top
  if (tooltipY < 20) {
    tooltipY = 20;
  }

  // Adjust if tooltip would go off bottom
  if (tooltipY + tooltipHeight > svgHeight - 20) {
    tooltipY = svgHeight - tooltipHeight - 20;
  }

  const domainColor = DOMAIN_COLORS[node.domain] || DOMAIN_COLORS.finance;
  const freshnessColor = getFreshnessColor(node.freshness);

  // Get freshness label
  const getFreshnessLabel = (freshness: string): string => {
    if (freshness === 'N/A') return 'N/A';
    return freshness;
  };

  // Sample dimensions based on metric type
  const getDimensions = (metric: string): string[] => {
    const dimensionMap: Record<string, string[]> = {
      revenue: ['Time', 'Region', 'Product'],
      net_income: ['Time', 'Business Unit'],
      bookings: ['Subscription', 'Customer', 'Plan'],
      gross_margin_pct: ['Time', 'Product'],
      operating_margin_pct: ['Time'],
      cash: ['Account', 'Currency'],
      ar: ['Customer', 'Age'],
      default: ['Time'],
    };
    return dimensionMap[metric] || dimensionMap.default;
  };

  // Get logic type based on metric
  const getLogicType = (metric: string): string => {
    if (metric.includes('pct') || metric.includes('margin')) return 'AVG';
    if (metric.includes('growth') || metric.includes('change')) return 'DELTA';
    return 'SUM';
  };

  return (
    <g transform={`translate(${tooltipX}, ${tooltipY})`} className="node-tooltip">
      {/* Background with border */}
      <rect
        width={tooltipWidth}
        height={tooltipHeight}
        rx={8}
        fill="#1e293b"
        stroke="#334155"
        strokeWidth={1}
        filter="drop-shadow(0 4px 12px rgba(0,0,0,0.5))"
      />

      {/* Header section */}
      <g transform="translate(16, 16)">
        {/* Title row */}
        <text fill="#fff" fontSize="14" fontWeight="600">
          {node.display_name}
        </text>
        {isPrimary && (
          <g transform={`translate(${node.display_name.length * 7 + 10}, -3)`}>
            <rect width={56} height={18} rx={4} fill="#22c55e" opacity={0.2} />
            <text x={8} y={13} fill="#22c55e" fontSize="10" fontWeight="600">
              PRIMARY
            </text>
          </g>
        )}

        {/* Metric code */}
        <text y={20} fill="#64748b" fontSize="11">
          {node.metric}
        </text>

        {/* Divider */}
        <line x1={0} y1={32} x2={tooltipWidth - 32} y2={32} stroke="#334155" />

        {/* Value/description */}
        <rect y={40} width={tooltipWidth - 32} height={36} rx={4} fill="#0f172a" />
        <text y={62} x={8} fill="#94a3b8" fontSize="12">
          {node.formatted_value
            ? `Value: ${node.formatted_value}`
            : node.rationale || 'Financial metric'}
        </text>

        {/* Stats row */}
        <g transform="translate(0, 88)">
          {/* Confidence */}
          <text fill="#64748b" fontSize="10">Confidence</text>
          <text y={14} fill="#3b82f6" fontSize="13" fontWeight="600">
            {Math.round(node.confidence * 100)}%
          </text>

          {/* Data Quality */}
          <g transform={`translate(${(tooltipWidth - 32) / 2}, 0)`}>
            <text fill="#64748b" fontSize="10">Data Quality</text>
            <text y={14} fill="#22c55e" fontSize="13" fontWeight="600">
              {Math.round(node.data_quality * 100)}%
            </text>
          </g>
        </g>

        {/* Freshness & Cluster row */}
        <g transform="translate(0, 124)">
          {/* Freshness */}
          <text fill="#64748b" fontSize="10">Freshness</text>
          <g transform="translate(0, 14)">
            <circle r={4} cx={4} cy={0} fill={freshnessColor} />
            <text x={12} fill="#fff" fontSize="11" dy="0.35em">
              {getFreshnessLabel(node.freshness)}
            </text>
          </g>

          {/* Cluster/Domain */}
          <g transform={`translate(${(tooltipWidth - 32) / 2}, 0)`}>
            <text fill="#64748b" fontSize="10">Cluster</text>
            <g transform="translate(0, 14)">
              <circle r={4} cx={4} cy={0} fill={domainColor} />
              <text x={12} fill="#fff" fontSize="11" dy="0.35em" className="capitalize">
                {node.domain.charAt(0).toUpperCase() + node.domain.slice(1)}
              </text>
            </g>
          </g>
        </g>

        {/* Divider */}
        <line x1={0} y1={156} x2={tooltipWidth - 32} y2={156} stroke="#334155" />

        {/* Dimensions */}
        <g transform="translate(0, 166)">
          <text fill="#64748b" fontSize="10">DIMENSIONS</text>
          <g transform="translate(0, 16)">
            {getDimensions(node.metric).map((dim, i) => (
              <g key={dim} transform={`translate(${i * 70}, 0)`}>
                <rect
                  width={60}
                  height={20}
                  rx={4}
                  fill="rgba(59, 130, 246, 0.15)"
                  stroke="rgba(59, 130, 246, 0.3)"
                />
                <text x={30} y={14} fill="#3b82f6" fontSize="10" textAnchor="middle">
                  {dim}
                </text>
              </g>
            ))}
          </g>
        </g>

        {/* Logic & Event row */}
        <g transform="translate(0, 200)">
          <text fill="#64748b" fontSize="10">LOGIC</text>
          <text x={45} fill="#fff" fontSize="11" fontWeight="500">
            {getLogicType(node.metric)}
          </text>
        </g>
      </g>
    </g>
  );
};
