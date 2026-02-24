/**
 * DashboardRenderer - Schema-driven dashboard rendering
 *
 * Features:
 * - Natural language dashboard generation and refinement
 * - Reset to start over
 * - Save dashboard / Save as template
 * - Drag-and-drop layout editing with react-grid-layout
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import GridLayout from 'react-grid-layout/legacy';
import { useQueryRouter } from '../../hooks/useQueryRouter';
import { useDashboardRefinement } from '../../hooks/useDashboardRefinement';
import { DashboardErrorBoundary } from './DashboardErrorBoundary';
import { useDashboardLayout } from '../../hooks/useDashboardLayout';
import {
  useDashboardPersistence,
  getSavedDashboards,
  getSavedTemplates,
  deleteSavedDashboard,
  deleteSavedTemplate,
  SavedDashboard,
  SavedTemplate,
} from '../../hooks/useDashboardPersistence';
import 'react-grid-layout/css/styles.css';
import {
  DashboardSchema,
  Widget,
  WidgetData,
  DashboardGenerationResponse,
} from '../../types/generated-dashboard';
import { WidgetRenderer } from './WidgetRenderer';
import { ScenarioModelingPanel } from './ScenarioModelingPanel';
import { generateMockWidgetData } from './mockData';

interface PersonaOption {
  label: string;
  value: string;
}

interface DashboardRendererProps {
  /** Initial schema to render (optional - can start empty) */
  initialSchema?: DashboardSchema;
  /** Pre-resolved widget data from backend (uses real fact base data) */
  initialWidgetData?: Record<string, WidgetData>;
  /** Query that generated the dashboard */
  sourceQuery?: string;
  /** Callback when a drill-down is triggered */
  onDrillDown?: (query: string) => void;
  /** Callback when dashboard is refined - includes schema and widget data for parent sync */
  onRefinement?: (newSchema: DashboardSchema, widgetData?: Record<string, WidgetData>) => void;
  /** Callback when a factual query should navigate to Galaxy space */
  onNavigateToGalaxy?: (query: string) => void;
  /** Show refinement input */
  showRefinementInput?: boolean;
  /** Persona-specific preset refinement suggestions */
  refinePresets?: string[];
  /** Current persona (for showing what-if panel) */
  persona?: 'CFO' | 'CRO' | 'COO' | 'CTO' | 'CHRO' | string;
  /** Persona options for dropdown */
  personaOptions?: PersonaOption[];
  /** Callback when persona changes */
  onPersonaChange?: (persona: string) => void;
  /** Whether dashboard is being generated */
  isGenerating?: boolean;
  /** Data mode: 'live' for DCL, 'demo' for local fact_base.json */
  dataMode?: 'live' | 'demo';
}

// =============================================================================
// Forecast Comparison
// =============================================================================

import { ForecastComparison } from './ForecastComparison';
import type { ForecastRow } from './ForecastComparison';

// =============================================================================
// Main Component
// =============================================================================

/** Cap widget row_span and col_span at the schema level so every downstream consumer gets compact sizes */
function normalizeSchema(s: DashboardSchema): DashboardSchema {
  const maxH: Record<string, number> = { kpi_card: 2, data_table: 5, map: 3 };
  const maxW: Record<string, number> = { map: 6 };
  const defaultMaxH = 4; // charts
  const changed = s.widgets.some(w => {
    const capH = maxH[w.type] ?? defaultMaxH;
    const capW = maxW[w.type];
    return w.position.row_span > capH || (capW && w.position.col_span > capW);
  });
  if (!changed) return s;
  return {
    ...s,
    widgets: s.widgets.map(w => {
      const capH = maxH[w.type] ?? defaultMaxH;
      const capW = maxW[w.type];
      const needsH = w.position.row_span > capH;
      const needsW = capW && w.position.col_span > capW;
      if (!needsH && !needsW) return w;
      return { ...w, position: { ...w.position, row_span: needsH ? capH : w.position.row_span, col_span: (needsW && capW) ? capW : w.position.col_span } };
    }),
  };
}

