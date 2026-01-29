import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  IntentMapResponse,
  IntentNode,
  RING_CONFIG,
  DOMAIN_COLORS,
  getCircleRadius,
  getQualityRingRadius,
  getInnerHighlightRadius,
  getTypeStyle,
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
  width?: number;
  height?: number;
}

interface NodeState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  targetRadius: number;  // Orbital radius this node should be on
  fx: number | null;     // Fixed x position (for dragging)
  fy: number | null;     // Fixed y position (for dragging)
}

export const GalaxyView: React.FC<GalaxyViewProps> = ({
  data,
  width = 700,
  height = 700,
}) => {
  const [selectedNode, setSelectedNode] = useState<IntentNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<IntentNode | null>(null);
  const [hoveredPosition, setHoveredPosition] = useState<{ x: number; y: number } | null>(null);
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);
  const [nodeStates, setNodeStates] = useState<Map<string, NodeState>>(new Map());
  const [showDashboardModal, setShowDashboardModal] = useState(false);

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

  const centerX = width / 2;
  const centerY = height / 2;

  // Simulation alpha (heat) - controls how active the simulation is
  const alphaRef = useRef(1.0);
  const alphaTargetRef = useRef(0);

  // Get orbital radius for a node based on match type
  const getOrbitalRadius = useCallback((matchType: string) => {
    switch (matchType) {
      case 'exact': return RING_CONFIG.inner.radius;
      case 'potential': return RING_CONFIG.middle.radius;
      case 'hypothesis': return RING_CONFIG.outer.radius;
      default: return RING_CONFIG.middle.radius;
    }
  }, []);

  // Get collision radius for a node (per spec: 20 + confidence * 40)
  const getCollisionRadius = useCallback((confidence: number) => {
    return 20 + confidence * 40;
  }, []);

  // Initialize node states when data changes (with random jitter per spec)
  useEffect(() => {
    const newStates = new Map<string, NodeState>();
    const totalNodes = data.nodes.length;
    
    data.nodes.forEach((node, index) => {
      const existing = nodeStates.get(node.id);
      const orbitalRadius = getOrbitalRadius(node.match_type);
      
      if (existing) {
        // Keep existing position but update target radius
        newStates.set(node.id, {
          ...existing,
          targetRadius: orbitalRadius,
        });
      } else {
        // Initial position with jitter (per spec)
        const angle = (index / totalNodes) * 2 * Math.PI - Math.PI / 2;
        const jitter = (Math.random() - 0.5) * 40;
        newStates.set(node.id, {
          x: centerX + Math.cos(angle) * (orbitalRadius + jitter),
          y: centerY + Math.sin(angle) * (orbitalRadius + jitter),
          vx: (Math.random() - 0.5) * 2,  // Small initial velocity for organic feel
          vy: (Math.random() - 0.5) * 2,
          targetRadius: orbitalRadius,
          fx: null,
          fy: null,
        });
      }
    });
    
    setNodeStates(newStates);
    alphaRef.current = 1.0;  // Restart simulation on data change
  }, [data.nodes, centerX, centerY, getOrbitalRadius]);

  // Physics simulation loop with D3-style forces (per spec)
  useEffect(() => {
    const CHARGE_STRENGTH = -200;      // Repulsion between nodes
    const CENTER_STRENGTH = 0.01;      // Weak attraction to center
    const RADIAL_STRENGTH = 0.6;       // Pull toward orbital ring
    const ALPHA_DECAY = 0.015;         // Slow decay for organic settling
    const VELOCITY_DECAY = 0.4;        // Friction

    const simulate = () => {
      // Alpha decay (per spec)
      alphaRef.current += (alphaTargetRef.current - alphaRef.current) * ALPHA_DECAY;
      
      if (alphaRef.current < 0.001) {
        alphaRef.current = 0;
      }

      setNodeStates(prev => {
        const next = new Map(prev);
        const nodes = Array.from(next.entries());

        // Apply forces to each node
        nodes.forEach(([nodeId, state]) => {
          // Skip fixed nodes (being dragged)
          if (state.fx !== null && state.fy !== null) {
            state.x = state.fx;
            state.y = state.fy;
            return;
          }

          let forceX = 0;
          let forceY = 0;

          // 1. Charge force - repulsion from other nodes (per spec)
          nodes.forEach(([otherId, otherState]) => {
            if (nodeId === otherId) return;
            const dx = state.x - otherState.x;
            const dy = state.y - otherState.y;
            const distSq = dx * dx + dy * dy;
            const dist = Math.sqrt(distSq);
            if (dist > 0 && dist < 200) {
              const force = (CHARGE_STRENGTH * alphaRef.current) / distSq;
              forceX -= force * dx;
              forceY -= force * dy;
            }
          });

          // 2. Center force - weak attraction to center (per spec)
          const toCenterX = centerX - state.x;
          const toCenterY = centerY - state.y;
          forceX += toCenterX * CENTER_STRENGTH * alphaRef.current;
          forceY += toCenterY * CENTER_STRENGTH * alphaRef.current;

          // 3. Radial force - pull toward orbital ring (per spec)
          const distFromCenter = Math.sqrt(
            (state.x - centerX) ** 2 + (state.y - centerY) ** 2
          );
          if (distFromCenter > 0) {
            const radialDiff = state.targetRadius - distFromCenter;
            const radialForce = radialDiff * RADIAL_STRENGTH * alphaRef.current;
            const angle = Math.atan2(state.y - centerY, state.x - centerX);
            forceX += Math.cos(angle) * radialForce;
            forceY += Math.sin(angle) * radialForce;
          }

          // 4. Collision force - prevent overlap (per spec)
          const node = data.nodes.find(n => n.id === nodeId);
          const myRadius = node ? getCollisionRadius(node.confidence) : 30;
          
          nodes.forEach(([otherId, otherState]) => {
            if (nodeId === otherId) return;
            const otherNode = data.nodes.find(n => n.id === otherId);
            const otherRadius = otherNode ? getCollisionRadius(otherNode.confidence) : 30;
            const minDist = myRadius + otherRadius;
            
            const dx = state.x - otherState.x;
            const dy = state.y - otherState.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            
            if (dist < minDist && dist > 0) {
              const overlap = (minDist - dist) / dist * 0.5;
              forceX += dx * overlap * alphaRef.current;
              forceY += dy * overlap * alphaRef.current;
            }
          });

          // Apply forces to velocity
          state.vx += forceX;
          state.vy += forceY;

          // Velocity decay (friction)
          state.vx *= (1 - VELOCITY_DECAY);
          state.vy *= (1 - VELOCITY_DECAY);

          // Update position
          state.x += state.vx;
          state.y += state.vy;
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
  }, [data.nodes, centerX, centerY, getCollisionRadius]);

  // Get current position for a node
  const getNodePosition = useCallback((nodeId: string) => {
    const state = nodeStates.get(nodeId);
    if (state) {
      return { x: state.x, y: state.y };
    }
    return { x: centerX, y: centerY };
  }, [nodeStates, centerX, centerY]);

  // Drag handlers (per spec)
  const handleMouseDown = useCallback((e: React.MouseEvent, node: IntentNode) => {
    e.preventDefault();
    e.stopPropagation();
    setDraggedNodeId(node.id);
    setHoveredNode(null);
    setHoveredPosition(null);
    
    // Reheat simulation on drag start (per spec)
    alphaTargetRef.current = 0.3;
    alphaRef.current = Math.max(alphaRef.current, 0.3);
    
    // Fix node position
    setNodeStates(prev => {
      const next = new Map(prev);
      const state = next.get(node.id);
      if (state) {
        state.fx = state.x;
        state.fy = state.y;
      }
      return next;
    });
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!draggedNodeId || !svgRef.current) return;

    const svgRect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - svgRect.left;
    const mouseY = e.clientY - svgRect.top;

    // Update fixed position during drag
    setNodeStates(prev => {
      const next = new Map(prev);
      const state = next.get(draggedNodeId);
      if (state) {
        state.fx = mouseX;
        state.fy = mouseY;
        state.x = mouseX;
        state.y = mouseY;
        state.vx = 0;
        state.vy = 0;
      }
      return next;
    });
  }, [draggedNodeId]);

  const handleMouseUp = useCallback(() => {
    if (draggedNodeId) {
      // Release fixed position and cool down simulation (per spec)
      setNodeStates(prev => {
        const next = new Map(prev);
        const state = next.get(draggedNodeId);
        if (state) {
          state.fx = null;
          state.fy = null;
        }
        return next;
      });
      
      // Cool down simulation
      alphaTargetRef.current = 0;
    }
    setDraggedNodeId(null);
  }, [draggedNodeId]);

  const handleMouseLeave = useCallback(() => {
    if (draggedNodeId) {
      // Release fixed position
      setNodeStates(prev => {
        const next = new Map(prev);
        const state = next.get(draggedNodeId);
        if (state) {
          state.fx = null;
          state.fy = null;
        }
        return next;
      });
      alphaTargetRef.current = 0;
    }
    setDraggedNodeId(null);
    setHoveredNode(null);
    setHoveredPosition(null);
  }, [draggedNodeId]);

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

      {/* Main content area - three column layout */}
      <div className="flex-1 flex min-h-0">
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
        <div className="flex-1 flex items-center justify-center p-4 overflow-hidden">
          <svg
            ref={svgRef}
            width={width}
            height={height}
            className="galaxy-svg"
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseLeave}
          >
            {/* Gradient and filter definitions */}
            <defs>
              {/* Background nebula gradient per spec */}
              <radialGradient id="nebulaGradient" cx="50%" cy="50%" r="60%">
                <stop offset="0%" stopColor="#1a1f3c" stopOpacity="0.8" />
                <stop offset="40%" stopColor="#0f1424" stopOpacity="0.5" />
                <stop offset="100%" stopColor="#080b12" stopOpacity="1" />
              </radialGradient>
              
              {/* Ring glow effect */}
              <filter id="ringGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              
              {/* Node glow filters for each domain */}
              <filter id="glowFinance" x="-100%" y="-100%" width="300%" height="300%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feFlood floodColor="#4facfe" floodOpacity="0.4" />
                <feComposite in2="blur" operator="in" />
                <feMerge>
                  <feMergeNode />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="glowGrowth" x="-100%" y="-100%" width="300%" height="300%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feFlood floodColor="#f093fb" floodOpacity="0.4" />
                <feComposite in2="blur" operator="in" />
                <feMerge>
                  <feMergeNode />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="glowOps" x="-100%" y="-100%" width="300%" height="300%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feFlood floodColor="#43e97b" floodOpacity="0.4" />
                <feComposite in2="blur" operator="in" />
                <feMerge>
                  <feMergeNode />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="glowProduct" x="-100%" y="-100%" width="300%" height="300%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feFlood floodColor="#fa709a" floodOpacity="0.4" />
                <feComposite in2="blur" operator="in" />
                <feMerge>
                  <feMergeNode />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="glowPeople" x="-100%" y="-100%" width="300%" height="300%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feFlood floodColor="#fee140" floodOpacity="0.4" />
                <feComposite in2="blur" operator="in" />
                <feMerge>
                  <feMergeNode />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>
            
            {/* Background */}
            <rect width={width} height={height} fill="#080b12" />
            <rect width={width} height={height} fill="url(#nebulaGradient)" />

            {/* Orbital Rings with glow (per spec) */}
            {/* Outer ring glow */}
            <circle
              cx={centerX}
              cy={centerY}
              r={RING_CONFIG.outer.radius}
              fill="none"
              stroke="rgba(79, 172, 254, 0.1)"
              strokeWidth="8"
              filter="url(#ringGlow)"
            />
            {/* Outer ring */}
            <circle
              cx={centerX}
              cy={centerY}
              r={RING_CONFIG.outer.radius}
              fill="none"
              stroke={RING_CONFIG.outer.strokeColor}
              strokeWidth="1"
              strokeDasharray="8 4"
            />
            {/* Middle ring glow */}
            <circle
              cx={centerX}
              cy={centerY}
              r={RING_CONFIG.middle.radius}
              fill="none"
              stroke="rgba(79, 172, 254, 0.1)"
              strokeWidth="8"
              filter="url(#ringGlow)"
            />
            {/* Middle ring */}
            <circle
              cx={centerX}
              cy={centerY}
              r={RING_CONFIG.middle.radius}
              fill="none"
              stroke={RING_CONFIG.middle.strokeColor}
              strokeWidth="1"
              strokeDasharray="8 4"
            />
            {/* Core ring (solid) */}
            <circle
              cx={centerX}
              cy={centerY}
              r={RING_CONFIG.inner.radius}
              fill="none"
              stroke={RING_CONFIG.inner.strokeColor}
              strokeWidth="1"
            />

            {/* Ring Labels */}
            <text
              x={centerX}
              y={centerY - RING_CONFIG.inner.radius - 8}
              textAnchor="middle"
              fill="rgba(79, 172, 254, 0.6)"
              fontSize="9"
              fontFamily="monospace"
            >
              CORE
            </text>
            <text
              x={centerX}
              y={centerY - RING_CONFIG.middle.radius - 8}
              textAnchor="middle"
              fill="rgba(79, 172, 254, 0.5)"
              fontSize="9"
              fontFamily="monospace"
            >
              INNER
            </text>
            <text
              x={centerX}
              y={centerY - RING_CONFIG.outer.radius - 8}
              textAnchor="middle"
              fill="rgba(79, 172, 254, 0.4)"
              fontSize="9"
              fontFamily="monospace"
            >
              OUTER
            </text>

            {/* Connection lines from center to nodes */}
            {data.nodes.map((node) => {
              const pos = getNodePosition(node.id);
              const color = DOMAIN_COLORS[node.domain] || DOMAIN_COLORS.finance;
              const typeStyle = getTypeStyle(node.match_type, node.id === data.primary_node_id);
              const lineOpacity = 0.1 + (node.confidence * 0.15);
              
              return (
                <line
                  key={`line-${node.id}`}
                  x1={centerX}
                  y1={centerY}
                  x2={pos.x}
                  y2={pos.y}
                  stroke={color}
                  strokeWidth={typeStyle.strokeWidth * 0.5}
                  strokeOpacity={lineOpacity}
                  strokeDasharray={typeStyle.dashArray === 'none' ? undefined : typeStyle.dashArray}
                />
              );
            })}

            {/* Center - Persona Indicator (per spec) */}
            <g transform={`translate(${centerX}, ${centerY})`}>
              {/* Outer glow circle */}
              <circle
                r={45}
                fill="rgba(79, 172, 254, 0.08)"
                stroke="rgba(79, 172, 254, 0.4)"
                strokeWidth="1"
              />
              {/* Inner circle */}
              <circle
                r={30}
                fill="rgba(15, 20, 36, 0.9)"
                stroke="#4facfe"
                strokeWidth="2"
              />
              {/* Persona name */}
              <text
                textAnchor="middle"
                dy="-0.1em"
                fill="#4facfe"
                fontSize="11"
                fontWeight="bold"
              >
                {data.persona || data.nodes[0]?.domain?.toUpperCase() || 'NLQ'}
              </text>
              {/* PERSONA label */}
              <text
                textAnchor="middle"
                dy="1.3em"
                fill="rgba(79, 172, 254, 0.6)"
                fontSize="8"
                fontFamily="monospace"
              >
                PERSONA
              </text>
            </g>

            {/* Nodes (per spec) */}
            {data.nodes.map((node) => {
              const pos = getNodePosition(node.id);
              const isPrimary = node.id === data.primary_node_id;
              const isSelected = selectedNode?.id === node.id;
              const isHovered = hoveredNode?.id === node.id;
              const isDragging = draggedNodeId === node.id;
              const baseRadius = getCircleRadius(node.confidence, isPrimary);
              // Hover pulse: +4px per spec
              const radius = isHovered ? baseRadius + 4 : baseRadius;
              const qualityRingRadius = getQualityRingRadius(node.confidence);
              const innerRadius = getInnerHighlightRadius(node.confidence);
              const color = DOMAIN_COLORS[node.domain] || DOMAIN_COLORS.finance;
              const typeStyle = getTypeStyle(node.match_type, isPrimary);
              
              // Get glow filter based on domain
              const glowFilter = {
                finance: 'url(#glowFinance)',
                growth: 'url(#glowGrowth)',
                ops: 'url(#glowOps)',
                product: 'url(#glowProduct)',
                people: 'url(#glowPeople)',
              }[node.domain] || 'url(#glowFinance)';
              
              // Confidence label prefix (per spec)
              const confidencePrefix = node.confidence > 0.9 ? 'Exact: ' : node.confidence > 0.7 ? 'Likely: ' : 'Potential: ';
              const prefixColor = node.confidence > 0.9 ? '#43e97b' : node.confidence > 0.7 ? '#fee140' : '#64748b';

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
                      r={radius + 10}
                      fill="none"
                      stroke={isSelected ? '#fff' : 'rgba(255,255,255,0.4)'}
                      strokeWidth={isSelected ? 2 : 1}
                      opacity={0.8}
                    />
                  )}

                  {/* Data quality ring (outer arc per spec) */}
                  <path
                    d={getArcPath(0, 0, qualityRingRadius, node.data_quality)}
                    fill="none"
                    stroke={color}
                    strokeWidth="3"
                    strokeLinecap="round"
                    opacity={node.data_quality * 0.6}
                    style={{ transform: 'rotate(-90deg)', transformOrigin: 'center' }}
                  />

                  {/* Main circle with glow */}
                  <circle
                    r={radius}
                    fill={color}
                    opacity={typeStyle.opacity}
                    stroke={color}
                    strokeWidth={typeStyle.strokeWidth}
                    strokeDasharray={typeStyle.dashArray === 'none' ? undefined : typeStyle.dashArray}
                    filter={isPrimary || isHovered ? glowFilter : undefined}
                    style={{ transition: 'r 150ms ease-out' }}
                  />

                  {/* Inner highlight (per spec) */}
                  <circle
                    r={innerRadius}
                    fill="none"
                    stroke="rgba(255,255,255,0.35)"
                    strokeWidth="1"
                  />

                  {/* Freshness dot (per spec - top right) */}
                  <circle
                    cx={radius * 0.7}
                    cy={-radius * 0.7}
                    r={5}
                    fill={getFreshnessColor(node.freshness)}
                    stroke="#0f1424"
                    strokeWidth="2"
                  />

                  {/* Confidence percentage (per spec) */}
                  <text
                    textAnchor="middle"
                    dy="0.35em"
                    fill="rgba(255,255,255,0.95)"
                    fontSize={node.confidence > 0.6 ? 13 : 10}
                    fontWeight="bold"
                    fontFamily="monospace"
                    style={{ pointerEvents: 'none' }}
                  >
                    {Math.round(node.confidence * 100)}%
                  </text>

                  {/* Semantic label with prefix (per spec) */}
                  <text
                    y={22 + (node.confidence * 32)}
                    textAnchor="middle"
                    fontSize="10"
                    fontWeight="500"
                    style={{ pointerEvents: 'none' }}
                  >
                    <tspan fill={prefixColor}>{confidencePrefix}</tspan>
                    <tspan fill="#94a3b8">{node.display_name}{node.confidence <= 0.7 ? '?' : ''}</tspan>
                  </text>

                  {/* Type badge (per spec) */}
                  <text
                    y={36 + (node.confidence * 32)}
                    textAnchor="middle"
                    fill="#64748b"
                    fontSize="8"
                    fontFamily="monospace"
                    style={{ pointerEvents: 'none', textTransform: 'uppercase' }}
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
