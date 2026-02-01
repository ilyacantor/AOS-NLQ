import { useState, useEffect, useCallback, useRef } from 'react'
import { GalaxyView, IntentMapResponse } from './components/galaxy'
import { RAGLearningPanel, LLMCallCounter, useSessionId } from './components/rag'
import { InsufficientDataPanel } from './components/rag/InsufficientDataPanel'
import { DashboardRenderer, DashboardSchema } from './components/generated-dashboard'
import { UserGuide } from './components/UserGuide'

async function fetchWithRetry(
  url: string,
  options: RequestInit,
  maxRetries = 3,
  baseDelay = 500
): Promise<Response> {
  let lastError: Error | null = null
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await fetch(url, options)
      return response
    } catch (error) {
      lastError = error as Error
      if (attempt < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, baseDelay * (attempt + 1)))
      }
    }
  }
  throw lastError
}

interface QueryHistoryItem {
  id: string
  query: string
  timestamp: string
  duration: string
  tag: string
  count: number
}

type ViewMode = 'galaxy' | 'dashboard' | 'guide'
type Persona = 'CFO' | 'CRO' | 'COO' | 'CTO' | 'CHRO'
type PanelTab = 'History' | 'Learning' | 'Data Gaps'
type QueryMode = 'static' | 'ai'

const personaOptions: { label: string; value: Persona; query: string; refinePresets: string[] }[] = [
  {
    label: 'CFO',
    value: 'CFO',
    query: 'Show me a finance dashboard with revenue KPI, gross margin percent KPI, operating margin trend, net income KPI, and cash breakdown by region',
    refinePresets: ['Add EBITDA card', 'Show burn rate trend', 'Add AR vs AP comparison', 'Filter to AMER region']
  },
  {
    label: 'CRO',
    value: 'CRO',
    query: 'Show me a sales dashboard with ARR KPI, pipeline KPI, bookings trend over time, win rate KPI, and quota attainment by rep',
    refinePresets: ['Add churn rate card', 'Show NRR trend', 'Break down by product', 'Add sales cycle chart']
  },
  {
    label: 'COO',
    value: 'COO',
    query: 'Show me an operations dashboard with headcount KPI, revenue per employee KPI, magic number trend, LTV CAC ratio KPI, and NPS breakdown',
    refinePresets: ['Add CAC payback card', 'Show customer count trend', 'Add CSAT score', 'Filter to Enterprise']
  },
  {
    label: 'CTO',
    value: 'CTO',
    query: 'Show me a technology dashboard with uptime percent KPI, P1 incidents KPI, deploys per week trend, sprint velocity KPI, and MTTR breakdown',
    refinePresets: ['Add code coverage card', 'Show tech debt trend', 'Add features shipped', 'Filter to Platform']
  },
  {
    label: 'CHRO',
    value: 'CHRO',
    query: 'Show me a people dashboard with total headcount KPI, turnover rate KPI, time to hire trend, employee satisfaction KPI, and engagement breakdown',
    refinePresets: ['Add training hours card', 'Show hiring trend', 'Break down by department', 'Add retention rate']
  },
]

const quickActions = [
  '2025 KPIs',
  'whats the margin',
  'are we profitable',
  'how\'s pipeline looking',
  'churn?',
  'are we efficient',
  'platform stable?',
  'how\'s velocity',
  'pto days',
  '401k match',
]

function aggregateHistory(items: QueryHistoryItem[]): QueryHistoryItem[] {
  const queryMap = new Map<string, QueryHistoryItem>()
  for (const item of items) {
    const normalizedQuery = item.query.toLowerCase().trim()
    const existing = queryMap.get(normalizedQuery)
    if (existing) {
      existing.count += 1
    } else {
      queryMap.set(normalizedQuery, { ...item, count: 1 })
    }
  }
  return Array.from(queryMap.values())
}

