import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
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
import { DataTable } from './DataTable';

interface GalaxyViewProps {
  data: IntentMapResponse;
  width?: number;
  height?: number;
  /** Callback when a dashboard query is detected - navigates to dashboard space */
  onNavigateToDashboard?: (query: string, data: IntentMapResponse) => void;
}

// Bottom sheet height states
type SheetState = 'collapsed' | 'partial' | 'expanded';
const SHEET_COLLAPSED_HEIGHT = 80;
const SHEET_PARTIAL_HEIGHT = 240;
const SHEET_EXPANDED_HEIGHT_RATIO = 0.7; // 70% of viewport

interface NodeState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  targetX: number;
  targetY: number;
}

export const GalaxyView: React.FC<GalaxyViewProps> = ({
  data,
  width = 700,
  height = 700,
  onNavigateToDashboard,
}) => {
  const [selectedNode, setSelectedNode] = useState<IntentNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<IntentNode | null>(null);
  const [hoveredPosition, setHoveredPosition] = useState<{ x: number; y: number } | null>(null);
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);
  const [nodeStates, setNodeStates] = useState<Map<string, NodeState>>(new Map());

  // Mobile bottom sheet state
  const [sheetState, setSheetState] = useState<SheetState>('collapsed');
  const [isDraggingSheet, setIsDraggingSheet] = useState(false);
  const [sheetDragStart, setSheetDragStart] = useState<number>(0);
  const [sheetDragOffset, setSheetDragOffset] = useState<number>(0);
  const sheetRef = useRef<HTMLDivElement>(null);

  // Navigate to dashboard space when dashboard query is detected
  const isDashboard = data.query_type === 'DASHBOARD';
  useEffect(() => {
    if (isDashboard && onNavigateToDashboard) {
      // Navigate to dashboard space instead of showing modal
      onNavigateToDashboard(data.query, data);
    }
  }, [isDashboard, data.query, data, onNavigateToDashboard]);

  const svgRef = useRef<SVGSVGElement>(null);
  const animationRef = useRef<number | null>(null);

  const centerX = width / 2;
  const centerY = height / 2;

  // Calculate target positions for nodes on their rings
  const targetPositions = useMemo(() => {
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

    const inner = data.nodes.filter(n => n.match_type === 'exact');
    const middle = data.nodes.filter(n => n.match_type === 'potential');
    const outer = data.nodes.filter(n => n.match_type === 'hypothesis');

    placeNodesOnRing(inner, RING_CONFIG.inner.radius);
    placeNodesOnRing(middle, RING_CONFIG.middle.radius);
    placeNodesOnRing(outer, RING_CONFIG.outer.radius);

    return positions;
  }, [data.nodes, centerX, centerY]);

  // Initialize node states when data changes
  useEffect(() => {
    const newStates = new Map<string, NodeState>();
    data.nodes.forEach(node => {
      const target = targetPositions.get(node.id) || { x: centerX, y: centerY };
      const existing = nodeStates.get(node.id);
      newStates.set(node.id, {
        x: existing?.x ?? target.x,
        y: existing?.y ?? target.y,
        vx: 0,
        vy: 0,
        targetX: target.x,
        targetY: target.y,
      });
    });
    setNodeStates(newStates);
  }, [data.nodes, targetPositions]);

  // Physics simulation loop - nodes smoothly return to their orbital positions
  useEffect(() => {
    const simulate = () => {
      setNodeStates(prev => {
        const next = new Map(prev);
        let needsUpdate = false;

        next.forEach((state, nodeId) => {
          // Skip dragged node
          if (nodeId === draggedNodeId) return;

          // Spring force toward target position
          const dx = state.targetX - state.x;
          const dy = state.targetY - state.y;
          const distance = Math.sqrt(dx * dx + dy * dy);

          if (distance > 0.5) {
            needsUpdate = true;
            // Spring constant
            const springStrength = 0.08;
            // Damping
            const damping = 0.85;

            // Apply spring force
            state.vx = (state.vx + dx * springStrength) * damping;
            state.vy = (state.vy + dy * springStrength) * damping;

            // Update position
            state.x += state.vx;
            state.y += state.vy;
          } else {
            // Snap to target when close enough
            state.x = state.targetX;
            state.y = state.targetY;
            state.vx = 0;
            state.vy = 0;
          }
        });

        return next;
      });

      animationRef.current = requestAnimationFrame(simulate);
    };

    animationRef.current = requestAnimationFrame(simulate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [draggedNodeId]);

  // Get current position for a node
  const getNodePosition = useCallback((nodeId: string) => {
    const state = nodeStates.get(nodeId);
    if (state) {
      return { x: state.x, y: state.y };
    }
    return targetPositions.get(nodeId) || { x: centerX, y: centerY };
  }, [nodeStates, targetPositions, centerX, centerY]);

  // Drag handlers
  const handleMouseDown = useCallback((e: React.MouseEvent, node: IntentNode) => {
    e.preventDefault();
    e.stopPropagation();
    setDraggedNodeId(node.id);
    setHoveredNode(null);
    setHoveredPosition(null);
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!draggedNodeId || !svgRef.current) return;

    const svgRect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - svgRect.left;
    const mouseY = e.clientY - svgRect.top;

    setNodeStates(prev => {
      const next = new Map(prev);
      const state = next.get(draggedNodeId);
      if (state) {
        state.x = mouseX;
        state.y = mouseY;
        state.vx = 0;
        state.vy = 0;
      }
      return next;
    });
  }, [draggedNodeId]);

  const handleMouseUp = useCallback(() => {
    setDraggedNodeId(null);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setDraggedNodeId(null);
    setHoveredNode(null);
    setHoveredPosition(null);
  }, []);

  const handleNodeClick = (node: IntentNode) => {
    if (!draggedNodeId) {
      setSelectedNode(prev => prev?.id === node.id ? null : node);
    }
  };

  const handleNodeMouseEnter = (node: IntentNode) => {
    if (!draggedNodeId) {
      setHoveredNode(node);
      const pos = getNodePosition(node.id);
      setHoveredPosition(pos);
    }
  };

  const handleNodeMouseLeave = () => {
    if (!draggedNodeId) {
      setHoveredNode(null);
      setHoveredPosition(null);
    }
  };

  // Check if we have multiple data elements for table display
  const hasMultipleDataElements = data.nodes && data.nodes.length > 1;

  // Mobile bottom sheet handlers
  const handleSheetTouchStart = useCallback((e: React.TouchEvent) => {
    setIsDraggingSheet(true);
    setSheetDragStart(e.touches[0].clientY);
    setSheetDragOffset(0);
  }, []);

  const handleSheetTouchMove = useCallback((e: React.TouchEvent) => {
    if (!isDraggingSheet) return;
    const currentY = e.touches[0].clientY;
    const delta = sheetDragStart - currentY;
    setSheetDragOffset(delta);
  }, [isDraggingSheet, sheetDragStart]);

  const handleSheetTouchEnd = useCallback(() => {
    if (!isDraggingSheet) return;
    setIsDraggingSheet(false);

    // Determine new state based on drag direction and distance
    const threshold = 50;
    if (sheetDragOffset > threshold) {
      // Dragged up - expand
      setSheetState(prev => prev === 'collapsed' ? 'partial' : 'expanded');
    } else if (sheetDragOffset < -threshold) {
      // Dragged down - collapse
      setSheetState(prev => prev === 'expanded' ? 'partial' : 'collapsed');
    }
    setSheetDragOffset(0);
  }, [isDraggingSheet, sheetDragOffset]);

  const toggleSheetState = useCallback(() => {
    setSheetState(prev => {
      if (prev === 'collapsed') return 'partial';
      if (prev === 'partial') return 'expanded';
      return 'collapsed';
    });
  }, []);

  // Calculate sheet height based on state
  const getSheetHeight = useCallback(() => {
    const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 600;
    switch (sheetState) {
      case 'collapsed': return SHEET_COLLAPSED_HEIGHT;
      case 'partial': return SHEET_PARTIAL_HEIGHT;
      case 'expanded': return Math.round(viewportHeight * SHEET_EXPANDED_HEIGHT_RATIO);
    }
  }, [sheetState]);

  // SVG content for reuse in both layouts
  const svgContent = (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="galaxy-svg max-w-full max-h-full"
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseLeave}
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
              const isDragging = draggedNodeId === node.id;
              const radius = getCircleRadius(node.confidence, isPrimary);
              const color = DOMAIN_COLORS[node.domain] || DOMAIN_COLORS.finance;
              const arcRadius = radius + 6;

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  onClick={() => handleNodeClick(node)}
                  onMouseDown={(e) => handleMouseDown(e, node)}
                  onMouseEnter={() => handleNodeMouseEnter(node)}
                  onMouseLeave={handleNodeMouseLeave}
                  style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
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
      {hoveredNode && hoveredPosition && !draggedNodeId && (
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
  );

  return (
    <div className="galaxy-container flex flex-col h-full bg-slate-950">
      {/* Header */}
      <GalaxyHeader
        confidence={data.overall_confidence}
        dataQuality={data.overall_data_quality}
        nodeCount={data.node_count}
        query={data.query}
      />

      {/* ============ MOBILE LAYOUT ============ */}
      <div className="md:hidden flex-1 flex flex-col min-h-0 overflow-hidden relative">
        {/* Full-width SVG visualization */}
        <div className="flex-1 flex items-center justify-center p-2 overflow-hidden min-h-0">
          {svgContent}
        </div>

        {/* Mobile Bottom Sheet */}
        <div
          ref={sheetRef}
          className="absolute left-0 right-0 bottom-0 bg-slate-900 border-t border-slate-700 rounded-t-2xl shadow-2xl transition-all duration-300 ease-out"
          style={{
            height: isDraggingSheet
              ? Math.max(SHEET_COLLAPSED_HEIGHT, getSheetHeight() + sheetDragOffset)
              : getSheetHeight(),
            maxHeight: '85vh',
          }}
        >
          {/* Drag Handle */}
          <div
            className="flex justify-center items-center py-3 cursor-grab active:cursor-grabbing touch-none"
            onTouchStart={handleSheetTouchStart}
            onTouchMove={handleSheetTouchMove}
            onTouchEnd={handleSheetTouchEnd}
            onClick={toggleSheetState}
          >
            <div className="w-12 h-1.5 bg-slate-600 rounded-full" />
          </div>

          {/* Sheet Content */}
          <div className="px-4 pb-4 overflow-y-auto" style={{ maxHeight: 'calc(100% - 40px)' }}>
            {/* Answer Summary - Always visible */}
            {data.text_response && (
              <div className="mb-3">
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
                  Answer
                </h3>
                <p className={`text-slate-200 text-sm leading-relaxed ${sheetState === 'collapsed' ? 'line-clamp-2' : ''}`}>
                  {data.text_response}
                </p>
                {data.needs_clarification && data.clarification_prompt && sheetState !== 'collapsed' && (
                  <p className="text-amber-400 text-sm mt-2 p-2 bg-amber-900/20 rounded border border-amber-800/30">
                    {data.clarification_prompt}
                  </p>
                )}
              </div>
            )}

            {/* Expanded Content - Data Table and Legend */}
            {sheetState !== 'collapsed' && (
              <>
                {/* Data Table */}
                {hasMultipleDataElements && (
                  <div className="mb-3">
                    <DataTable nodes={data.nodes} title="Data Points" />
                  </div>
                )}

                {/* Legend - only in expanded state */}
                {sheetState === 'expanded' && (
                  <div className="border-t border-slate-800/50 pt-3">
                    <GalaxyLegend compact />
                  </div>
                )}
              </>
            )}

            {/* Expand hint when collapsed */}
            {sheetState === 'collapsed' && (
              <p className="text-slate-500 text-xs text-center mt-1">
                Swipe up for details
              </p>
            )}
          </div>
        </div>

        {/* Selected Node Overlay (Mobile) */}
        {selectedNode && (
          <div className="absolute inset-0 bg-black/50 z-50 flex items-end">
            <div className="w-full max-h-[70vh] overflow-auto">
              <NodeDetailPanel
                node={selectedNode}
                isPrimary={selectedNode.id === data.primary_node_id}
                onClose={() => setSelectedNode(null)}
              />
            </div>
          </div>
        )}
      </div>

      {/* ============ DESKTOP LAYOUT ============ */}
      <div className="hidden md:flex flex-1 min-h-0 overflow-hidden">
        {/* Left Panel - Text Response & Data Table */}
        <div className="flex-shrink-0 flex flex-col border-r border-slate-800 bg-slate-900/30" style={{ width: '293px' }}>
          {/* Text Answer - Top Left */}
          {data.text_response && (
            <div className="p-4 border-b border-slate-800/50">
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                Answer
              </h3>
              <p className="text-slate-200 text-sm leading-relaxed">
                {data.text_response}
              </p>
              {data.needs_clarification && data.clarification_prompt && (
                <p className="text-amber-400 text-sm mt-3 p-2 bg-amber-900/20 rounded border border-amber-800/30">
                  {data.clarification_prompt}
                </p>
              )}
            </div>
          )}

          {/* Data Table - Below Text Answer */}
          {hasMultipleDataElements && (
            <div className="flex-1 overflow-auto p-3">
              <DataTable nodes={data.nodes} title="Data Points" />
            </div>
          )}

          {/* Legend at bottom of left panel */}
          <div className="mt-auto border-t border-slate-800/50">
            <GalaxyLegend compact />
          </div>
        </div>

        {/* Center - SVG Visualization */}
        <div className="flex-1 flex items-center justify-center p-4 overflow-hidden min-h-0">
          {svgContent}
        </div>

        {/* Right Panel - Node Detail Panel */}
        {selectedNode && (
          <NodeDetailPanel
            node={selectedNode}
            isPrimary={selectedNode.id === data.primary_node_id}
            onClose={() => setSelectedNode(null)}
          />
        )}
      </div>
    </div>
  );
};
