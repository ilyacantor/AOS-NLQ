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
import { DashboardModal } from './DashboardModal';

interface GalaxyViewProps {
  data: IntentMapResponse;
}

interface NodeState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  targetX: number;
  targetY: number;
}

// Custom hook for responsive dimensions
function useContainerDimensions(ref: React.RefObject<HTMLDivElement | null>) {
  const [dimensions, setDimensions] = useState({ width: 500, height: 500 });

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout>;

    const updateDimensions = () => {
      // Debounce: wait 100ms after last resize before updating
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        if (ref.current) {
          const { width, height } = ref.current.getBoundingClientRect();
          // Ensure minimum size and maintain aspect ratio
          const minSize = Math.max(300, Math.min(width, height));
          setDimensions({
            width: Math.max(300, width),
            height: Math.max(300, Math.min(height, width * 0.85))
          });
        }
      }, 100);
    };

    // Initial measurement
    updateDimensions();

    const resizeObserver = new ResizeObserver(updateDimensions);
    if (ref.current) resizeObserver.observe(ref.current);

    return () => {
      clearTimeout(timeoutId);
      resizeObserver.disconnect();
    };
  }, [ref]);

  return dimensions;
}

export const GalaxyView: React.FC<GalaxyViewProps> = ({ data }) => {
  const [selectedNode, setSelectedNode] = useState<IntentNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<IntentNode | null>(null);
  const [hoveredPosition, setHoveredPosition] = useState<{ x: number; y: number } | null>(null);
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);
  const [nodeStates, setNodeStates] = useState<Map<string, NodeState>>(new Map());
  const [showDashboardModal, setShowDashboardModal] = useState(false);
  const [showLeftPanel, setShowLeftPanel] = useState(true);

  // Responsive container ref and dimensions
  const containerRef = useRef<HTMLDivElement>(null);
  const { width, height } = useContainerDimensions(containerRef);

  // Check if we're on mobile
  const isMobile = width < 640;

  // Auto-show modal for dashboard queries
  const isDashboard = data.query_type === 'DASHBOARD';
  useEffect(() => {
    if (isDashboard) {
      setShowDashboardModal(true);
    } else {
      setShowDashboardModal(false);
    }
  }, [isDashboard, data.query]);

  const svgRef = useRef<SVGSVGElement>(null);
  const animationRef = useRef<number | null>(null);

  // Calculate center based on current dimensions
  const centerX = width / 2;
  const centerY = height / 2;

  // Scale rings for smaller screens
  const scaleFactor = Math.min(1, width / 700);
  const scaledRingConfig = {
    inner: { ...RING_CONFIG.inner, radius: RING_CONFIG.inner.radius * scaleFactor },
    middle: { ...RING_CONFIG.middle, radius: RING_CONFIG.middle.radius * scaleFactor },
    outer: { ...RING_CONFIG.outer, radius: RING_CONFIG.outer.radius * scaleFactor },
  };

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

    placeNodesOnRing(inner, scaledRingConfig.inner.radius);
    placeNodesOnRing(middle, scaledRingConfig.middle.radius);
    placeNodesOnRing(outer, scaledRingConfig.outer.radius);

    return positions;
  }, [data.nodes, centerX, centerY, scaledRingConfig]);

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

  return (
    <div className="galaxy-container flex flex-col h-full bg-slate-950">
      {/* Header */}
      <GalaxyHeader
        confidence={data.overall_confidence}
        dataQuality={data.overall_data_quality}
        nodeCount={data.node_count}
        query={data.query}
      />

      {/* Main content area - responsive layout */}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0 overflow-hidden">
        {/* Left Panel - Text Response & Data Table */}
        {/* Mobile: collapsible, Desktop: always visible */}
        <div className={`
          ${isMobile ? (showLeftPanel ? 'max-h-48' : 'max-h-0') : ''}
          lg:max-h-none lg:flex-shrink-0
          flex flex-col border-b lg:border-b-0 lg:border-r border-slate-800 bg-slate-900/30
          transition-all duration-300 overflow-hidden
          w-full lg:w-72 xl:w-[293px]
        `}>
          {/* Mobile: Toggle button for left panel */}
          {isMobile && (
            <button
              onClick={() => setShowLeftPanel(!showLeftPanel)}
              className="flex items-center justify-between w-full px-4 py-2 bg-slate-800/50 text-slate-300 text-sm"
            >
              <span>Answer & Data</span>
              <svg
                className={`w-4 h-4 transition-transform ${showLeftPanel ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          )}

          {/* Text Answer */}
          {data.text_response && (
            <div className="p-3 lg:p-4 border-b border-slate-800/50">
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                Answer
              </h3>
              <p className="text-slate-200 text-sm leading-relaxed line-clamp-3 lg:line-clamp-none">
                {data.text_response}
              </p>
              {data.needs_clarification && data.clarification_prompt && (
                <p className="text-amber-400 text-sm mt-3 p-2 bg-amber-900/20 rounded border border-amber-800/30">
                  {data.clarification_prompt}
                </p>
              )}
            </div>
          )}

          {/* Data Table - Below Text Answer (hidden on mobile when collapsed) */}
          {hasMultipleDataElements && (!isMobile || showLeftPanel) && (
            <div className="flex-1 overflow-auto p-3 hidden lg:block">
              <DataTable nodes={data.nodes} title="Data Points" />
            </div>
          )}

          {/* Legend at bottom of left panel - hidden on mobile */}
          <div className="mt-auto border-t border-slate-800/50 hidden lg:block">
            <GalaxyLegend compact />
          </div>
        </div>

        {/* Center - SVG Visualization */}
        <div
          ref={containerRef}
          className="flex-1 flex items-center justify-center p-2 lg:p-4 overflow-hidden min-h-0"
        >
          <svg
            ref={svgRef}
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            className="galaxy-svg w-full h-full"
            style={{ maxWidth: width, maxHeight: height }}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseLeave}
            onTouchMove={(e) => {
              if (!draggedNodeId || !svgRef.current) return;
              const touch = e.touches[0];
              const svgRect = svgRef.current.getBoundingClientRect();
              const touchX = touch.clientX - svgRect.left;
              const touchY = touch.clientY - svgRect.top;
              setNodeStates(prev => {
                const next = new Map(prev);
                const state = next.get(draggedNodeId);
                if (state) {
                  state.x = touchX;
                  state.y = touchY;
                  state.vx = 0;
                  state.vy = 0;
                }
                return next;
              });
            }}
            onTouchEnd={() => setDraggedNodeId(null)}
          >
            {/* Gradient definitions */}
            <defs>
              <radialGradient id="bgGradient" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#0f172a" />
                <stop offset="100%" stopColor="#020617" />
              </radialGradient>
            </defs>
            <rect width={width} height={height} fill="url(#bgGradient)" />

            {/* Orbital Rings - scaled for responsive */}
            <circle
              cx={centerX}
              cy={centerY}
              r={scaledRingConfig.outer.radius}
              fill="none"
              stroke={RING_CONFIG.outer.strokeColor}
              strokeWidth="1"
              strokeDasharray="4 4"
            />
            <circle
              cx={centerX}
              cy={centerY}
              r={scaledRingConfig.middle.radius}
              fill="none"
              stroke={RING_CONFIG.middle.strokeColor}
              strokeWidth="1"
              strokeDasharray="4 4"
            />
            <circle
              cx={centerX}
              cy={centerY}
              r={scaledRingConfig.inner.radius}
              fill="none"
              stroke={RING_CONFIG.inner.strokeColor}
              strokeWidth="2"
            />

            {/* Ring Labels - hidden on small screens */}
            {!isMobile && (
              <>
                <text
                  x={centerX}
                  y={centerY - scaledRingConfig.inner.radius - 8}
                  textAnchor="middle"
                  fill="#64748b"
                  fontSize="10"
                >
                  Inner
                </text>
                <text
                  x={centerX + scaledRingConfig.middle.radius + 15}
                  y={centerY}
                  textAnchor="start"
                  fill="#475569"
                  fontSize="10"
                >
                  Outer
                </text>
              </>
            )}

            {/* Center - Persona - scaled for responsive */}
            <g transform={`translate(${centerX}, ${centerY})`}>
              <circle
                r={50 * scaleFactor}
                fill="rgba(59, 130, 246, 0.15)"
                stroke="#3B82F6"
                strokeWidth="2"
              />
              <text
                textAnchor="middle"
                dy="-0.2em"
                fill="#fff"
                fontSize={14 * scaleFactor}
                fontWeight="bold"
              >
                {data.persona || 'CFO'}
              </text>
              <text
                textAnchor="middle"
                dy="1.2em"
                fill="#64748b"
                fontSize={10 * scaleFactor}
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
              // Scale radius for mobile, ensure minimum touch target (22px radius = 44px diameter)
              const baseRadius = getCircleRadius(node.confidence, isPrimary);
              const radius = Math.max(22, baseRadius * scaleFactor);
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
                  onTouchStart={(e) => {
                    e.preventDefault();
                    setDraggedNodeId(node.id);
                    setHoveredNode(null);
                    setHoveredPosition(null);
                  }}
                  style={{ cursor: isDragging ? 'grabbing' : 'grab', touchAction: 'none' }}
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
                    fontSize={Math.max(10, (isPrimary ? 14 : 11) * scaleFactor)}
                    fontWeight="bold"
                    style={{ pointerEvents: 'none' }}
                  >
                    {Math.round(node.confidence * 100)}%
                  </text>

                  {/* Label below node - hidden on small screens */}
                  {!isMobile && (
                    <>
                      <text
                        y={radius + 16}
                        textAnchor="middle"
                        fill="#94a3b8"
                        fontSize={10 * scaleFactor}
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
                        fontSize={9 * scaleFactor}
                        style={{ pointerEvents: 'none' }}
                      >
                        {isPrimary ? 'PRIMARY' : node.match_type.toUpperCase()}
                      </text>
                    </>
                  )}
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
        </div>

        {/* Right Panel - Node Detail Panel */}
        {/* Mobile: Bottom sheet, Desktop: Side panel */}
        {selectedNode && (
          <div className={`
            ${isMobile
              ? 'fixed inset-x-0 bottom-0 z-50 max-h-[60vh] rounded-t-2xl safe-bottom'
              : 'relative'
            }
          `}>
            <NodeDetailPanel
              node={selectedNode}
              isPrimary={selectedNode.id === data.primary_node_id}
              onClose={() => setSelectedNode(null)}
            />
          </div>
        )}
      </div>

      {/* Dashboard Modal - for KPI/Dashboard queries */}
      <DashboardModal
        isOpen={showDashboardModal}
        onClose={() => setShowDashboardModal(false)}
        title={data.persona === 'KPIs' ? '2025 vs 2024 KPIs' : `${data.persona || 'Executive'} Dashboard`}
        textResponse={data.text_response || ''}
        nodes={data.nodes}
      />
    </div>
  );
};
