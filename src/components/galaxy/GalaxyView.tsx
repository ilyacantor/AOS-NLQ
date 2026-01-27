import React, { useMemo, useState } from 'react';
import {
  IntentMapResponse,
  IntentNode,
  RING_CONFIG,
  DOMAIN_COLORS,
  getCircleRadius,
  getArcPath,
  getFreshnessColor,
} from './types';
import { GalaxyHeader } from './GalaxyHeader';
import { GalaxyLegend } from './GalaxyLegend';
import { NodeDetailPanel } from './NodeDetailPanel';

interface GalaxyViewProps {
  data: IntentMapResponse;
  width?: number;
  height?: number;
}

export const GalaxyView: React.FC<GalaxyViewProps> = ({
  data,
  width = 700,
  height = 700,
}) => {
  const [selectedNode, setSelectedNode] = useState<IntentNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const centerX = width / 2;
  const centerY = height / 2;

  // Group nodes by ring (match_type)
  const nodesByRing = useMemo(() => {
    const inner = data.nodes.filter(n => n.match_type === 'exact');
    const middle = data.nodes.filter(n => n.match_type === 'potential');
    const outer = data.nodes.filter(n => n.match_type === 'hypothesis');
    return { inner, middle, outer };
  }, [data.nodes]);

  // Calculate positions for all nodes
  const nodePositions = useMemo(() => {
    const positions = new Map<string, { x: number; y: number }>();

    const placeNodesOnRing = (nodes: IntentNode[], radius: number) => {
      if (nodes.length === 0) return;

      const angleStep = (2 * Math.PI) / nodes.length;
      const startAngle = -Math.PI / 2; // Start from top

      nodes.forEach((node, i) => {
        const angle = startAngle + angleStep * i;
        positions.set(node.id, {
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle),
        });
      });
    };

    placeNodesOnRing(nodesByRing.inner, RING_CONFIG.inner.radius);
    placeNodesOnRing(nodesByRing.middle, RING_CONFIG.middle.radius);
    placeNodesOnRing(nodesByRing.outer, RING_CONFIG.outer.radius);

    return positions;
  }, [nodesByRing, centerX, centerY]);

  const handleNodeClick = (node: IntentNode) => {
    setSelectedNode(prev => prev?.id === node.id ? null : node);
  };

  return (
    <div className="galaxy-container flex flex-col h-full bg-slate-950">
      {/* Header */}
      <GalaxyHeader
        confidence={data.overall_confidence}
        dataQuality={data.overall_data_quality}
        nodeCount={data.node_count}
        query={data.query}
      />

      {/* Main content area */}
      <div className="flex-1 flex">
        {/* SVG Visualization */}
        <div className="flex-1 flex items-center justify-center p-4">
          <svg
            width={width}
            height={height}
            className="galaxy-svg"
            style={{ filter: 'drop-shadow(0 0 20px rgba(59, 130, 246, 0.15))' }}
          >
            {/* Background gradient */}
            <defs>
              <radialGradient id="bgGradient" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#0f172a" />
                <stop offset="100%" stopColor="#020617" />
              </radialGradient>
            </defs>
            <rect width={width} height={height} fill="url(#bgGradient)" />

            {/* Orbital Rings */}
            <circle
              cx={centerX}
              cy={centerY}
              r={RING_CONFIG.outer.radius}
              fill="none"
              stroke={RING_CONFIG.outer.strokeColor}
              strokeWidth="1"
              strokeDasharray="4 4"
            />
            <circle
              cx={centerX}
              cy={centerY}
              r={RING_CONFIG.middle.radius}
              fill="none"
              stroke={RING_CONFIG.middle.strokeColor}
              strokeWidth="1"
              strokeDasharray="4 4"
            />
            <circle
              cx={centerX}
              cy={centerY}
              r={RING_CONFIG.inner.radius}
              fill="none"
              stroke={RING_CONFIG.inner.strokeColor}
              strokeWidth="2"
            />

            {/* Ring Labels */}
            <text
              x={centerX}
              y={centerY - RING_CONFIG.inner.radius - 8}
              textAnchor="middle"
              fill="#64748b"
              fontSize="10"
            >
              EXACT
            </text>
            <text
              x={centerX}
              y={centerY - RING_CONFIG.middle.radius - 8}
              textAnchor="middle"
              fill="#475569"
              fontSize="10"
            >
              POTENTIAL
            </text>
            <text
              x={centerX}
              y={centerY - RING_CONFIG.outer.radius - 8}
              textAnchor="middle"
              fill="#334155"
              fontSize="10"
            >
              HYPOTHESIS
            </text>

            {/* Center - Persona */}
            <g transform={`translate(${centerX}, ${centerY})`}>
              <circle
                r={50}
                fill="rgba(59, 130, 246, 0.15)"
                stroke="#3B82F6"
                strokeWidth="2"
              />
              <text
                textAnchor="middle"
                dy="-0.2em"
                fill="#fff"
                fontSize="14"
                fontWeight="bold"
              >
                {data.persona || 'USER'}
              </text>
              <text
                textAnchor="middle"
                dy="1.2em"
                fill="#64748b"
                fontSize="10"
              >
                {data.query_type}
              </text>
            </g>

            {/* Nodes */}
            {data.nodes.map(node => {
              const pos = nodePositions.get(node.id);
              if (!pos) return null;

              const isPrimary = node.id === data.primary_node_id;
              const isSelected = selectedNode?.id === node.id;
              const isHovered = hoveredNode === node.id;
              const radius = getCircleRadius(node.confidence, isPrimary);
              const color = DOMAIN_COLORS[node.domain] || DOMAIN_COLORS.finance;
              const arcRadius = radius + 6;

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  onClick={() => handleNodeClick(node)}
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                  style={{ cursor: 'pointer' }}
                  className="galaxy-node"
                >
                  {/* Selection/hover ring */}
                  {(isSelected || isHovered) && (
                    <circle
                      r={radius + 12}
                      fill="none"
                      stroke={isSelected ? '#fff' : '#64748b'}
                      strokeWidth={isSelected ? 2 : 1}
                      opacity={isSelected ? 0.8 : 0.5}
                    />
                  )}

                  {/* Main circle */}
                  <circle
                    r={radius}
                    fill={color}
                    opacity={isSelected || isHovered ? 1 : 0.85}
                    stroke={isPrimary ? '#fff' : 'none'}
                    strokeWidth={isPrimary ? 2 : 0}
                  />

                  {/* Data quality arc */}
                  <path
                    d={getArcPath(0, 0, arcRadius, node.data_quality)}
                    fill="none"
                    stroke="#4ade80"
                    strokeWidth="3"
                    strokeLinecap="round"
                    opacity="0.9"
                  />

                  {/* Freshness dot */}
                  <circle
                    cx={radius * 0.7}
                    cy={-radius * 0.7}
                    r={5}
                    fill={getFreshnessColor(node.freshness)}
                    stroke="#0f172a"
                    strokeWidth="1"
                  />

                  {/* Confidence percentage */}
                  <text
                    textAnchor="middle"
                    dy="0.35em"
                    fill="#fff"
                    fontSize={isPrimary ? 14 : 11}
                    fontWeight="bold"
                  >
                    {Math.round(node.confidence * 100)}%
                  </text>

                  {/* Label below node */}
                  <text
                    y={radius + 16}
                    textAnchor="middle"
                    fill="#94a3b8"
                    fontSize="10"
                    fontWeight="500"
                  >
                    {node.display_name}
                  </text>

                  {/* Semantic label */}
                  {node.semantic_label && (
                    <text
                      y={radius + 28}
                      textAnchor="middle"
                      fill="#64748b"
                      fontSize="9"
                    >
                      {node.semantic_label}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>

        {/* Node Detail Panel */}
        {selectedNode && (
          <NodeDetailPanel
            node={selectedNode}
            isPrimary={selectedNode.id === data.primary_node_id}
            onClose={() => setSelectedNode(null)}
          />
        )}
      </div>

      {/* Text Response */}
      {data.text_response && (
        <div className="px-4 py-3 bg-slate-900/70 border-t border-slate-800">
          <p className="text-slate-300 text-sm">{data.text_response}</p>
          {data.needs_clarification && data.clarification_prompt && (
            <p className="text-amber-400 text-sm mt-2">
              {data.clarification_prompt}
            </p>
          )}
        </div>
      )}

      {/* Legend */}
      <GalaxyLegend />
    </div>
  );
};