function App() {
  // Core state
  const [query, setQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('galaxy')
  const [queryMode, setQueryMode] = useState<QueryMode>('ai')
  const [selectedPersona, setSelectedPersona] = useState<Persona>('CFO')
  const [panelTab, setPanelTab] = useState<PanelTab>('History')
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [galaxyResponse, setGalaxyResponse] = useState<IntentMapResponse | null>(null)
  const [lastDuration, setLastDuration] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Dashboard state - always use DashboardRenderer
  const [dashboardSchema, setDashboardSchema] = useState<DashboardSchema | null>(null)
  const [dashboardWidgetData, setDashboardWidgetData] = useState<Record<string, any>>({})
  const [isGeneratingDashboard, setIsGeneratingDashboard] = useState(false)
  const [dashboardError, setDashboardError] = useState<string | null>(null)

  const [hasLoadedDefault, setHasLoadedDefault] = useState(false)
  const [hasLoadedDefaultDashboard, setHasLoadedDefaultDashboard] = useState(false)
  const sessionId = useSessionId()

  // Use ref for query to avoid stale closure issues
  const queryRef = useRef(query)
  queryRef.current = query

  // Load query history from database on mount
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const response = await fetch('/api/v1/rag/learning/log/db?limit=50')
        if (response.ok) {
          const data = await response.json()
          const historyItems: QueryHistoryItem[] = (data.entries || []).map((entry: any) => ({
            id: entry.id,
            query: entry.query,
            timestamp: new Date(entry.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true }),
            duration: entry.execution_time_ms ? `${entry.execution_time_ms}ms` : '',
            tag: entry.learned ? 'LEARNED' : (entry.source === 'cache' ? 'CACHED' : 'AI'),
            count: 1,
          }))
          setQueryHistory(aggregateHistory(historyItems))
        }
      } catch (error) {
        console.error('Failed to load history:', error)
      }
    }
    loadHistory()
  }, [])

  // Generate dashboard via API
  const generateDashboard = useCallback(async (queryText: string, forceNew: boolean = false, titleOverride?: string) => {
    if (!queryText.trim()) return

    setIsGeneratingDashboard(true)
    setDashboardError(null)

    try {
      // Check if this is a "build me X dashboard" request or we're forcing new
      const isBuildRequest = forceNew || /build\s+(me\s+)?a?\s*\w+\s+dashboard/i.test(queryText)

      if (isBuildRequest || !dashboardSchema) {
        // Generate new dashboard - correct endpoint is /query/dashboard
        const res = await fetchWithRetry('/api/v1/query/dashboard', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: queryText,
            reference_date: '2026-01-27',
            conversation_id: sessionId
          })
        })

        if (res.ok) {
          const data = await res.json()
          if (data.success && data.dashboard) {
            const schema = data.dashboard
            if (titleOverride) {
              schema.title = titleOverride
            }
            setDashboardSchema(schema)
            setDashboardWidgetData(data.widget_data || {})
          } else if (data.error) {
            setDashboardError(data.error)
          } else {
            setDashboardError('Failed to generate dashboard - no schema returned')
          }
        } else {
          const errorData = await res.json().catch(() => ({}))
          setDashboardError(errorData.detail || 'Failed to generate dashboard')
        }
      } else {
        // Refine existing dashboard
        const res = await fetchWithRetry('/api/v1/dashboard/refine', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dashboard_id: dashboardSchema.id,
            refinement_query: queryText,
            conversation_id: sessionId
          })
        })

        if (res.ok) {
          const data = await res.json()
          if (data.success && data.dashboard) {
            setDashboardSchema(data.dashboard)
            setDashboardWidgetData(data.widget_data || {})
          } else if (data.error) {
            setDashboardError(data.error)
          }
        } else {
          const errorData = await res.json().catch(() => ({}))
          setDashboardError(errorData.detail || 'Failed to refine dashboard')
        }
      }
    } catch (error) {
      console.error('Dashboard generation failed:', error)
      setDashboardError('Connection error. Is the server running?')
    }

    setIsGeneratingDashboard(false)
  }, [dashboardSchema, sessionId])

  // Handle persona selection - generate that persona's dashboard
  const handlePersonaSelect = useCallback((persona: Persona) => {
    setSelectedPersona(persona)
    const personaConfig = personaOptions.find(p => p.value === persona)
    if (personaConfig) {
      generateDashboard(personaConfig.query, true, `${persona} Dashboard`)
    }
  }, [generateDashboard])

  // Load default dashboard on first view
  useEffect(() => {
    if (!hasLoadedDefaultDashboard && viewMode === 'dashboard') {
      setHasLoadedDefaultDashboard(true)
      const personaConfig = personaOptions.find(p => p.value === selectedPersona)
      if (personaConfig) {
        generateDashboard(personaConfig.query, true, `${selectedPersona} Dashboard`)
      }
    }
  }, [hasLoadedDefaultDashboard, viewMode, selectedPersona, generateDashboard])

  // Detect if query is a dashboard command (add/remove/show widgets, build dashboard, etc.)
  const isDashboardCommand = useCallback((queryText: string): boolean => {
    const dashboardPatterns = [
      /\b(add|remove|delete|show|hide|create|insert)\b.*(kpi|card|chart|widget|metric|dashboard)/i,
      /\bbuild\s+(me\s+)?a?\s*\w*\s*dashboard/i,
      /\b(make|resize|move|arrange|reorganize)\b.*widget/i,
      /\badd\s+(a\s+)?(revenue|margin|pipeline|churn|headcount|arr|nrr|cac|ltv)/i,
    ]
    return dashboardPatterns.some(pattern => pattern.test(queryText))
  }, [])

  // Submit a Galaxy query
  const submitGalaxyQuery = useCallback(async (queryText: string) => {
    if (!queryText.trim()) return

    // Check if this is a dashboard command - route to dashboard
    if (isDashboardCommand(queryText)) {
      const timestamp = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })

      // Add to history first
      const newItem: QueryHistoryItem = {
        id: Date.now().toString(),
        query: queryText,
        timestamp,
        duration: '',
        tag: 'DASHBOARD',
        count: 1,
      }
      setQueryHistory(prev => aggregateHistory([newItem, ...prev]))
      setQuery('')

      // Switch to dashboard and trigger refinement or generation
      setViewMode('dashboard')

      // If we have an existing dashboard, refine it; otherwise generate new
      if (dashboardSchema) {
        // Trigger refinement via the dashboard API
        try {
          const startTime = performance.now()
          const res = await fetchWithRetry('/api/v1/dashboard/refine', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              dashboard_id: dashboardSchema.id,
              refinement_query: queryText,
              conversation_id: sessionId
            })
          })
          const data = await res.json()
          const duration = Math.round(performance.now() - startTime)
          setLastDuration(`${duration}ms`)

          if (data.success && data.dashboard) {
            setDashboardSchema(data.dashboard)
            if (data.widget_data) {
              setDashboardWidgetData(data.widget_data)
            }
          }
        } catch (error) {
          console.error('Dashboard refinement failed:', error)
        }
      } else {
        // Generate new dashboard
        generateDashboard(queryText, true)
      }
      return
    }

    setIsLoading(true)
    setQuery('')
    setGalaxyResponse(null)
    const timestamp = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    const startTime = performance.now()

    try {
      const res = await fetchWithRetry('/api/v1/intent-map', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: queryText,
          reference_date: '2026-01-27',
          mode: queryMode,
          session_id: sessionId
        })
      })

      const data = await res.json()
      const duration = Math.round(performance.now() - startTime)

      setGalaxyResponse(data as IntentMapResponse)
      setLastDuration(`${duration}ms`)

      const newItem: QueryHistoryItem = {
        id: Date.now().toString(),
        query: queryText,
        timestamp,
        duration: `${duration}ms`,
        tag: (data as IntentMapResponse).query_type || 'intent-map',
        count: 1,
      }
      setQueryHistory(prev => aggregateHistory([newItem, ...prev]))
    } catch (error) {
      console.error('Query failed:', error)
      setGalaxyResponse({
        query: queryText,
        query_type: 'ERROR',
        ambiguity_type: null,
        persona: 'CFO',
        overall_confidence: 0,
        overall_data_quality: 0,
        node_count: 0,
        nodes: [],
        primary_node_id: null,
        primary_answer: 'Failed to connect to backend. Is the server running?',
        text_response: 'Failed to connect to backend. Is the server running?',
        needs_clarification: false,
        clarification_prompt: null,
      } as IntentMapResponse)
    }

    setIsLoading(false)
  }, [queryMode, sessionId, isDashboardCommand, dashboardSchema, generateDashboard])

  // Auto-query "2025 results" for Galaxy view on first load
  useEffect(() => {
    if (!hasLoadedDefault && viewMode === 'galaxy') {
      setHasLoadedDefault(true)
      submitGalaxyQuery('2025 results')
    }
  }, [hasLoadedDefault, viewMode, submitGalaxyQuery])

  // Handle form submit
  const handleSubmit = useCallback(() => {
    const currentQuery = queryRef.current
    if (currentQuery.trim()) {
      submitGalaxyQuery(currentQuery)
    }
  }, [submitGalaxyQuery])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  // Handle drill-down from dashboard tiles - open in Galaxy view
  const handleDashboardDrillDown = useCallback((drillQuery: string) => {
    setViewMode('galaxy')
    submitGalaxyQuery(drillQuery)
  }, [submitGalaxyQuery])

  // Handle dashboard refinement from DashboardRenderer
  const handleDashboardRefinement = useCallback((newSchema: DashboardSchema) => {
    setDashboardSchema(newSchema)
    setDashboardWidgetData({})
  }, [])

  const hasGalaxyResponse = galaxyResponse !== null

  return (
    <div className="h-screen bg-slate-950 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="border-b border-slate-800">
        {/* Mobile Header Row */}
        <div className="flex items-center justify-between px-4 py-3 md:hidden">
          <div className="flex items-center gap-2">
            <span className="text-cyan-400 text-xl font-bold">NLQ</span>
          </div>
          <div className="flex items-center gap-2">
            {/* View Mode Toggle - Compact for mobile */}
            <div className="flex items-center gap-1 bg-slate-900 rounded-lg p-1">
              <button
                onClick={() => setViewMode('galaxy')}
                className={`min-h-[44px] min-w-[44px] px-2 rounded-md text-xs font-medium transition-colors ${
                  viewMode === 'galaxy'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Galaxy
              </button>
              <button
                onClick={() => setViewMode('dashboard')}
                className={`min-h-[44px] min-w-[44px] px-2 rounded-md text-xs font-medium transition-colors ${
                  viewMode === 'dashboard'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Dash
              </button>
              <button
                onClick={() => setViewMode('guide')}
                className={`min-h-[44px] min-w-[44px] px-2 rounded-md text-xs font-medium transition-colors ${
                  viewMode === 'guide'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Guide
              </button>
            </div>
            {/* Hamburger Menu Button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="min-h-[44px] min-w-[44px] p-2 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors"
              aria-label="Toggle menu"
            >
              <svg className="w-6 h-6 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {mobileMenuOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile Menu Dropdown */}
        {mobileMenuOpen && (
          <div className="md:hidden px-4 pb-4 bg-slate-900/95 border-t border-slate-800">
            <div className="flex flex-col gap-3 pt-3">
              {/* Mode Toggle */}
              <div className="flex items-center justify-between">
                <span className="text-slate-400 text-sm">Mode:</span>
                <div className="flex items-center bg-slate-800 rounded-lg p-1">
                  <button
                    onClick={() => setQueryMode('static')}
                    className={`min-h-[44px] px-4 rounded-md text-sm font-medium transition-colors ${
                      queryMode === 'static'
                        ? 'bg-amber-600 text-white'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    Static
                  </button>
                  <button
                    onClick={() => setQueryMode('ai')}
                    className={`min-h-[44px] px-4 rounded-md text-sm font-medium transition-colors ${
                      queryMode === 'ai'
                        ? 'bg-emerald-600 text-white'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    AI
                  </button>
                </div>
              </div>
              {/* User Guide & Stats */}
              <div className="flex items-center justify-between">
                <button
                  onClick={() => { setViewMode('guide'); setMobileMenuOpen(false); }}
                  className={`min-h-[44px] px-4 py-2 rounded-lg transition-colors ${
                    viewMode === 'guide'
                      ? 'bg-slate-700 text-white'
                      : 'bg-slate-800 text-cyan-400 hover:bg-slate-700'
                  }`}
                >
                  User Guide
                </button>
                <div className="flex items-center gap-3 text-slate-500 text-sm">
                  <LLMCallCounter />
                  {lastDuration && <span>{lastDuration}</span>}
                </div>
              </div>
              {/* History Panel Toggle */}
              <button
                onClick={() => { setSidebarOpen(!sidebarOpen); setMobileMenuOpen(false); }}
                className="min-h-[44px] px-4 py-2 bg-slate-800 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors text-left"
              >
                {sidebarOpen ? 'Hide' : 'Show'} History Panel
              </button>
            </div>
          </div>
        )}

        {/* Desktop Header Row */}
        <div className="hidden md:flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-cyan-400 text-2xl font-bold">NLQ</span>
              <span className="text-slate-300 text-lg font-normal hidden lg:inline">Natural Language Query</span>
            </div>

            {/* View Mode Toggle */}
            <div className="flex items-center gap-2 ml-8">
              <span className="text-slate-500 text-sm hidden lg:inline">View:</span>
              <div className="flex items-center gap-1 bg-slate-900 rounded-lg p-1">
                <button
                  onClick={() => setViewMode('galaxy')}
                  className={`min-h-[44px] px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    viewMode === 'galaxy'
                      ? 'bg-slate-700 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Galaxy
                </button>
                <button
                  onClick={() => setViewMode('dashboard')}
                  className={`min-h-[44px] px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    viewMode === 'dashboard'
                      ? 'bg-slate-700 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Dashboard
                </button>
                <button
                  onClick={() => setViewMode('guide')}
                  className={`min-h-[44px] px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    viewMode === 'guide'
                      ? 'bg-slate-700 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  User Guide
                </button>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4 text-slate-500 text-sm">
            {/* Static/AI Mode Toggle */}
            <div className="flex items-center gap-2">
              <span className="text-slate-500 text-xs">Mode:</span>
              <div className="flex items-center bg-slate-900 rounded-lg p-0.5">
                <button
                  onClick={() => setQueryMode('static')}
                  className={`min-h-[44px] px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                    queryMode === 'static'
                      ? 'bg-amber-600 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Static
                </button>
                <button
                  onClick={() => setQueryMode('ai')}
                  className={`min-h-[44px] px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                    queryMode === 'ai'
                      ? 'bg-emerald-600 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  AI
                </button>
              </div>
            </div>
            <LLMCallCounter />
            {lastDuration && <span className="text-slate-400">{lastDuration}</span>}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Main Content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Query Input Section - Only shown in Galaxy view */}
          {viewMode === 'galaxy' && (
            <div className="flex flex-col items-center pt-4 pb-3 px-6">
              <div className="w-full max-w-2xl">
                <div className="relative">
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask any question, use a preset below, or just say hi..."
                    className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-200 text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
                  />
                  {isLoading && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                      <svg className="w-4 h-4 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                    </div>
                  )}
                </div>
              </div>

              {/* Quick Action Buttons - Horizontally scrollable with fade edges */}
              <div className="relative w-full max-w-2xl mt-3">
                {/* Left fade edge */}
                <div className="absolute left-0 top-0 bottom-0 w-6 bg-gradient-to-r from-slate-950 to-transparent z-10 pointer-events-none" />
                {/* Right fade edge */}
                <div className="absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-slate-950 to-transparent z-10 pointer-events-none" />
                {/* Scrollable container */}
                <div className="flex items-center gap-2 overflow-x-auto px-6 py-1 scrollbar-hide">
                  {quickActions.map((action) => (
                    <button
                      key={action}
                      onClick={() => submitGalaxyQuery(action)}
                      className="flex-shrink-0 px-3 py-1 bg-cyan-900/30 border border-cyan-700/50 rounded-full text-cyan-300 text-xs hover:bg-cyan-800/40 hover:text-cyan-200 transition-colors whitespace-nowrap"
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Results Area */}
          <div className="flex-1 overflow-hidden">
            {/* Dashboard View - Always uses DashboardRenderer with full controls */}
            {viewMode === 'dashboard' && (
              <div className="h-full overflow-hidden flex flex-col">
                {/* Dashboard Header with Persona Selector - Compact on mobile */}
                <div className="flex-shrink-0 px-4 md:px-6 py-2 md:py-3 border-b border-slate-800 bg-slate-900/50">
                  <div className="flex items-center justify-between gap-2">
                    {/* Mobile: Dropdown selector */}
                    <div className="md:hidden flex items-center gap-2">
                      <select
                        value={selectedPersona}
                        onChange={(e) => handlePersonaSelect(e.target.value as Persona)}
                        disabled={isGeneratingDashboard}
                        className="min-h-[36px] px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-cyan-300 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-cyan-500/50 disabled:opacity-50"
                      >
                        {personaOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label} Dashboard
                          </option>
                        ))}
                      </select>
                      {isGeneratingDashboard && (
                        <svg className="w-4 h-4 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                      )}
                    </div>

                    {/* Desktop: Button tabs */}
                    <div className="hidden md:flex items-center gap-2">
                      <span className="text-slate-500 text-xs">Quick Load:</span>
                      <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1">
                        {personaOptions.map((option) => (
                          <button
                            key={option.value}
                            onClick={() => handlePersonaSelect(option.value)}
                            disabled={isGeneratingDashboard}
                            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors disabled:opacity-50 ${
                              selectedPersona === option.value
                                ? 'bg-cyan-600 text-white'
                                : 'text-slate-400 hover:text-slate-200'
                            }`}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Help Text - Desktop only */}
                    <div className="hidden lg:block px-3 py-1.5 bg-cyan-900/30 border border-cyan-700/50 rounded-lg">
                      <p className="text-cyan-300 text-xs">
                        💡 Drag to rearrange • Resize corners • Chatbox to refine
                      </p>
                    </div>
                  </div>
                </div>

                {/* DashboardRenderer - Full builder functionality */}
                <div className="flex-1 overflow-hidden">
                  <DashboardRenderer
                    initialSchema={dashboardSchema || undefined}
                    initialWidgetData={dashboardWidgetData}
                    onDrillDown={handleDashboardDrillDown}
                    onRefinement={handleDashboardRefinement}
                    showRefinementInput={true}
                    refinePresets={personaOptions.find(p => p.value === selectedPersona)?.refinePresets || []}
                    persona={selectedPersona}
                  />
                </div>

                {/* Error display */}
                {dashboardError && (
                  <div className="px-6 py-3 bg-red-900/20 border-t border-red-800/50 text-red-400 text-sm">
                    {dashboardError}
                  </div>
                )}
              </div>
            )}

            {/* Galaxy View */}
            {viewMode === 'galaxy' && hasGalaxyResponse && (
              <div className="h-full overflow-hidden">
                <GalaxyView data={galaxyResponse} />
              </div>
            )}

            {/* Empty State for Galaxy */}
            {viewMode === 'galaxy' && !hasGalaxyResponse && !isLoading && (
              <div className="h-full flex items-center justify-center text-slate-500">
                <p>Enter a query above to see results</p>
              </div>
            )}

            {/* User Guide View */}
            {viewMode === 'guide' && (
              <UserGuide />
            )}
          </div>
        </main>

        {/* Sidebar Toggle Button - Desktop only */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="hidden md:block absolute right-0 top-1/2 -translate-y-1/2 z-10 min-h-[44px] min-w-[44px] p-2 bg-slate-800 border border-slate-700 rounded-l-lg hover:bg-slate-700 transition-colors"
          style={{ right: sidebarOpen ? '283px' : '0' }}
        >
          <svg className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {sidebarOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            )}
          </svg>
        </button>

        {/* Mobile Sidebar Backdrop */}
        {sidebarOpen && (
          <div
            className="md:hidden fixed inset-0 bg-black/50 z-30"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Right Sidebar - Full overlay on mobile, fixed width on desktop */}
        <aside className={`
          fixed md:relative right-0 top-0 h-full z-40 md:z-auto
          w-[85vw] max-w-[320px]
          border-l border-slate-800 flex flex-col bg-slate-900 md:bg-slate-900/30
          transition-all duration-300
          ${sidebarOpen
            ? 'translate-x-0 md:w-[283px]'
            : 'translate-x-full md:translate-x-0 md:w-0 md:overflow-hidden'
          }
        `}>
          {/* Mobile Close Button */}
          <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-slate-800">
            <span className="text-slate-300 font-medium">Panel</span>
            <button
              onClick={() => setSidebarOpen(false)}
              className="min-h-[44px] min-w-[44px] p-2 text-slate-400 hover:text-white transition-colors"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Panel Tabs */}
          <div className="flex border-b border-slate-800 overflow-x-auto">
            {(['History', 'Learning', 'Data Gaps'] as PanelTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setPanelTab(tab)}
                className={`flex-1 min-h-[44px] px-3 md:px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
                  panelTab === tab
                    ? 'text-white border-b-2 border-cyan-400 bg-slate-900/50'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Panel Content */}
          <div className="flex-1 overflow-y-auto">
            {panelTab === 'History' && (
              <div className="p-3">
                {queryHistory.length === 0 ? (
                  <div className="text-slate-500 text-sm text-center py-8">
                    No queries yet
                  </div>
                ) : (
                  <div className="space-y-1">
                    {queryHistory.map((item) => (
                      <div
                        key={item.id}
                        onClick={() => submitGalaxyQuery(item.query)}
                        className="p-3 rounded-lg hover:bg-slate-800/50 cursor-pointer transition-colors"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-slate-200 text-sm truncate flex-1">{item.query}</p>
                          {item.count > 1 && (
                            <span className="text-cyan-400/70 text-xs font-medium bg-cyan-400/10 px-1.5 py-0.5 rounded">
                              ×{item.count}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-slate-500 text-xs">{item.timestamp}</span>
                          <span className="text-slate-600 text-xs">{item.duration}</span>
                          <span className="text-cyan-400/70 text-xs truncate">{item.tag}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {panelTab === 'Learning' && (
              <RAGLearningPanel
                refreshInterval={5000}
                maxEntries={50}
              />
            )}

            {panelTab === 'Data Gaps' && (
              <InsufficientDataPanel
                refreshInterval={5000}
                maxEntries={50}
              />
            )}

          </div>
        </aside>
      </div>
    </div>
  )
}

export default App
