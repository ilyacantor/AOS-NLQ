import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as d3 from 'd3';
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
import { NodeTooltip } from './NodeTooltip';

interface GalaxyViewProps {
  data: IntentMapResponse;
  width?: number;
  height?: number;
}

// Simulation node type extending IntentNode with D3 simulation properties
interface SimulationNode extends IntentNode {
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
  vx?: number;
  vy?: number;
}

export const GalaxyView: React.FC<GalaxyViewProps> = ({
  data,
  width = 700,
  height = 700,
}) => {
  const [selectedNode, setSelectedNode] = useState<IntentNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<IntentNode | null>(null);
  const [hoveredPosition, setHoveredPosition] = useState<{ x: number; y: number } | null>(null);
  const [nodePositions, setNodePositions] = useState<Map<string, { x: number; y: number }>>(new Map());
  const [isDragging, setIsDragging] = useState(false);

  const svgRef = useRef<SVGSVGElement>(null);
  const simulationRef = useRef<d3.Simulation<SimulationNode, undefined> | null>(null);

  const centerX = width / 2;
  const centerY = height / 2;

  // Ring radii for radial force
  const ringRadii = {
    exact: RING_CONFIG.inner.radius,
    potential: RING_CONFIG.middle.radius,
    hypothesis: RING_CONFIG.outer.radius,
  };

  // Initialize D3 force simulation
  useEffect(() => {
    if (!svgRef.current || data.nodes.length === 0) return;

    // Create simulation nodes with initial positions on their respective rings
    const simNodes: SimulationNode[] = data.nodes.map((node, i) => {
      const ringRadius = ringRadii[node.match_type as keyof typeof ringRadii] || ringRadii.potential;
      const nodesInRing = data.nodes.filter(n => n.match_type === node.match_type);
      const indexInRing = nodesInRing.indexOf(node);
      const angleStep = (2 * Math.PI) / nodesInRing.length;
      const angle = -Math.PI / 2 + angleStep * indexInRing;

      return {
        ...node,
        x: centerX + ringRadius * Math.cos(angle),
        y: centerY + ringRadius * Math.sin(angle),
      };
    });

    // Create force simulation
    const simulation = d3.forceSimulation<SimulationNode>(simNodes)
      .force("charge", d3.forceManyBody<SimulationNode>().strength(-150))
      .force("center", d3.forceCenter(centerX, centerY).strength(0.01))
      .force("collision", d3.forceCollide<SimulationNode>()
        .radius(d => 15 + d.confidence * 35)
        .strength(0.8)
      )
      .force("radial", d3.forceRadial<SimulationNode>(
        d => ringRadii[d.match_type as keyof typeof ringRadii] || ringRadii.potential,
        centerX,
        centerY
      ).strength(0.6))
      .alphaDecay(0.02)
      .velocityDecay(0.3);

    // Update positions on each tick
    simulation.on("tick", () => {
      const newPositions = new Map<string, { x: number; y: number }>();
      simNodes.forEach(node => {
        newPositions.set(node.id, { x: node.x || centerX, y: node.y || centerY });
      });
      setNodePositions(newPositions);
    });

    simulationRef.current = simulation;

    // Setup drag behavior on nodes
    const svg = d3.select(svgRef.current);

    const drag = d3.drag<SVGGElement, SimulationNode>()
      .on("start", (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
        setIsDragging(true);
        setHoveredNode(null);
        setHoveredPosition(null);
      })
      .on("drag", (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on("end", (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        // Let node return to its natural position
        d.fx = null;
        d.fy = null;
        setIsDragging(false);
      });

    // Apply drag behavior to node groups
    svg.selectAll<SVGGElement, SimulationNode>(".galaxy-node")
      .data(simNodes, d => d.id)
      .call(drag);

    return () => {
      simulation.stop();
      simulationRef.current = null;
    };
  }, [data.nodes, centerX, centerY, width, height]);

  // Reheat simulation when data changes
  useEffect(() => {
    if (simulationRef.current) {
      simulationRef.current.alpha(0.5).restart();
    }
  }, [data]);

  const getNodePosition = useCallback((nodeId: string) => {
    return nodePositions.get(nodeId) || { x: centerX, y: centerY };
  }, [nodePositions, centerX, centerY]);

  const handleNodeClick = (node: IntentNode) => {
    if (!isDragging) {
      setSelectedNode(prev => prev?.id === node.id ? null : node);
    }
  };

  const handleNodeMouseEnter = (node: IntentNode) => {
    if (!isDragging) {
      setHoveredNode(node);
      const pos = getNodePosition(node.id);
      setHoveredPosition(pos);
    }
  };

  const handleNodeMouseLeave = () => {
    if (!isDragging) {
      setHoveredNode(null);
      setHoveredPosition(null);
    }
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
            ref={svgRef}
            width={width}
            height={height}
            className="galaxy-svg"
            style={{ filter: 'drop-shadow(0 0 20px rgba(59, 130, 246, 0.15))' }}
          >
            {/* Gradient definitions */}
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
              Inner
            </text>
            <text
              x={centerX + RING_CONFIG.middle.radius + 15}
              y={centerY}
              textAnchor="start"
              fill="#475569"
              fontSize="10"
            >
              Outer
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
                {data.persona || 'CFO'}
              </text>
              <text
                textAnchor="middle"
                dy="1.2em"
                fill="#64748b"
                fontSize="10"
              >
                PERSONA
              </text>
            </g>

            {/* Nodes */}
            {data.nodes.map((node) => {
              const pos = getNodePosition(node.id);
              const isPrimary = node.id === data.primary_node_id;
              const isSelected = selectedNode?.id === node.id;
              const isHovered = hoveredNode?.id === node.id;
              const radius = getCircleRadius(node.confidence, isPrimary);
              const color = DOMAIN_COLORS[node.domain] || DOMAIN_COLORS.finance;
              const arcRadius = radius + 6;

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  onClick={() => handleNodeClick(node)}
                  onMouseEnter={() => handleNodeMouseEnter(node)}
                  onMouseLeave={handleNodeMouseLeave}
                  style={{ cursor: 'grab' }}
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
                    style={{ pointerEvents: 'none' }}
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
                    style={{ pointerEvents: 'none' }}
                  >
                    {node.semantic_label}: {node.display_name}
                  </text>

                  {/* Secondary label */}
                  <text
                    y={radius + 28}
                    textAnchor="middle"
                    fill="#64748b"
                    fontSize="9"
                    style={{ pointerEvents: 'none' }}
                  >
                    {isPrimary ? 'PRIMARY' : node.match_type.toUpperCase()}
                  </text>
                </g>
              );
            })}

            {/* Hover Tooltip */}
            {hoveredNode && hoveredPosition && !isDragging && (
              <NodeTooltip
                node={hoveredNode}
                isPrimary={hoveredNode.id === data.primary_node_id}
                x={hoveredPosition.x}
                y={hoveredPosition.y}
                svgWidth={width}
                svgHeight={height}
              />
            )}
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
