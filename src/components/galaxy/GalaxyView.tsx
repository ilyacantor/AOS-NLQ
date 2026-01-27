import React, { useMemo, useState, useEffect, useCallback, useRef } from 'react';
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

interface DragState {
  nodeId: string;
  offsetX: number;
  offsetY: number;
}

export const GalaxyView: React.FC<GalaxyViewProps> = ({
  data,
  width = 700,
  height = 700,
}) => {
  const [selectedNode, setSelectedNode] = useState<IntentNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<IntentNode | null>(null);
  const [hoveredPosition, setHoveredPosition] = useState<{ x: number; y: number } | null>(null);
  const [isFloating, setIsFloating] = useState(true);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [nodeOffsets, setNodeOffsets] = useState<Map<string, { x: number; y: number }>>(new Map());
  const [snappingNodes, setSnappingNodes] = useState<Set<string>>(new Set());
  const svgRef = useRef<SVGSVGElement>(null);

  const centerX = width / 2;
  const centerY = height / 2;

  // Stop floating animation after 3 seconds
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsFloating(false);
    }, 3000);
    return () => clearTimeout(timer);
  }, []);

  // Group nodes by ring (match_type)
  const nodesByRing = useMemo(() => {
    const inner = data.nodes.filter(n => n.match_type === 'exact');
    const middle = data.nodes.filter(n => n.match_type === 'potential');
    const outer = data.nodes.filter(n => n.match_type === 'hypothesis');
    return { inner, middle, outer };
  }, [data.nodes]);

  // Calculate base positions for all nodes
  const nodePositions = useMemo(() => {
    const positions = new Map<string, { x: number; y: number }>();

    const placeNodesOnRing = (nodes: IntentNode[], radius: number) => {
      if (nodes.length === 0) return;

      const angleStep = (2 * Math.PI) / nodes.length;
      const startAngle = -Math.PI / 2;

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

  // Get current position including any drag offset
  const getNodePosition = useCallback((nodeId: string) => {
    const basePos = nodePositions.get(nodeId);
    if (!basePos) return { x: 0, y: 0 };

    const offset = nodeOffsets.get(nodeId);
    if (offset) {
      return {
        x: basePos.x + offset.x,
        y: basePos.y + offset.y,
      };
    }
    return basePos;
  }, [nodePositions, nodeOffsets]);

  // Handle mouse down on node - start drag
  const handleMouseDown = useCallback((e: React.MouseEvent, node: IntentNode) => {
    e.preventDefault();
    e.stopPropagation();

    const pos = getNodePosition(node.id);
    const svgRect = svgRef.current?.getBoundingClientRect();
    if (!svgRect) return;

    const mouseX = e.clientX - svgRect.left;
    const mouseY = e.clientY - svgRect.top;

    // Remove from snapping set if it was snapping
    setSnappingNodes(prev => {
      const next = new Set(prev);
      next.delete(node.id);
      return next;
    });

    setDragState({
      nodeId: node.id,
      offsetX: mouseX - pos.x,
      offsetY: mouseY - pos.y,
    });

    // Hide tooltip while dragging
    setHoveredNode(null);
    setHoveredPosition(null);
  }, [getNodePosition]);

  // Handle mouse move - update drag position
  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragState) return;

    const svgRect = svgRef.current?.getBoundingClientRect();
    if (!svgRect) return;

    const mouseX = e.clientX - svgRect.left;
    const mouseY = e.clientY - svgRect.top;

    const newX = mouseX - dragState.offsetX;
    const newY = mouseY - dragState.offsetY;

    setNodeOffsets(prev => {
      const next = new Map(prev);
      const basePos = nodePositions.get(dragState.nodeId);
      if (basePos) {
        next.set(dragState.nodeId, {
          x: newX - basePos.x,
          y: newY - basePos.y,
        });
      }
      return next;
    });
  }, [dragState, nodePositions]);

  // Handle mouse up - snap back to original position
  const handleMouseUp = useCallback(() => {
    if (!dragState) return;

    const nodeId = dragState.nodeId;

    // Add to snapping set for animation
    setSnappingNodes(prev => {
      const next = new Set(prev);
      next.add(nodeId);
      return next;
    });

    // Remove offset to snap back
    setNodeOffsets(prev => {
      const next = new Map(prev);
      next.delete(nodeId);
      return next;
    });

    // Remove from snapping set after animation
    setTimeout(() => {
      setSnappingNodes(prev => {
        const next = new Set(prev);
        next.delete(nodeId);
        return next;
      });
    }, 300);

    setDragState(null);
  }, [dragState]);

  // Handle mouse leave SVG
  const handleMouseLeave = useCallback(() => {
    if (dragState) {
      handleMouseUp();
    }
    setHoveredNode(null);
    setHoveredPosition(null);
  }, [dragState, handleMouseUp]);

  const handleNodeClick = (node: IntentNode) => {
    if (!dragState) {
      setSelectedNode(prev => prev?.id === node.id ? null : node);
    }
  };

  const handleNodeMouseEnter = (node: IntentNode) => {
    if (!dragState) {
      setHoveredNode(node);
      const pos = getNodePosition(node.id);
      setHoveredPosition(pos);
    }
  };

  const handleNodeMouseLeave = () => {
    if (!dragState) {
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
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseLeave}
          >
            {/* CSS for floating animation */}
            <defs>
              <radialGradient id="bgGradient" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#0f172a" />
                <stop offset="100%" stopColor="#020617" />
              </radialGradient>
              <style>{`
                @keyframes float0 {
                  0%, 100% { transform: translate(0, 0); }
                  25% { transform: translate(3px, -4px); }
                  50% { transform: translate(-2px, 3px); }
                  75% { transform: translate(4px, 2px); }
                }
                @keyframes float1 {
                  0%, 100% { transform: translate(0, 0); }
                  25% { transform: translate(-4px, 2px); }
                  50% { transform: translate(3px, -3px); }
                  75% { transform: translate(-2px, 4px); }
                }
                @keyframes float2 {
                  0%, 100% { transform: translate(0, 0); }
                  25% { transform: translate(2px, 4px); }
                  50% { transform: translate(-3px, -2px); }
                  75% { transform: translate(3px, -3px); }
                }
                .floating-0 { animation: float0 2.5s ease-in-out infinite; }
                .floating-1 { animation: float1 2.8s ease-in-out infinite; animation-delay: 0.3s; }
                .floating-2 { animation: float2 2.2s ease-in-out infinite; animation-delay: 0.6s; }
                .snapping {
                  transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
                }
              `}</style>
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
            {data.nodes.map((node, index) => {
              const pos = getNodePosition(node.id);
              const isPrimary = node.id === data.primary_node_id;
              const isSelected = selectedNode?.id === node.id;
              const isHovered = hoveredNode?.id === node.id;
              const isDragging = dragState?.nodeId === node.id;
              const isSnapping = snappingNodes.has(node.id);
              const radius = getCircleRadius(node.confidence, isPrimary);
              const color = DOMAIN_COLORS[node.domain] || DOMAIN_COLORS.finance;
              const arcRadius = radius + 6;

              // Determine animation class
              const floatClass = isFloating && !isDragging ? `floating-${index % 3}` : '';
              const snapClass = isSnapping ? 'snapping' : '';

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  onClick={() => handleNodeClick(node)}
                  onMouseDown={(e) => handleMouseDown(e, node)}
                  onMouseEnter={() => handleNodeMouseEnter(node)}
                  onMouseLeave={handleNodeMouseLeave}
                  style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
                  className={`galaxy-node ${floatClass} ${snapClass}`}
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
            {hoveredNode && hoveredPosition && !dragState && (
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