export function DashboardRenderer({
  initialSchema,
  initialWidgetData,
  sourceQuery,
  onDrillDown,
  onRefinement,
  onNavigateToGalaxy,
  showRefinementInput = true,
  refinePresets = [],
  persona,
  personaOptions = [],
  onPersonaChange,
  isGenerating = false,
  dataMode = 'demo',
}: DashboardRendererProps) {
  // Query router for detecting factual queries that should go to Galaxy
  const { routeQuery } = useQueryRouter();
  const [schema, setSchemaRaw] = useState<DashboardSchema | null>(initialSchema ? normalizeSchema(initialSchema) : null);
  // Wrapper that always normalizes before setting
  const setSchema = useCallback((v: React.SetStateAction<DashboardSchema | null>) => {
    setSchemaRaw(prev => {
      const next = typeof v === 'function' ? v(prev) : v;
      return next ? normalizeSchema(next) : next;
    });
  }, []);
  // Use pre-resolved data from backend if available, otherwise empty (will fetch mock)
  const [widgetData, setWidgetData] = useState<Record<string, WidgetData>>(initialWidgetData || {});
  // Store the default (initial) schema and data for reset-to-default
  const defaultSchemaRef = useRef<DashboardSchema | null>(initialSchema ? normalizeSchema(initialSchema) : null);
  const defaultWidgetDataRef = useRef<Record<string, WidgetData>>(initialWidgetData || {});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initialQuery, setInitialQuery] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);

  // Drag-to-scroll for presets container on desktop
  const presetsRef = useRef<HTMLDivElement>(null);
  const [isDraggingPresets, setIsDraggingPresets] = useState(false);
  const [dragStartX, setDragStartX] = useState(0);
  const [scrollStartX, setScrollStartX] = useState(0);

  const handlePresetsMouseDown = useCallback((e: React.MouseEvent) => {
    if (!presetsRef.current) return;
    setIsDraggingPresets(true);
    setDragStartX(e.clientX);
    setScrollStartX(presetsRef.current.scrollLeft);
    presetsRef.current.style.cursor = 'grabbing';
    presetsRef.current.style.userSelect = 'none';
  }, []);

  const handlePresetsMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDraggingPresets || !presetsRef.current) return;
    const dx = e.clientX - dragStartX;
    presetsRef.current.scrollLeft = scrollStartX - dx;
  }, [isDraggingPresets, dragStartX, scrollStartX]);

  const handlePresetsMouseUp = useCallback(() => {
    setIsDraggingPresets(false);
    if (presetsRef.current) {
      presetsRef.current.style.cursor = 'grab';
      presetsRef.current.style.userSelect = '';
    }
  }, []);

  const handlePresetsMouseLeave = useCallback(() => {
    if (isDraggingPresets) {
      handlePresetsMouseUp();
    }
  }, [isDraggingPresets, handlePresetsMouseUp]);

  // Scenario modeling panel state (CFO only)
  const [scenarioOpen, setScenarioOpen] = useState(false);
  // Forecast comparison data — populated when user clicks "Apply to Forecast"
  const [forecastData, setForecastData] = useState<ForecastRow[] | null>(null);

  // Listen for tour event to open the What-If panel
  useEffect(() => {
    const handler = () => setScenarioOpen(true);
    window.addEventListener('tour:open-whatif', handler);
    return () => window.removeEventListener('tour:open-whatif', handler);
  }, []);

  const baseMetrics = useMemo(() => ({
    revenue: 150000000,
    revenueGrowthPct: 18,
    grossMarginPct: 65,
    operatingMarginPct: 30,
    netIncomePct: 22,
    headcount: 350,
    opex: 45000000,
  }), []);

  const {
    layoutMap,
    setLayoutMap,
    containerRef,
    containerWidth,
    editMode,
    setEditMode,
    gridLayout,
    handleLayoutChange,
    handleAutoArrange,
  } = useDashboardLayout({ schema, setSchema });

  // Fetch data for all widgets (uses pre-resolved data if available, otherwise mock)
  const fetchWidgetData = useCallback(async (
    dashboard: DashboardSchema,
    preResolvedData?: Record<string, WidgetData>
  ) => {
    const newData: Record<string, WidgetData> = {};
    for (const widget of dashboard.widgets) {
      // Use pre-resolved data from backend if available
      if (preResolvedData && preResolvedData[widget.id]) {
        newData[widget.id] = preResolvedData[widget.id];
      } else {
        // Fall back to mock data generation
        newData[widget.id] = await generateMockWidgetData(widget);
      }
    }
    setWidgetData(newData);
  }, []);

  // Persistence hook (save/load/template/test state and callbacks)
  const {
    showSaveModal,
    setShowSaveModal,
    showTemplateModal,
    setShowTemplateModal,
    showLoadModal,
    setShowLoadModal,
    showTestModal,
    setShowTestModal,
    saveName,
    setSaveName,
    templateName,
    setTemplateName,
    templateDesc,
    setTemplateDesc,
    saveSuccess,
    setSaveSuccess,
    testRunning,
    testResult,
    handleSave,
    handleSaveAsTemplate,
    handleLoad,
    handleRunTests,
  } = useDashboardPersistence({
    schema,
    layoutMap,
    widgetData,
    setSchema,
    setLayoutMap,
    setWidgetData,
    fetchWidgetData,
  });

  // Sync with initialSchema/initialWidgetData prop changes (for persona switching)
  useEffect(() => {
    if (initialSchema) {
      setSchema(initialSchema);
      setLayoutMap({}); // Clear custom positions when new schema is loaded
      setError(null);
      defaultSchemaRef.current = initialSchema;
    }
  }, [initialSchema]);

  useEffect(() => {
    if (initialWidgetData && Object.keys(initialWidgetData).length > 0) {
      setWidgetData(initialWidgetData);
      defaultWidgetDataRef.current = initialWidgetData;
    }
  }, [initialWidgetData]);

  // Initialize with pre-resolved data if provided (from /v1/query endpoint)
  useEffect(() => {
    if (initialSchema && initialWidgetData && Object.keys(initialWidgetData).length > 0) {
      // We have pre-resolved data from the backend - use it directly
      setSchema(initialSchema);
      setWidgetData(initialWidgetData);
    }
  }, [initialSchema, initialWidgetData]);

  // Generate dashboard from query
  const generateDashboard = useCallback(async (query: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/v1/query/dashboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query, data_mode: dataMode }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        setError(`API error (${response.status}): ${errorText.slice(0, 200)}`);
        return;
      }

      const data: DashboardGenerationResponse = await response.json();

      if (data.success && data.dashboard) {
        setSchema(data.dashboard);
        setSuggestions(data.suggestions || []);
        setLayoutMap({});
        // Use pre-resolved widget data from backend if available
        if (data.widget_data && Object.keys(data.widget_data).length > 0) {
          setWidgetData(data.widget_data);
        } else {
          // Fallback to loading + mock data if backend didn't provide data
          const initialData: Record<string, WidgetData> = {};
          data.dashboard.widgets.forEach(widget => {
            initialData[widget.id] = { loading: true };
          });
          setWidgetData(initialData);
          fetchWidgetData(data.dashboard);
        }

        // Auto-arrange on initial generation if not in edit mode
        if (!editMode) {
          setTimeout(() => {
            handleAutoArrange();
          }, 50);
        }
      } else {
        setError(data.error || 'Dashboard generation returned no data');
        setSuggestions(data.suggestions || []);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Request failed: ${message}`);
      console.error('Dashboard generation error:', err);
    } finally {
      setLoading(false);
    }
  }, [editMode, handleAutoArrange]);

  const {
    refinementQuery,
    setRefinementQuery,
    isRefining,
    refinementMessage,
    refineDashboard,
  } = useDashboardRefinement({
    schema,
    widgetData,
    setSchema,
    setWidgetData,
    fetchWidgetData,
    onRefinement,
    editMode,
    handleAutoArrange,
    dataMode,
  });

  // Reset dashboard — reverts to the default persona dashboard state
  const handleReset = useCallback(() => {
    if (defaultSchemaRef.current) {
      setSchema(defaultSchemaRef.current);
      setWidgetData(defaultWidgetDataRef.current);
      setLayoutMap({});
      setError(null);
      setSuggestions([]);
      setRefinementQuery('');
      setForecastData(null);
    } else {
      setSchema(null);
      setWidgetData({});
      setError(null);
      setSuggestions([]);
      setInitialQuery('');
      setRefinementQuery('');
      setLayoutMap({});
      setForecastData(null);
    }
  }, [setRefinementQuery]);

  // Remove a single widget
  const handleRemoveWidget = useCallback((widgetId: string) => {
    setSchema(prev => {
      if (!prev) return prev;
      const filtered = prev.widgets.filter(w => w.id !== widgetId);
      if (filtered.length === 0) return prev; // Don't allow removing the last widget
      return { ...prev, widgets: filtered };
    });
    setWidgetData(prev => {
      const next = { ...prev };
      delete next[widgetId];
      return next;
    });
    setLayoutMap(prev => {
      const next = { ...prev };
      delete next[widgetId];
      return next;
    });
  }, []);

  // Handle widget click (drill-down) — stays within dashboard (refines)
  const handleWidgetClick = useCallback((widget: Widget, value?: string) => {
    if (widget.type === 'kpi_card') {
      const metric = value || widget.data.metrics[0]?.metric || widget.title;
      const trendId = `trend_${metric}`;
      const altTrendId = `${metric}_trend`;
      const existingId = schema?.widgets.find(
        w => w.id === trendId || w.id === altTrendId
      )?.id;
      if (existingId) {
        // Scroll to the existing trend widget and flash-highlight it
        const el = document.querySelector(`[data-widget-id="${existingId}"]`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('ring-2', 'ring-cyan-400', 'transition-all');
          setTimeout(() => el.classList.remove('ring-2', 'ring-cyan-400', 'transition-all'), 1500);
        }
        return;
      }
      refineDashboard(`Add a quarterly trend chart for ${metric}`);
      return;
    }

    // For charts, drill into the clicked dimension as a dashboard refinement
    if (value) {
      const metric = widget.data.metrics[0]?.metric || 'data';
      refineDashboard(`Add a detail chart showing ${metric} for ${value}`);
    }
  }, [refineDashboard, schema]);

  // Handle KPI double-click to show time-based chart
  const handleKPIDoubleClick = useCallback((widget: Widget) => {
    const metric = widget.data.metrics[0]?.metric;
    if (metric) {
      // Trigger refinement to add a trend chart for this metric
      const refinementQuery = `Add a quarterly trend chart for ${widget.title || metric}`;
      refineDashboard(refinementQuery);
    }
  }, [refineDashboard]);

  // Handle refinement submit - route to Galaxy if factual, otherwise refine dashboard
  const handleRefinementSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const query = refinementQuery.trim();
    if (!query) return;

    // Check if this query should go to Galaxy (factual query)
    const routeResult = routeQuery(query, 'dashboard', !!schema);
    if (routeResult.destination === 'galaxy' && routeResult.confidence > 0.7 && onNavigateToGalaxy) {
      // This is a factual query - route to Galaxy space
      setRefinementQuery('');
      onNavigateToGalaxy(query);
      return;
    }

    // Dashboard query - refine the current dashboard
    refineDashboard(query);
  };

  // Handle suggestion click
  const handleSuggestionClick = (suggestion: string) => {
    const parts = suggestion.split(':');
    const query = parts.length > 1 ? parts[1].trim().replace(/^'|'$/g, '') : suggestion;
    setRefinementQuery(query);
  };

  // Generate dashboard on mount if sourceQuery provided
  useEffect(() => {
    if (sourceQuery && !schema) {
      generateDashboard(sourceQuery);
    }
  }, [sourceQuery, schema, generateDashboard]);

  const rowHeight = schema?.layout.row_height || 55;

  // State for mobile menu and desktop actions dropdown
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [showActionsMenu, setShowActionsMenu] = useState(false);

  return (
    <div className="h-full flex flex-col bg-slate-950">
      {/* Dashboard Header - Compact on mobile */}
      {schema && (
        <div className="px-4 md:px-6 py-2 md:py-3 border-b border-slate-800">
          <div className="flex items-center justify-between gap-2">
            {/* Mobile: Persona dropdown + menu button */}
            <div className="md:hidden flex items-center gap-2">
              {personaOptions.length > 0 && (
                <select
                  value={persona || ''}
                  onChange={(e) => onPersonaChange?.(e.target.value)}
                  disabled={isGenerating}
                  className="min-h-[36px] px-2 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-cyan-300 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500/50 disabled:opacity-50"
                >
                  {personaOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              )}
              <div className="relative">
                <button
                  onClick={() => setShowMobileMenu(!showMobileMenu)}
                  className="px-3 py-1.5 bg-slate-800 text-slate-300 rounded-lg text-sm hover:bg-slate-700 transition-colors"
                >
                  ⋮ Menu
                </button>
                {showMobileMenu && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowMobileMenu(false)} />
                    <div className="absolute right-0 top-full mt-1 z-50 bg-slate-800 border border-slate-700 rounded-lg shadow-xl py-1 min-w-[140px]">
                      <button onClick={() => { setEditMode(!editMode); setShowMobileMenu(false); }} className={`w-full px-4 py-2 text-left text-sm hover:bg-slate-700 ${editMode ? 'text-amber-300' : 'text-slate-300'}`}>
                        {editMode ? '✓ Edit Mode' : '⊞ Edit Layout'}
                      </button>
                      {persona === 'CFO' && (
                        <button onClick={() => { setScenarioOpen(true); setShowMobileMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-cyan-300 hover:bg-slate-700">📊 What-If</button>
                      )}
                      <button onClick={() => { handleAutoArrange(); setSaveSuccess('Layout auto-arranged!'); setTimeout(() => setSaveSuccess(null), 2000); setShowMobileMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700">⊞ Auto Arrange</button>
                      <button onClick={() => { setSaveName(schema.title); setShowSaveModal(true); setShowMobileMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700">💾 Save</button>
                      <button onClick={() => { setTemplateName(schema.title + ' Template'); setShowTemplateModal(true); setShowMobileMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700">📋 Template</button>
                      <button onClick={() => { setShowLoadModal(true); setShowMobileMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700">📂 Load</button>
                      <button onClick={() => { handleRunTests(); setShowMobileMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-purple-300 hover:bg-slate-700">🧪 Tests</button>
                      <hr className="my-1 border-slate-700" />
                      <button onClick={() => { handleReset(); setShowMobileMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-red-400 hover:bg-slate-700">✕ Reset</button>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Desktop: Persona dropdown + controls in one row */}
            <div className="hidden md:flex items-center gap-2">
              {/* Persona dropdown */}
              {personaOptions.length > 0 && (
                <>
                  <select
                    id="dashboard-persona-select"
                    value={persona || ''}
                    onChange={(e) => onPersonaChange?.(e.target.value)}
                    disabled={isGenerating}
                    className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-cyan-300 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500/50 disabled:opacity-50 cursor-pointer"
                  >
                    {personaOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label} Dashboard
                      </option>
                    ))}
                  </select>
                  {isGenerating && (
                    <svg className="w-4 h-4 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  )}
                  <div className="w-px h-6 bg-slate-700 mx-1" />
                </>
              )}

              {/* Edit toggle */}
              <button
                onClick={() => setEditMode(!editMode)}
                className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${editMode ? 'bg-amber-600 text-white hover:bg-amber-500' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}
                title={editMode ? 'Exit edit mode to click/drill widgets' : 'Enter edit mode to drag/resize widgets'}
              >
                {editMode ? '✓ Editing' : '✎ Edit'}
              </button>

              {/* Actions dropdown */}
              <div className="relative">
                <button
                  onClick={() => setShowActionsMenu(!showActionsMenu)}
                  className="px-3 py-1.5 bg-slate-800 text-slate-300 rounded-lg text-sm hover:bg-slate-700 transition-colors flex items-center gap-1"
                >
                  Actions
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {showActionsMenu && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setShowActionsMenu(false)} />
                    <div className="absolute right-0 top-full mt-1 z-50 bg-slate-800 border border-slate-700 rounded-lg shadow-xl py-1 min-w-[160px]">
                      {persona === 'CFO' && (
                        <button id="dashboard-whatif-btn" onClick={() => { setScenarioOpen(true); setShowActionsMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-cyan-300 hover:bg-slate-700 flex items-center gap-2">
                          <span>📊</span> What-If
                        </button>
                      )}
                      <button onClick={() => { handleAutoArrange(); setSaveSuccess('Layout auto-arranged!'); setTimeout(() => setSaveSuccess(null), 2000); setShowActionsMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-cyan-300 hover:bg-slate-700 flex items-center gap-2">
                        <span>⊞</span> Auto Arrange
                      </button>
                      <hr className="my-1 border-slate-700" />
                      <button onClick={() => { setSaveName(schema.title); setShowSaveModal(true); setShowActionsMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700 flex items-center gap-2">
                        <span>💾</span> Save Dashboard
                      </button>
                      <button onClick={() => { setTemplateName(schema.title + ' Template'); setShowTemplateModal(true); setShowActionsMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700 flex items-center gap-2">
                        <span>📋</span> Save as Template
                      </button>
                      <button onClick={() => { setShowLoadModal(true); setShowActionsMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700 flex items-center gap-2">
                        <span>📂</span> Load
                      </button>
                      <button onClick={() => { setSchema(null); setWidgetData({}); setSuggestions([]); setError(null); setShowActionsMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-700 flex items-center gap-2">
                        <span>🏗️</span> Build from Scratch
                      </button>
                      <hr className="my-1 border-slate-700" />
                      <button onClick={() => { handleRunTests(); setShowActionsMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-purple-300 hover:bg-slate-700 flex items-center gap-2">
                        <span>🧪</span> Run Tests
                      </button>
                      <hr className="my-1 border-slate-700" />
                      <button onClick={() => { handleReset(); setShowActionsMenu(false); }} className="w-full px-4 py-2 text-left text-sm text-red-400 hover:bg-slate-700 flex items-center gap-2">
                        <span>✕</span> Reset
                      </button>
                    </div>
                  </>
                )}
              </div>

              {/* Refinement input inline on desktop */}
              {showRefinementInput && (
                <>
                  <div className="w-px h-6 bg-slate-700 mx-1" />
                  <form onSubmit={handleRefinementSubmit} className="flex gap-2 flex-1 min-w-0">
                    <input
                      id="dashboard-refine-input"
                      type="text"
                      value={refinementQuery}
                      onChange={(e) => setRefinementQuery(e.target.value)}
                      placeholder="Refine dashboard..."
                      className="flex-1 min-w-0 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
                      disabled={isRefining}
                    />
                    <button
                      type="submit"
                      disabled={isRefining || !refinementQuery.trim()}
                      className="px-3 py-1.5 bg-cyan-600 text-white rounded-lg text-sm hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                    >
                      {isRefining ? '...' : 'Go'}
                    </button>
                  </form>
                </>
              )}
            </div>
          </div>

          {/* Success message */}
          {saveSuccess && (
            <div className="mt-2 px-3 py-1.5 bg-green-900/30 border border-green-700/50 rounded-lg text-xs md:text-sm text-green-300">
              {saveSuccess}
            </div>
          )}
        </div>
      )}

      {/* Refinement Input - Mobile only (below header) */}
      {schema && showRefinementInput && (
        <div className="md:hidden px-4 py-2 border-b border-slate-800 bg-slate-900/50">
          <form onSubmit={handleRefinementSubmit} className="flex gap-2">
            <input
              type="text"
              value={refinementQuery}
              onChange={(e) => setRefinementQuery(e.target.value)}
              placeholder="Refine dashboard..."
              className="flex-1 px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
              disabled={isRefining}
            />
            <button
              type="submit"
              disabled={isRefining || !refinementQuery.trim()}
              className="px-3 py-1.5 bg-cyan-600 text-white rounded-lg text-sm hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
            >
              {isRefining ? '...' : 'Go'}
            </button>
          </form>
        </div>
      )}

      {/* Presets, Suggestions, Refinement Message & History — shared row below header */}
      {schema && showRefinementInput && (
        <div className="px-4 md:px-6 py-1 border-b border-slate-800">
          {refinementMessage && (
            <div className="mb-1 px-3 py-1 bg-green-900/30 border border-green-700/50 rounded-lg">
              <p className="text-green-300 text-xs">
                ✓ {refinementMessage}
              </p>
            </div>
          )}

          {refinePresets.length > 0 && (
            <div
              ref={presetsRef}
              className="flex items-center gap-2 overflow-x-auto scrollbar-hide"
              style={{ cursor: 'grab' }}
              onMouseDown={handlePresetsMouseDown}
              onMouseMove={handlePresetsMouseMove}
              onMouseUp={handlePresetsMouseUp}
              onMouseLeave={handlePresetsMouseLeave}
            >
              <span className="text-slate-500 text-xs py-1 flex-shrink-0">Try:</span>
              {refinePresets.map((preset, i) => (
                <button
                  key={i}
                  onClick={() => {
                    if (!isDraggingPresets) {
                      refineDashboard(preset);
                    }
                  }}
                  disabled={isRefining}
                  className="flex-shrink-0 px-3 py-1 bg-cyan-900/30 border border-cyan-700/50 rounded-full text-cyan-300 text-xs hover:bg-cyan-800/40 hover:text-cyan-200 transition-colors disabled:opacity-50 whitespace-nowrap"
                >
                  {preset}
                </button>
              ))}
            </div>
          )}

          {suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-1">
              {suggestions.map((suggestion, i) => (
                <button
                  key={i}
                  onClick={() => handleSuggestionClick(suggestion)}
                  className="px-3 py-1 bg-slate-800/50 border border-slate-700/50 rounded-full text-slate-400 text-xs hover:bg-slate-700 hover:text-slate-200 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}

          {schema.refinement_history.length > 0 && (
            <div className="mt-1 text-xs text-slate-500">
              <span>Refinements: </span>
              {schema.refinement_history.map((r, i) => (
                <span key={i}>
                  {i > 0 && ' → '}
                  <span className="text-slate-400">"{r}"</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Loading State — either internal loading or parent isGenerating */}
      {(loading || (isGenerating && !schema)) && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <svg className="w-8 h-8 animate-spin text-cyan-400 mx-auto mb-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <p className="text-slate-400">Generating dashboard...</p>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && !loading && (
        <div className="m-6 p-4 bg-red-900/20 border border-red-800/50 rounded-lg">
          <p className="text-red-400">{error}</p>
          {suggestions.length > 0 && (
            <div className="mt-3">
              <p className="text-slate-400 text-sm mb-2">Try one of these:</p>
              <div className="flex flex-wrap gap-2">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => handleSuggestionClick(s)}
                    className="px-3 py-1 bg-slate-800 border border-slate-700 rounded text-slate-300 text-xs hover:bg-slate-700"
                  >
                    {s.split(':')[0]}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Forecast Comparison — shown after Apply to Forecast */}
      {forecastData && (
        <ForecastComparison rows={forecastData} onDismiss={() => setForecastData(null)} />
      )}

      {/* Dashboard Grid with Drag-and-Drop */}
      {schema && !loading && (
        <DashboardErrorBoundary onReset={handleReset}>
          <div className="flex-1 overflow-auto p-6" ref={containerRef}>
            <GridLayout
              className="layout"
              layout={gridLayout}
              cols={schema.layout.columns}
              rowHeight={rowHeight}
              width={containerWidth}
              onLayoutChange={handleLayoutChange}
              isDraggable={editMode}
              isResizable={editMode}
              margin={[schema.layout.gap, schema.layout.gap]}
              containerPadding={[0, 0]}
              compactType="vertical"
              preventCollision={false}
            >
              {schema.widgets.map(widget => (
                <div
                  key={widget.id}
                  data-widget-id={widget.id}
                  className="h-full group/widget relative"
                >
                  <WidgetRenderer
                    widget={widget}
                    data={widgetData[widget.id] || { loading: true }}
                    onClick={editMode ? undefined : (value) => handleWidgetClick(widget, value)}
                    onDoubleClick={editMode ? undefined : handleKPIDoubleClick}
                  />
                  {/* Per-widget close button — visible on hover */}
                  {schema.widgets.length > 1 && (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRemoveWidget(widget.id); }}
                      className="absolute top-1 right-1 w-5 h-5 rounded-full bg-slate-800/80 text-slate-500 hover:bg-red-600 hover:text-white flex items-center justify-center opacity-0 group-hover/widget:opacity-100 transition-opacity z-10 text-xs"
                      title="Remove widget"
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
            </GridLayout>
          </div>
        </DashboardErrorBoundary>
      )}

      {/* Empty State - Initial Query Input (blank slate builder) */}
      {!schema && !loading && !isGenerating && !error && (
        <div className="flex-1 flex items-center justify-center">
          <div className="w-full max-w-2xl px-8">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-semibold text-white mb-2">
                Create a Dashboard with Natural Language
              </h2>
              <p className="text-slate-400">
                Describe what you want to see, and I'll build it for you.
              </p>
            </div>

            {/* Query Input */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (initialQuery.trim()) {
                  generateDashboard(initialQuery.trim());
                }
              }}
              className="mb-6"
            >
              <div className="relative">
                <input
                  type="text"
                  value={initialQuery}
                  onChange={(e) => setInitialQuery(e.target.value)}
                  placeholder="e.g., Show me revenue by region over time"
                  className="w-full px-5 py-4 bg-slate-900 border border-slate-700 rounded-xl text-slate-200 text-lg placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500"
                />
                <button
                  type="submit"
                  disabled={!initialQuery.trim()}
                  className="absolute right-3 top-1/2 -translate-y-1/2 px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Create
                </button>
              </div>
            </form>

            {/* Load saved dashboards/templates */}
            <div className="text-center mb-6">
              <button
                onClick={() => setShowLoadModal(true)}
                className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg text-sm hover:bg-slate-700 transition-colors"
              >
                📂 Load Saved Dashboard or Template
              </button>
            </div>

            {/* Example Queries */}
            <div className="text-center">
              <p className="text-slate-500 text-sm mb-3">Or try one of these:</p>
              <div className="flex flex-wrap justify-center gap-2">
                {[
                  'Show me revenue by region over time',
                  'Create a dashboard with revenue, margin, and pipeline KPIs',
                  'Visualize quarterly revenue trend',
                  'Revenue breakdown by product',
                ].map((example) => (
                  <button
                    key={example}
                    onClick={() => {
                      setInitialQuery(example);
                      generateDashboard(example);
                    }}
                    className="px-3 py-1.5 bg-slate-800/80 border border-slate-700 rounded-full text-slate-300 text-xs hover:bg-slate-700 hover:border-slate-600 transition-colors"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Save Dashboard Modal */}
      {showSaveModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-white mb-4">Save Dashboard</h3>
            <input
              type="text"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Dashboard name"
              className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 mb-4"
              autoFocus
            />
            <div className="flex gap-3">
              <button
                onClick={() => setShowSaveModal(false)}
                className="flex-1 px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!saveName.trim()}
                className="flex-1 px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 transition-colors"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Save as Template Modal */}
      {showTemplateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold text-white mb-4">Save as Template</h3>
            <input
              type="text"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="Template name"
              className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 mb-3"
              autoFocus
            />
            <textarea
              value={templateDesc}
              onChange={(e) => setTemplateDesc(e.target.value)}
              placeholder="Description (optional)"
              rows={3}
              className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 mb-4 resize-none"
            />
            <div className="flex gap-3">
              <button
                onClick={() => setShowTemplateModal(false)}
                className="flex-1 px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveAsTemplate}
                disabled={!templateName.trim()}
                className="flex-1 px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 transition-colors"
              >
                Save Template
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Load Dashboard/Template Modal */}
      {showLoadModal && (
        <LoadModal
          onClose={() => setShowLoadModal(false)}
          onLoad={handleLoad}
          onDelete={(id, type) => {
            if (type === 'dashboard') deleteSavedDashboard(id);
            else deleteSavedTemplate(id);
          }}
        />
      )}

      {/* Test Results Modal */}
      {showTestModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-lg max-h-[80vh] flex flex-col">
            <h3 className="text-lg font-semibold text-white mb-4">🧪 NLQ-DCL Evaluation</h3>

            {testRunning ? (
              <div className="flex flex-col items-center py-8">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-400 mb-4"></div>
                <p className="text-slate-300">Running evaluation tests...</p>
                <p className="text-slate-500 text-sm mt-2">This may take up to 2 minutes</p>
              </div>
            ) : testResult ? (
              <div className="flex-1 overflow-y-auto">
                {/* Status Banner */}
                <div className={`px-4 py-3 rounded-lg mb-4 ${
                  testResult.status === 'passed'
                    ? 'bg-green-900/30 border border-green-700/50'
                    : testResult.status === 'failed'
                    ? 'bg-red-900/30 border border-red-700/50'
                    : 'bg-yellow-900/30 border border-yellow-700/50'
                }`}>
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">
                      {testResult.status === 'passed' ? '✓' : testResult.status === 'failed' ? '✗' : '⚠'}
                    </span>
                    <div>
                      <p className={`font-medium ${
                        testResult.status === 'passed' ? 'text-green-300' :
                        testResult.status === 'failed' ? 'text-red-300' : 'text-yellow-300'
                      }`}>
                        {testResult.status === 'passed' ? 'All Tests Passed' :
                         testResult.status === 'failed' ? 'Some Tests Failed' : 'Error Running Tests'}
                      </p>
                      <p className="text-slate-400 text-sm">{testResult.summary}</p>
                    </div>
                  </div>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-4 gap-3 mb-4">
                  <div className="bg-slate-800 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-white">{testResult.total}</p>
                    <p className="text-xs text-slate-400">Total</p>
                  </div>
                  <div className="bg-green-900/30 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-green-400">{testResult.passed}</p>
                    <p className="text-xs text-green-400/70">Passed</p>
                  </div>
                  <div className="bg-red-900/30 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-red-400">{testResult.failed}</p>
                    <p className="text-xs text-red-400/70">Failed</p>
                  </div>
                  <div className="bg-yellow-900/30 rounded-lg p-3 text-center">
                    <p className="text-2xl font-bold text-yellow-400">{testResult.errors}</p>
                    <p className="text-xs text-yellow-400/70">Errors</p>
                  </div>
                </div>

                {/* Duration */}
                <p className="text-slate-500 text-sm mb-4">
                  Completed in {testResult.duration_seconds}s
                </p>

                {/* Failures */}
                {testResult.failures.length > 0 && (
                  <div className="mb-4">
                    <p className="text-slate-300 font-medium mb-2">Failures:</p>
                    <div className="bg-slate-800 rounded-lg p-3 max-h-48 overflow-y-auto">
                      {testResult.failures.map((f, i) => (
                        <p key={i} className="text-red-400 text-xs font-mono mb-1">{f}</p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}

            <div className="flex gap-3 mt-4">
              <button
                onClick={() => setShowTestModal(false)}
                className="flex-1 px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
              >
                Close
              </button>
              {!testRunning && (
                <button
                  onClick={handleRunTests}
                  className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-500 transition-colors"
                >
                  Run Again
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Scenario Modeling Panel - CFO only */}
      {persona === 'CFO' && (
        <ScenarioModelingPanel
          isOpen={scenarioOpen}
          onToggle={() => setScenarioOpen(!scenarioOpen)}
          baseMetrics={baseMetrics}
          onApply={(adjustments) => {
            // Compute projected metrics from adjustments
            const revMult = (1 + adjustments.revenueGrowth / 100) * (1 + adjustments.pricingChange / 100);
            const adjRevenue = baseMetrics.revenue * revMult;
            const adjGrowth = baseMetrics.revenueGrowthPct + adjustments.revenueGrowth;
            const adjGrossMargin = Math.max(0, baseMetrics.grossMarginPct + adjustments.pricingChange * -0.1);
            const headcountCost = adjustments.headcountChange * 0.3;
            const opexImpact = adjustments.smSpendChange * 0.4;
            const revEfficiency = adjustments.revenueGrowth * 0.2;
            const adjOpMargin = baseMetrics.operatingMarginPct - headcountCost - opexImpact + revEfficiency;

            setForecastData([
              { metric: 'Revenue', current: baseMetrics.revenue, adjusted: adjRevenue, format: 'currency' },
              { metric: 'Growth Rate', current: baseMetrics.revenueGrowthPct, adjusted: adjGrowth, format: 'percent' },
              { metric: 'Gross Margin', current: baseMetrics.grossMarginPct, adjusted: adjGrossMargin, format: 'percent' },
              { metric: 'Op. Margin', current: baseMetrics.operatingMarginPct, adjusted: adjOpMargin, format: 'percent' },
            ]);
            setScenarioOpen(false);
          }}
        />
      )}
    </div>
  );
}

// =============================================================================
// Load Modal Component
// =============================================================================

function LoadModal({
  onClose,
  onLoad,
  onDelete,
}: {
  onClose: () => void;
  onLoad: (item: SavedDashboard | SavedTemplate) => void;
  onDelete: (id: string, type: 'dashboard' | 'template') => void;
}) {
  const [tab, setTab] = useState<'dashboards' | 'templates'>('dashboards');
  const [dashboards, setDashboards] = useState<SavedDashboard[]>([]);
  const [templates, setTemplates] = useState<SavedTemplate[]>([]);

  useEffect(() => {
    setDashboards(getSavedDashboards());
    setTemplates(getSavedTemplates());
  }, []);

  const handleDelete = (id: string, type: 'dashboard' | 'template') => {
    onDelete(id, type);
    if (type === 'dashboard') {
      setDashboards(prev => prev.filter(d => d.id !== id));
    } else {
      setTemplates(prev => prev.filter(t => t.id !== id));
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-lg max-h-[80vh] flex flex-col">
        <h3 className="text-lg font-semibold text-white mb-4">Load Dashboard or Template</h3>

        {/* Tabs */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setTab('dashboards')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'dashboards'
                ? 'bg-cyan-600 text-white'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Saved Dashboards ({dashboards.length})
          </button>
          <button
            onClick={() => setTab('templates')}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === 'templates'
                ? 'bg-cyan-600 text-white'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Templates ({templates.length})
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-auto min-h-[200px]">
          {tab === 'dashboards' ? (
            dashboards.length === 0 ? (
              <p className="text-slate-500 text-center py-8">No saved dashboards yet</p>
            ) : (
              <div className="space-y-2">
                {dashboards.map(d => (
                  <div
                    key={d.id}
                    className="flex items-center justify-between p-3 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors"
                  >
                    <button
                      onClick={() => onLoad(d)}
                      className="flex-1 text-left"
                    >
                      <p className="text-white font-medium">{d.name}</p>
                      <p className="text-slate-400 text-xs">
                        {new Date(d.savedAt).toLocaleDateString()} • {d.schema.widgets.length} widgets
                      </p>
                    </button>
                    <button
                      onClick={() => handleDelete(d.id, 'dashboard')}
                      className="ml-2 p-1 text-red-400 hover:text-red-300"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )
          ) : (
            templates.length === 0 ? (
              <p className="text-slate-500 text-center py-8">No templates yet</p>
            ) : (
              <div className="space-y-2">
                {templates.map(t => (
                  <div
                    key={t.id}
                    className="flex items-center justify-between p-3 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors"
                  >
                    <button
                      onClick={() => onLoad(t)}
                      className="flex-1 text-left"
                    >
                      <p className="text-white font-medium">{t.name}</p>
                      {t.description && (
                        <p className="text-slate-400 text-xs">{t.description}</p>
                      )}
                      <p className="text-slate-500 text-xs">
                        {new Date(t.savedAt).toLocaleDateString()} • {t.schema.widgets.length} widgets
                      </p>
                    </button>
                    <button
                      onClick={() => handleDelete(t.id, 'template')}
                      className="ml-2 p-1 text-red-400 hover:text-red-300"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )
          )}
        </div>

        <button
          onClick={onClose}
          className="mt-4 w-full px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
        >
          Close
        </button>
      </div>
    </div>
  );
}

export default DashboardRenderer;
