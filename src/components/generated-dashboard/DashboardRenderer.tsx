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
import GridLayout, { Layout } from 'react-grid-layout';
import 'react-grid-layout/css/styles.css';
import {
  DashboardSchema,
  Widget,
  WidgetData,
  DashboardGenerationResponse,
  DashboardRefinementResponse,
} from '../../types/generated-dashboard';
import { WidgetRenderer } from './WidgetRenderer';

// Storage keys
const SAVED_DASHBOARDS_KEY = 'aos_saved_dashboards';
const SAVED_TEMPLATES_KEY = 'aos_saved_templates';

interface SavedDashboard {
  id: string;
  name: string;
  schema: DashboardSchema;
  savedAt: string;
}

interface SavedTemplate {
  id: string;
  name: string;
  description: string;
  schema: DashboardSchema;
  savedAt: string;
}

interface DashboardRendererProps {
  /** Initial schema to render (optional - can start empty) */
  initialSchema?: DashboardSchema;
  /** Query that generated the dashboard */
  sourceQuery?: string;
  /** Callback when a drill-down is triggered */
  onDrillDown?: (query: string) => void;
  /** Callback when dashboard is refined */
  onRefinement?: (newSchema: DashboardSchema) => void;
  /** Show refinement input */
  showRefinementInput?: boolean;
}

// =============================================================================
// Storage Helpers
// =============================================================================

