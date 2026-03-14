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
import { ProvenanceBadge } from './ProvenanceBadge';
import { DataTable } from './DataTable';

interface GalaxyViewProps {
  data: IntentMapResponse;
  width?: number;
  height?: number;
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
  width: propWidth,
  height: propHeight,
}) => {
  const [selectedNode, setSelectedNode] = useState<IntentNode | null>(null);
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);
  const [nodeStates, setNodeStates] = useState<Map<string, NodeState>>(new Map());
  const [leftPanelOpen, setLeftPanelOpen] = useState(false);

  // Auto-open left panel when any query result arrives (close only for funny/easter egg responses)
  useEffect(() => {
    if (data && data.query_type === 'OFF_TOPIC' && data.nodes.length === 0) {
      setLeftPanelOpen(false);
    } else if (data) {
      setLeftPanelOpen(true);
    }
  }, [data]);

  // Track drag to differentiate from click
  const dragStartPos = useRef<{ x: number; y: number } | null>(null);
  const hasDragged = useRef(false);

  // Container ref for measuring available space
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerSize, setContainerSize] = useState({ width: propWidth || 700, height: propHeight || 700 });

  // Use container size or props
  const width = propWidth || containerSize.width;
  const height = propHeight || containerSize.height;

  // Measure container and update size
  useEffect(() => {
    if (propWidth && propHeight) return; // Skip if explicit dimensions provided

    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        // Use the smaller dimension to keep it square, or use both for non-square
        if (rect.width > 0 && rect.height > 0) {
          setContainerSize({ width: rect.width, height: rect.height });
        }
      }
    };

    updateSize();

    const resizeObserver = new ResizeObserver(updateSize);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => resizeObserver.disconnect();
  }, [propWidth, propHeight]);

  // Mobile bottom sheet state
  const [sheetState, setSheetState] = useState<SheetState>('collapsed');
  const [isDraggingSheet, setIsDraggingSheet] = useState(false);
  const [sheetDragStart, setSheetDragStart] = useState<number>(0);
  const [sheetDragOffset, setSheetDragOffset] = useState<number>(0);
  const sheetRef = useRef<HTMLDivElement>(null);

  const isFunnyResponse = data.query_type === 'OFF_TOPIC' && data.nodes.length === 0 && !!data.text_response;
  const isTextOnlyResponse = !isFunnyResponse && data.query_type !== 'OFF_TOPIC' && data.nodes.length === 0 && !!data.text_response;

  const svgRef = useRef<SVGSVGElement>(null);

  const centerX = width / 2;
  const centerY = height / 2;

  // Calculate scale factor to fit visualization in container
  // Base design assumes 320 (outer ring) + 50 (node radius + padding) = 370 radius needed
  const baseRadius = 370;
  const availableRadius = Math.min(width, height) / 2 - 20; // 20px margin from edge
  // Ensure minimum scale of 0.6 to prevent rings from collapsing together
  const scale = Math.max(0.6, availableRadius / baseRadius);

  // Scaled ring radii
  const ringRadii = useMemo(() => ({
    inner: RING_CONFIG.inner.radius * scale,
    middle: RING_CONFIG.middle.radius * scale,
    outer: RING_CONFIG.outer.radius * scale,
  }), [scale]);

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

    placeNodesOnRing(inner, ringRadii.inner);
    placeNodesOnRing(middle, ringRadii.middle);
    placeNodesOnRing(outer, ringRadii.outer);

    return positions;
  }, [data.nodes, centerX, centerY, ringRadii]);

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

  // Animation removed — nodes are positioned statically (no orbit wobble)

  // Get current position for a node (static — no orbit wobble)
  const getNodePosition = useCallback((nodeId: string, _nodeIndex: number) => {
    const state = nodeStates.get(nodeId);
    const basePos = state
      ? { x: state.targetX, y: state.targetY }
      : (targetPositions.get(nodeId) || { x: centerX, y: centerY });

    // If being dragged, use exact drag position
    if (draggedNodeId === nodeId && state) {
      return { x: state.x, y: state.y };
    }

    return basePos;
  }, [nodeStates, targetPositions, centerX, centerY, draggedNodeId]);

  // Drag handlers
  const handleMouseDown = useCallback((e: React.MouseEvent, node: IntentNode, nodeIndex: number) => {
    e.preventDefault();
    e.stopPropagation();
    dragStartPos.current = { x: e.clientX, y: e.clientY };
    hasDragged.current = false;

    // Capture current visual position to prevent jump on drag start
    const target = targetPositions.get(node.id) || { x: centerX, y: centerY };
    const currentX = target.x;
    const currentY = target.y;

    setNodeStates(prev => {
      const next = new Map(prev);
      const existing = next.get(node.id);
      next.set(node.id, {
        x: currentX,
        y: currentY,
        vx: 0,
        vy: 0,
        targetX: existing?.targetX ?? target.x,
        targetY: existing?.targetY ?? target.y,
      });
      return next;
    });

    // Set dragged node after updating position to prevent flicker
    setDraggedNodeId(node.id);
  }, [targetPositions, centerX, centerY]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!draggedNodeId || !svgRef.current) return;

    // Check if moved enough to count as drag
    if (dragStartPos.current) {
      const dx = e.clientX - dragStartPos.current.x;
      const dy = e.clientY - dragStartPos.current.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
        hasDragged.current = true;
      }
    }

    const svgRect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - svgRect.left;
    const mouseY = e.clientY - svgRect.top;

    setNodeStates(prev => {
      const next = new Map(prev);
      const state = next.get(draggedNodeId);
      if (state) {
        state.x = mouseX;
        state.y = mouseY;
      }
      return next;
    });
  }, [draggedNodeId]);

  const handleMouseUp = useCallback(() => {
    // Update target position to where the node was dropped (so it stays there)
    if (draggedNodeId && hasDragged.current) {
      setNodeStates(prev => {
        const next = new Map(prev);
        const state = next.get(draggedNodeId);
        if (state) {
          state.targetX = state.x;
          state.targetY = state.y;
        }
        return next;
      });
    }
    setDraggedNodeId(null);
  }, [draggedNodeId]);

  // Reset all nodes to their original orbital positions
  const handleResetPositions = useCallback(() => {
    setNodeStates(prev => {
      const next = new Map(prev);
      next.forEach((state, nodeId) => {
        const originalTarget = targetPositions.get(nodeId);
        if (originalTarget) {
          state.targetX = originalTarget.x;
          state.targetY = originalTarget.y;
        }
      });
      return next;
    });
  }, [targetPositions]);

  const handleMouseLeave = useCallback(() => {
    setDraggedNodeId(null);
    dragStartPos.current = null;
    hasDragged.current = false;
  }, []);

  const handleNodeClick = useCallback((node: IntentNode) => {
    // Only open panel if this was a click, not a drag
    if (!hasDragged.current) {
      setSelectedNode(prev => prev?.id === node.id ? null : node);
    }
    // Reset drag state
    hasDragged.current = false;
    dragStartPos.current = null;
  }, []);

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
            {/* Plain dark background */}
            <rect width={width} height={height} fill="#0f172a" />

            {/* Center - Query */}
            <g transform={`translate(${centerX}, ${centerY})`}>
              <circle
                r={50 * scale}
                fill="rgba(59, 130, 246, 0.15)"
                stroke="#3B82F6"
                strokeWidth="2"
              />
              {/* Query text with wrapping */}
              {(() => {
                const query = data.query || 'Query';
                const maxWidth = 80 * scale; // Approximate max width for text
                const fontSize = 11;
                const lineHeight = 14;
                // Simple word wrapping - split into lines
                const words = query.split(' ');
                const lines: string[] = [];
                let currentLine = '';

                words.forEach(word => {
                  const testLine = currentLine ? `${currentLine} ${word}` : word;
                  // Rough estimate: ~6px per character at fontSize 11
                  if (testLine.length * 6 > maxWidth && currentLine) {
                    lines.push(currentLine);
                    currentLine = word;
                  } else {
                    currentLine = testLine;
                  }
                });
                if (currentLine) lines.push(currentLine);

                // Limit to 4 lines max and truncate if needed
                const maxLines = 4;
                const displayLines = lines.slice(0, maxLines);
                if (lines.length > maxLines) {
                  displayLines[maxLines - 1] = displayLines[maxLines - 1].slice(0, -3) + '...';
                }

                const totalHeight = displayLines.length * lineHeight;
                const startY = -totalHeight / 2 + lineHeight / 2;

                return displayLines.map((line, i) => (
                  <text
                    key={i}
                    textAnchor="middle"
                    y={startY + i * lineHeight}
                    dy="0.35em"
                    fill="#fff"
                    fontSize={fontSize}
                    fontWeight="500"
                  >
                    {line}
                  </text>
                ));
              })()}
            </g>

            {/* Nodes */}
            {data.nodes.map((node, nodeIndex) => {
              const pos = getNodePosition(node.id, nodeIndex);
              const isPrimary = node.id === data.primary_node_id;
              const isSelected = selectedNode?.id === node.id;
              const isDragging = draggedNodeId === node.id;
              // Scale node radius with the same factor as rings to prevent overlap when container is small
              const radius = getCircleRadius(node.confidence, isPrimary) * scale;
              const color = DOMAIN_COLORS[node.domain] || DOMAIN_COLORS.finance;
              const arcRadius = radius + 6 * scale;

              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x}, ${pos.y})`}
                  onClick={() => handleNodeClick(node)}
                  onMouseDown={(e) => handleMouseDown(e, node, nodeIndex)}
                  style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
                  className="galaxy-node"
                >
                  {/* Selection/hover ring */}
                  {isSelected && (
                    <circle
                      r={radius + 12 * scale}
                      fill="none"
                      stroke="#fff"
                      strokeWidth={2}
                      opacity={isSelected ? 0.8 : 0.5}
                    />
                  )}

                  {/* Main circle */}
                  <circle
                    r={radius}
                    fill={color}
                    opacity={isSelected ? 1 : 0.9}
                    stroke={isPrimary ? '#fff' : 'none'}
                    strokeWidth={isPrimary ? 2 : 0}
                  />

                  {/* Data quality arc */}
                  <path
                    d={getArcPath(0, 0, arcRadius, node.data_quality)}
                    fill="none"
                    stroke="#4ade80"
                    strokeWidth={Math.max(2, 3 * scale)}
                    strokeLinecap="round"
                    opacity="0.9"
                  />

                  {/* Freshness dot */}
                  <circle
                    cx={radius * 0.7}
                    cy={-radius * 0.7}
                    r={Math.max(3, 5 * scale)}
                    fill={getFreshnessColor(node.freshness, node.metric)}
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

                  {/* Label below node - just the metric name */}
                  <text
                    y={radius + 18 * scale}
                    textAnchor="middle"
                    fill="#94a3b8"
                    fontSize={Math.max(8, 10 * scale)}
                    fontWeight="500"
                    style={{ pointerEvents: 'none' }}
                  >
                    {node.display_name}
                  </text>
                </g>
              );
            })}

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
        <div className="flex-1 flex items-center justify-center p-2 overflow-hidden min-h-0 relative">
          {svgContent}
          {isFunnyResponse && (
            <div className="absolute inset-0 flex items-center justify-center z-30 pointer-events-none">
              <div className="pointer-events-auto max-w-sm mx-4 px-6 py-5 rounded-2xl bg-gradient-to-br from-slate-800/95 to-slate-900/95 border border-blue-500/30 shadow-[0_0_40px_rgba(59,130,246,0.15)] backdrop-blur-sm">
                <p className="text-slate-100 text-base leading-relaxed font-medium whitespace-pre-line">
                  {data.text_response}
                </p>
              </div>
            </div>
          )}
          {isTextOnlyResponse && (
            <div className="absolute inset-0 flex items-center justify-center z-30 pointer-events-none">
              <div className="pointer-events-auto max-w-sm mx-4 px-6 py-5 rounded-2xl bg-gradient-to-br from-slate-800/95 to-slate-900/95 border border-slate-500/30 shadow-[0_0_40px_rgba(100,116,139,0.15)] backdrop-blur-sm">
                <p className="text-slate-200 text-base leading-relaxed whitespace-pre-line">
                  {data.text_response}
                </p>
              </div>
            </div>
          )}
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
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                    Answer
                  </h3>
                  <ProvenanceBadge provenance={data.provenance} compact />
                </div>
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
                provenance={data.provenance}
              />
            </div>
          </div>
        )}
      </div>

      {/* ============ DESKTOP LAYOUT ============ */}
      <div className="hidden md:flex flex-1 min-h-0 overflow-hidden">
        {/* Left Panel Toggle Button — always visible */}
        <button
          onClick={() => setLeftPanelOpen(!leftPanelOpen)}
          className="flex-shrink-0 flex items-center justify-center w-6 bg-slate-900/60 hover:bg-slate-800/80 border-r border-slate-800 transition-colors cursor-pointer"
          title={leftPanelOpen ? 'Collapse panel' : 'Expand panel'}
        >
          <svg className="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {leftPanelOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            )}
          </svg>
        </button>

        {/* Left Panel - Text Response & Data Table (collapsible, collapsed on load) */}
        <div
          className={`flex-shrink-0 flex flex-col border-r border-slate-800 bg-slate-900/30 transition-all duration-300 overflow-hidden ${
            leftPanelOpen ? 'w-[293px]' : 'w-0'
          }`}
        >
          {/* Text Answer - Top Left */}
          {data.text_response && !isFunnyResponse && (
            <div className="p-4 border-b border-slate-800/50 min-w-[293px]">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Answer
                </h3>
                <ProvenanceBadge provenance={data.provenance} compact />
              </div>
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
            <div className="flex-1 overflow-auto p-3 min-w-[293px]">
              <DataTable nodes={data.nodes} title="Data Points" />
            </div>
          )}

          {/* Legend at bottom of left panel */}
          <div className="mt-auto border-t border-slate-800/50 min-w-[293px]">
            <GalaxyLegend compact />
          </div>
        </div>

        {/* Center - SVG Visualization */}
        <div ref={containerRef} className="flex-1 flex items-center justify-center overflow-hidden min-h-0 relative">
          {svgContent}
          {isFunnyResponse && (
            <div className="absolute inset-0 flex items-center justify-center z-30 pointer-events-none">
              <div className="pointer-events-auto max-w-md px-8 py-6 rounded-2xl bg-gradient-to-br from-slate-800/95 to-slate-900/95 border border-blue-500/30 shadow-[0_0_60px_rgba(59,130,246,0.2)] backdrop-blur-sm animate-[fadeIn_0.4s_ease-out]">
                <p className="text-slate-100 text-lg leading-relaxed font-medium whitespace-pre-line">
                  {data.text_response}
                </p>
              </div>
            </div>
          )}
          {isTextOnlyResponse && (
            <div className="absolute inset-0 flex items-center justify-center z-30 pointer-events-none">
              <div className="pointer-events-auto max-w-md px-8 py-6 rounded-2xl bg-gradient-to-br from-slate-800/95 to-slate-900/95 border border-slate-500/30 shadow-[0_0_60px_rgba(100,116,139,0.2)] backdrop-blur-sm animate-[fadeIn_0.4s_ease-out]">
                <p className="text-slate-200 text-lg leading-relaxed whitespace-pre-line">
                  {data.text_response}
                </p>
              </div>
            </div>
          )}
          {/* Reset button - appears in top right of visualization */}
          <button
            onClick={handleResetPositions}
            className="absolute top-4 right-4 px-3 py-1.5 text-xs bg-slate-800/80 hover:bg-slate-700 text-slate-300 rounded-md border border-slate-600/50 transition-colors"
            title="Reset node positions"
          >
            Reset
          </button>
        </div>

        {/* Right Panel - Node Detail Panel */}
        {selectedNode && (
          <NodeDetailPanel
            node={selectedNode}
            isPrimary={selectedNode.id === data.primary_node_id}
            onClose={() => setSelectedNode(null)}
            provenance={data.provenance}
          />
        )}
      </div>
    </div>
  );
};