function getSavedDashboards(): SavedDashboard[] {
  try {
    const data = localStorage.getItem(SAVED_DASHBOARDS_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
}

function saveDashboard(dashboard: SavedDashboard): void {
  const dashboards = getSavedDashboards();
  const existing = dashboards.findIndex(d => d.id === dashboard.id);
  if (existing >= 0) {
    dashboards[existing] = dashboard;
  } else {
    dashboards.push(dashboard);
  }
  localStorage.setItem(SAVED_DASHBOARDS_KEY, JSON.stringify(dashboards));
}

function deleteSavedDashboard(id: string): void {
  const dashboards = getSavedDashboards().filter(d => d.id !== id);
  localStorage.setItem(SAVED_DASHBOARDS_KEY, JSON.stringify(dashboards));
}

function getSavedTemplates(): SavedTemplate[] {
  try {
    const data = localStorage.getItem(SAVED_TEMPLATES_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
}

function saveTemplate(template: SavedTemplate): void {
  const templates = getSavedTemplates();
  templates.push(template);
  localStorage.setItem(SAVED_TEMPLATES_KEY, JSON.stringify(templates));
}

function deleteSavedTemplate(id: string): void {
  const templates = getSavedTemplates().filter(t => t.id !== id);
  localStorage.setItem(SAVED_TEMPLATES_KEY, JSON.stringify(templates));
}

// =============================================================================
// Main Component
// =============================================================================

export function DashboardRenderer({
  initialSchema,
  sourceQuery,
  onDrillDown,
  onRefinement,
  showRefinementInput = true,
}: DashboardRendererProps) {
  const [schema, setSchema] = useState<DashboardSchema | null>(initialSchema || null);
  const [widgetData, setWidgetData] = useState<Record<string, WidgetData>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refinementQuery, setRefinementQuery] = useState('');
  const [initialQuery, setInitialQuery] = useState('');
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isRefining, setIsRefining] = useState(false);

  // Drag and drop state
  const [isEditMode, setIsEditMode] = useState(false);
  const [customLayout, setCustomLayout] = useState<Layout[] | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1200);

  // Modal states
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [showLoadModal, setShowLoadModal] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [templateName, setTemplateName] = useState('');
  const [templateDesc, setTemplateDesc] = useState('');
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  // Measure container width for grid layout
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.offsetWidth - 48); // minus padding
      }
    };
    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  // Convert widget positions to react-grid-layout format
  const gridLayout = useMemo((): Layout[] => {
    if (customLayout) return customLayout;
    if (!schema) return [];

    return schema.widgets.map(widget => ({
      i: widget.id,
      x: widget.position.column - 1,
      y: widget.position.row - 1,
      w: widget.position.col_span,
      h: widget.position.row_span,
      minW: 2,
      minH: 2,
    }));
  }, [schema, customLayout]);

  // Handle layout change from drag-and-drop
  const handleLayoutChange = useCallback((newLayout: Layout[]) => {
    if (!isEditMode) return;
    setCustomLayout(newLayout);

    // Update schema with new positions
    if (schema) {
      const updatedWidgets = schema.widgets.map(widget => {
        const layoutItem = newLayout.find(l => l.i === widget.id);
        if (layoutItem) {
          return {
            ...widget,
            position: {
              ...widget.position,
              column: layoutItem.x + 1,
              row: layoutItem.y + 1,
              col_span: layoutItem.w,
              row_span: layoutItem.h,
            },
          };
        }
        return widget;
      });
      setSchema({ ...schema, widgets: updatedWidgets });
    }
  }, [isEditMode, schema]);

  // Reset dashboard
  const handleReset = useCallback(() => {
    setSchema(null);
    setWidgetData({});
    setError(null);
    setSuggestions([]);
    setInitialQuery('');
    setRefinementQuery('');
    setCustomLayout(null);
    setIsEditMode(false);
  }, []);

  // Save dashboard
  const handleSave = useCallback(() => {
    if (!schema || !saveName.trim()) return;

    const saved: SavedDashboard = {
      id: schema.id,
      name: saveName.trim(),
      schema: schema,
      savedAt: new Date().toISOString(),
    };
    saveDashboard(saved);
    setShowSaveModal(false);
    setSaveName('');
    setSaveSuccess('Dashboard saved!');
    setTimeout(() => setSaveSuccess(null), 2000);
  }, [schema, saveName]);

  // Save as template
  const handleSaveAsTemplate = useCallback(() => {
    if (!schema || !templateName.trim()) return;

    const template: SavedTemplate = {
      id: `template_${Date.now()}`,
      name: templateName.trim(),
      description: templateDesc.trim(),
      schema: {
        ...schema,
        id: `template_${Date.now()}`,
        source_query: '',
        refinement_history: [],
      },
      savedAt: new Date().toISOString(),
    };
    saveTemplate(template);
    setShowTemplateModal(false);
    setTemplateName('');
    setTemplateDesc('');
    setSaveSuccess('Template saved!');
    setTimeout(() => setSaveSuccess(null), 2000);
  }, [schema, templateName, templateDesc]);

  // Load saved dashboard or template
  const handleLoad = useCallback((item: SavedDashboard | SavedTemplate) => {
    setSchema(item.schema);
    setCustomLayout(null);
    fetchWidgetData(item.schema);
    setShowLoadModal(false);
  }, []);

  // Generate dashboard from query
  const generateDashboard = useCallback(async (query: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/v1/query/dashboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query }),
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
        setCustomLayout(null);
        const initialData: Record<string, WidgetData> = {};
        data.dashboard.widgets.forEach(widget => {
          initialData[widget.id] = { loading: true };
        });
        setWidgetData(initialData);
        fetchWidgetData(data.dashboard);
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
  }, []);

  // Refine existing dashboard
  const refineDashboard = useCallback(async (query: string) => {
    if (!schema) return;

    setIsRefining(true);
    setError(null);

    try {
      const response = await fetch('/api/v1/dashboard/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dashboard_id: schema.id,
          refinement_query: query,
        }),
      });

      const data: DashboardRefinementResponse = await response.json();

      if (data.success && data.dashboard) {
        setSchema(data.dashboard);
        setCustomLayout(null);
        onRefinement?.(data.dashboard);
        fetchWidgetData(data.dashboard);
      } else {
        setError(data.error || 'Failed to refine dashboard');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refine dashboard');
    } finally {
      setIsRefining(false);
      setRefinementQuery('');
    }
  }, [schema, onRefinement]);

  // Fetch data for all widgets
  const fetchWidgetData = useCallback(async (dashboard: DashboardSchema) => {
    const newData: Record<string, WidgetData> = {};
    for (const widget of dashboard.widgets) {
      newData[widget.id] = await generateMockWidgetData(widget);
    }
    setWidgetData(newData);
  }, []);

  // Handle widget click (drill-down)
  const handleWidgetClick = useCallback((widget: Widget, value?: string) => {
    if (isEditMode) return; // Don't drill down in edit mode
    const drillDown = widget.interactions.find(i => i.type === 'drill_down' && i.enabled);
    if (drillDown?.drill_down && onDrillDown) {
      const query = drillDown.drill_down.query_template.replace('{value}', value || '');
      onDrillDown(query);
    }
  }, [onDrillDown, isEditMode]);

  // Handle refinement submit
  const handleRefinementSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (refinementQuery.trim()) {
      refineDashboard(refinementQuery.trim());
    }
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

  const rowHeight = schema?.layout.row_height || 80;

  return (
    <div className="h-full flex flex-col bg-slate-950">
      {/* Dashboard Header */}
      {schema && (
        <div className="px-6 py-4 border-b border-slate-800">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">{schema.title}</h2>
              {schema.description && (
                <p className="text-sm text-slate-400 mt-1">{schema.description}</p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {/* Edit Mode Toggle */}
              <button
                onClick={() => setIsEditMode(!isEditMode)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  isEditMode
                    ? 'bg-cyan-600 text-white'
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                {isEditMode ? '✓ Done Editing' : '⋮⋮ Edit Layout'}
              </button>

              {/* Save Button */}
              <button
                onClick={() => {
                  setSaveName(schema.title);
                  setShowSaveModal(true);
                }}
                className="px-3 py-1.5 bg-slate-800 text-slate-300 rounded-lg text-sm hover:bg-slate-700 transition-colors"
              >
                💾 Save
              </button>

              {/* Save as Template Button */}
              <button
                onClick={() => {
                  setTemplateName(schema.title + ' Template');
                  setShowTemplateModal(true);
                }}
                className="px-3 py-1.5 bg-slate-800 text-slate-300 rounded-lg text-sm hover:bg-slate-700 transition-colors"
              >
                📋 Template
              </button>

              {/* Load Button */}
              <button
                onClick={() => setShowLoadModal(true)}
                className="px-3 py-1.5 bg-slate-800 text-slate-300 rounded-lg text-sm hover:bg-slate-700 transition-colors"
              >
                📂 Load
              </button>

              {/* Reset Button */}
              <button
                onClick={handleReset}
                className="px-3 py-1.5 bg-red-900/50 text-red-300 rounded-lg text-sm hover:bg-red-900/70 transition-colors"
              >
                ✕ Reset
              </button>
            </div>
          </div>

          {/* Edit mode hint */}
          {isEditMode && (
            <div className="mt-2 px-3 py-2 bg-cyan-900/30 border border-cyan-700/50 rounded-lg text-sm text-cyan-300">
              Drag widgets to rearrange. Drag corners to resize. Click "Done Editing" when finished.
            </div>
          )}

          {/* Success message */}
          {saveSuccess && (
            <div className="mt-2 px-3 py-2 bg-green-900/30 border border-green-700/50 rounded-lg text-sm text-green-300">
              {saveSuccess}
            </div>
          )}
        </div>
      )}

      {/* Loading State */}
      {loading && (
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

      {/* Dashboard Grid with Drag-and-Drop */}
      {schema && !loading && (
        <div className="flex-1 overflow-auto p-6" ref={containerRef}>
          <GridLayout
            className="layout"
            layout={gridLayout}
            cols={schema.layout.columns}
            rowHeight={rowHeight}
            width={containerWidth}
            onLayoutChange={handleLayoutChange}
            isDraggable={isEditMode}
            isResizable={isEditMode}
            margin={[schema.layout.gap, schema.layout.gap]}
            containerPadding={[0, 0]}
            compactType={null}
            preventCollision={false}
          >
            {schema.widgets.map(widget => (
              <div
                key={widget.id}
                className={`${isEditMode ? 'ring-2 ring-cyan-500/50 ring-offset-2 ring-offset-slate-950' : ''}`}
              >
                <WidgetRenderer
                  widget={widget}
                  data={widgetData[widget.id] || { loading: true }}
                  onClick={(value) => handleWidgetClick(widget, value)}
                  rowHeight={rowHeight}
                />
              </div>
            ))}
          </GridLayout>
        </div>
      )}

      {/* Refinement Input */}
      {schema && showRefinementInput && !isEditMode && (
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-900/50">
          <form onSubmit={handleRefinementSubmit} className="flex gap-3">
            <input
              type="text"
              value={refinementQuery}
              onChange={(e) => setRefinementQuery(e.target.value)}
              placeholder="Refine this dashboard... (e.g., 'Add a pipeline KPI', 'Make that a bar chart')"
              className="flex-1 px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
              disabled={isRefining}
            />
            <button
              type="submit"
              disabled={isRefining || !refinementQuery.trim()}
              className="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isRefining ? 'Refining...' : 'Refine'}
            </button>
          </form>

          {/* Suggestions */}
          {suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
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

          {/* Refinement History */}
          {schema.refinement_history.length > 0 && (
            <div className="mt-3 text-xs text-slate-500">
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

      {/* Empty State - Initial Query Input */}
      {!schema && !loading && !error && (
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

// =============================================================================
// Mock Data Generation (for MVP)
// =============================================================================

async function generateMockWidgetData(widget: Widget): Promise<WidgetData> {
  await new Promise(resolve => setTimeout(resolve, 300 + Math.random() * 200));

  const metric = widget.data.metrics[0]?.metric || 'revenue';

  switch (widget.type) {
    case 'kpi_card':
      return generateKPIData(metric);
    case 'line_chart':
    case 'area_chart':
      return generateTimeSeriesData(metric, widget.data.time?.granularity || 'quarterly');
    case 'bar_chart':
    case 'horizontal_bar':
      return generateCategoryData(metric, widget.data.dimensions[0]?.dimension);
    case 'stacked_bar':
      return generateStackedData(widget.data.metrics, widget.data.dimensions[0]?.dimension);
    case 'donut_chart':
      return generateDonutData(metric, widget.data.dimensions[0]?.dimension);
    case 'data_table':
      return generateTableData(widget.data.metrics, widget.data.dimensions);
    default:
      return { loading: false };
  }
}

function generateKPIData(metric: string): WidgetData {
  const values: Record<string, { value: number; format: string; trend: number }> = {
    revenue: { value: 200, format: '$200M', trend: 15.2 },
    gross_margin_pct: { value: 65, format: '65.0%', trend: 2.3 },
    net_income: { value: 45, format: '$45M', trend: 18.5 },
    pipeline: { value: 575, format: '$575M', trend: 8.7 },
    churn: { value: 2.5, format: '2.5%', trend: -0.3 },
    nrr: { value: 118, format: '118%', trend: 3.0 },
    headcount: { value: 450, format: '450', trend: 12.5 },
    win_rate: { value: 32, format: '32%', trend: 4.2 },
    quota_attainment: { value: 95.8, format: '95.8%', trend: 5.1 },
    magic_number: { value: 0.9, format: '0.9x', trend: 0.1 },
    ltv_cac: { value: 4.2, format: '4.2x', trend: 0.3 },
    uptime_pct: { value: 99.95, format: '99.95%', trend: 0.02 },
    p1_incidents: { value: 3, format: '3', trend: -2 },
  };

  const data = values[metric] || { value: 100, format: '100', trend: 5.0 };
  const isPositive = data.trend > 0;

  return {
    loading: false,
    value: data.value,
    formatted_value: data.format,
    trend: {
      direction: isPositive ? 'up' : data.trend < 0 ? 'down' : 'flat',
      percent_change: Math.abs(data.trend),
      comparison_label: 'vs prior period',
    },
    sparkline_data: Array.from({ length: 8 }, () => data.value * (0.8 + Math.random() * 0.4)),
  };
}

function generateTimeSeriesData(metric: string, granularity: string): WidgetData {
  const periods = granularity === 'quarterly'
    ? ['Q1 2024', 'Q2 2024', 'Q3 2024', 'Q4 2024', 'Q1 2025', 'Q2 2025', 'Q3 2025', 'Q4 2025']
    : ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  const baseValue = metric === 'revenue' ? 40 : metric.includes('pct') ? 60 : 100;
  const growth = 1.05;

  return {
    loading: false,
    categories: periods,
    series: [{
      name: metric,
      data: periods.map((label, i) => ({
        label,
        value: Math.round(baseValue * Math.pow(growth, i) * (0.9 + Math.random() * 0.2) * 10) / 10,
      })),
    }],
  };
}

function generateCategoryData(metric: string, dimension?: string): WidgetData {
  const categories = dimension === 'rep'
    ? ['John Smith', 'Sarah Jones', 'Mike Chen', 'Lisa Wang', 'Tom Brown']
    : dimension === 'product'
    ? ['Enterprise', 'Professional', 'Team', 'Starter']
    : ['AMER', 'EMEA', 'APAC', 'LATAM'];

  const baseValue = metric === 'revenue' ? 50 : 20;

  return {
    loading: false,
    categories,
    series: [{
      name: metric,
      data: categories.map((label, i) => ({
        label,
        value: Math.round(baseValue * (1 - i * 0.15) * (0.8 + Math.random() * 0.4) * 10) / 10,
      })),
    }],
  };
}

function generateStackedData(metrics: Array<{ metric: string }>, _dimension?: string): WidgetData {
  const categories = ['Q1', 'Q2', 'Q3', 'Q4'];

  return {
    loading: false,
    categories,
    series: metrics.slice(0, 3).map((m, mi) => ({
      name: m.metric,
      data: categories.map((label, i) => ({
        label,
        value: Math.round((30 - mi * 5) * (1 + i * 0.1) * (0.8 + Math.random() * 0.4) * 10) / 10,
      })),
    })),
  };
}

function generateDonutData(metric: string, dimension?: string): WidgetData {
  const categories = dimension === 'product'
    ? ['Enterprise', 'Professional', 'Team', 'Starter']
    : ['AMER', 'EMEA', 'APAC', 'LATAM'];

  return {
    loading: false,
    categories,
    series: [{
      name: metric,
      data: categories.map((label, i) => ({
        label,
        value: Math.round((40 - i * 8) * (0.8 + Math.random() * 0.4)),
      })),
    }],
  };
}

function generateTableData(
  metrics: Array<{ metric: string }>,
  dimensions: Array<{ dimension: string }>
): WidgetData {
  const dimension = dimensions[0]?.dimension || 'region';
  const categories = dimension === 'rep'
    ? ['John Smith', 'Sarah Jones', 'Mike Chen', 'Lisa Wang', 'Tom Brown']
    : ['AMER', 'EMEA', 'APAC', 'LATAM'];

  return {
    loading: false,
    rows: categories.map(cat => {
      const row: Record<string, any> = { [dimension]: cat };
      metrics.forEach(m => {
        const baseValue = m.metric === 'revenue' ? 50 : 20;
        row[m.metric] = Math.round(baseValue * (0.8 + Math.random() * 0.4) * 10) / 10;
      });
      return row;
    }),
  };
}

export default DashboardRenderer;
