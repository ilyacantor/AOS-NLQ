import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react'
import type { IntentMapResponse } from './components/galaxy'
import type { DashboardSchema } from './components/generated-dashboard'
import { RAGLearningPanel, LLMCallCounter, useSessionId, refreshLLMStats } from './components/rag'
import { InsufficientDataPanel } from './components/rag/InsufficientDataPanel'
import { DebugTracePanel } from './components/DebugTracePanel'
import { DataPipelineStatus } from './components/DataPipelineStatus'
import { ProductTour } from './components/ProductTour'
import { LandingPage } from './components/LandingPage'

// Lazy-load the three view components — only the active view's code is downloaded
const GalaxyView = React.lazy(() =>
  import('./components/galaxy/GalaxyView').then(m => ({ default: m.GalaxyView }))
)
const DashboardRenderer = React.lazy(() =>
  import('./components/generated-dashboard/DashboardRenderer')
)
const UserGuide = React.lazy(() =>
  import('./components/UserGuide').then(m => ({ default: m.UserGuide }))
)
const FinancialStatementView = React.lazy(() =>
  import('./components/financial-statement/FinancialStatementView').then(m => ({ default: m.FinancialStatementView }))
)
const BridgeChart = React.lazy(() =>
  import('./components/bridge-chart/BridgeChart').then(m => ({ default: m.BridgeChart }))
)
const ReportPortal = React.lazy(() =>
  import('./components/report-portal/ReportPortal').then(m => ({ default: m.ReportPortal }))
)

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

type ViewMode = 'galaxy' | 'dashboard' | 'guide' | 'reports'
type Persona = 'CFO' | 'CRO' | 'COO' | 'CTO' | 'CHRO'
type PanelTab = 'History' | 'Learning' | 'Data Gaps' | 'Trace'

const personaOptions: { label: string; value: Persona; query: string; refinePresets: string[] }[] = [
  {
    label: 'CFO',
    value: 'CFO',
    query: 'Show me a finance dashboard with revenue KPI, gross margin percent KPI, operating margin trend, net income KPI, EBITDA KPI, and cash KPI',
    refinePresets: ['Add EBITDA margin card', 'Show revenue trend', 'Add operating margin KPI', 'Show net margin trend']
  },
  {
    label: 'CRO',
    value: 'CRO',
    query: 'Show me a sales dashboard with ARR KPI, pipeline KPI, bookings trend over time, win rate KPI, and quota attainment by rep',
    refinePresets: ['Who is our top rep?', 'What is our largest deal?', 'Show pipeline by salesperson', 'Show NRR trend']
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
    refinePresets: ['Which service has the best SLO?', 'Show tech debt trend', 'Add features shipped', 'Filter to Platform']
  },
  {
    label: 'CHRO',
    value: 'CHRO',
    query: 'Show me a people dashboard with total headcount KPI, turnover rate KPI, time to hire trend, employee satisfaction KPI, and engagement breakdown',
    refinePresets: ['Add training hours card', 'Show hiring trend', 'Break down by department', 'Add retention rate']
  },
]

const quickActions = [
  'hi',
  'why did rev incr',
  '2025 KPIs in dash',
  '2025 P&L',
  'platform stable?',
  'whats the margin',
  'are we profitable',
  'churn?',
  'headcount',
  'pipeline',
  'how are we doing',
  'nrr',
  'arr',
]

function App() {
  // Core state
  const [query, setQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('galaxy')
  const [selectedPersona, setSelectedPersona] = useState<Persona>('CFO')
  const [panelTab, setPanelTab] = useState<PanelTab>('History')
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([])
  // Bumped after every query completes — triggers a re-fetch from the server
  // so that deduplicated counts are always accurate.
  const [historyVersion, setHistoryVersion] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [galaxyResponse, setGalaxyResponse] = useState<IntentMapResponse | null>(null)
  const [lastDuration, setLastDuration] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [dataMode, setDataMode] = useState<'live' | 'demo'>('live')
  const [liveDataAvailable, setLiveDataAvailable] = useState<boolean>(false)
  const [dclWaitSeconds, setDclWaitSeconds] = useState<number>(0)

  // Backend connectivity state
  const [backendStatus, setBackendStatus] = useState<'checking' | 'connected' | 'error'>('checking')
  const [backendMessage, setBackendMessage] = useState<string | null>(null)
  const [claudeAvailable, setClaudeAvailable] = useState<boolean | null>(null)

  // Landing page & product tour state
  const [showLanding, setShowLanding] = useState(false)
  const [tourVisible, setTourVisible] = useState(false)
  const [tourQuerySubmitted, setTourQuerySubmitted] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Dashboard state - always use DashboardRenderer
  // Restore from sessionStorage so dashboards survive view mode switches
  const [dashboardSchema, setDashboardSchema] = useState<DashboardSchema | null>(() => {
    try {
      const stored = sessionStorage.getItem('aos_dashboard_schema')
      return stored ? JSON.parse(stored) : null
    } catch { return null }
  })
  const [dashboardWidgetData, setDashboardWidgetData] = useState<Record<string, any>>(() => {
    try {
      const stored = sessionStorage.getItem('aos_dashboard_data')
      return stored ? JSON.parse(stored) : {}
    } catch { return {} }
  })
  const [isGeneratingDashboard, setIsGeneratingDashboard] = useState(false)
  const [dashboardError, setDashboardError] = useState<string | null>(null)

  const [hasLoadedDefaultDashboard, setHasLoadedDefaultDashboard] = useState(false)
  const [financialStatementData, setFinancialStatementData] = useState<any>(null)
  const [bridgeChartData, setBridgeChartData] = useState<any>(null)
  const sessionId = useSessionId()

  const queryRef = useRef(query)
  queryRef.current = query

  const dataModeRef = useRef(dataMode)
  dataModeRef.current = dataMode

  // Load deduplicated query history from the server.
  // Re-fetches whenever historyVersion is bumped (after each query completes).
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const response = await fetch('/api/v1/rag/history?limit=50')
        if (response.ok) {
          const data = await response.json()
          const historyItems: QueryHistoryItem[] = (data.entries || []).map((entry: any) => ({
            id: entry.normalized_query || entry.query,
            query: entry.query,
            timestamp: entry.last_used
              ? new Date(entry.last_used).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
              : '',
            duration: entry.execution_time_ms ? `${entry.execution_time_ms}ms` : '',
            tag: entry.tag || 'UNKNOWN',
            count: entry.count || 1,
          }))
          setQueryHistory(historyItems)
        } else if (response.status === 503) {
          // Supabase unavailable — show error in History tab
          console.error('History endpoint returned 503 — Supabase unavailable')
        }
      } catch (error) {
        console.error('Failed to load history:', error)
      }
    }
    loadHistory()
  }, [historyVersion])

  // Health check on mount — verify backend is reachable and show diagnostic banner
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/v1/health')
        if (res.ok) {
          const data = await res.json()
          setBackendStatus('connected')
          setClaudeAvailable(data.claude_available ?? null)
          setLiveDataAvailable(data.live_data_available ?? false)
          if (!data.claude_available) {
            setBackendMessage('ANTHROPIC_API_KEY not set — AI queries will fail.')
          } else {
            setBackendMessage(null)
          }
        } else {
          setBackendStatus('error')
          setBackendMessage(`Backend returned ${res.status}. Check server logs for errors.`)
        }
      } catch {
        setBackendStatus('error')
        setBackendMessage('Backend unreachable. Make sure NLQ backend is running (port 8005).')
      }
    }
    checkHealth()
    // Re-check every 30s
    const interval = setInterval(checkHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  // DCL wait counter — ticks every second while live data is unavailable
  useEffect(() => {
    if (dataMode !== 'live' || liveDataAvailable) {
      setDclWaitSeconds(0)
      return
    }
    const timer = setInterval(() => setDclWaitSeconds(s => s + 1), 1000)
    return () => clearInterval(timer)
  }, [dataMode, liveDataAvailable])

  // Submit query — ONE endpoint, ONE path: /api/v1/query
  const submitQuery = useCallback(async (queryText: string) => {
    if (!queryText.trim()) return

    setIsLoading(true)
    setFinancialStatementData(null)
    setBridgeChartData(null)
    setQuery('')
    setGalaxyResponse(null)
    const timestamp = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    const startTime = performance.now()

    try {
      const res = await fetchWithRetry('/api/v1/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: queryText,
          reference_date: new Date().toISOString().split('T')[0],
          session_id: sessionId,
          data_mode: dataModeRef.current,
          persona: selectedPersona
        })
      })

      const duration = Math.round(performance.now() - startTime)
      setLastDuration(`${duration}ms`)

      // Check HTTP status BEFORE parsing JSON
      if (!res.ok) {
        let errorDetail = `Server error (${res.status})`
        try {
          const errBody = await res.json()
          errorDetail = errBody.detail || errBody.error || errBody.answer || errorDetail
        } catch {
          errorDetail = `${res.status} ${res.statusText}`
        }
        console.error('Backend error:', res.status, errorDetail)
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
          primary_answer: 'Something went wrong processing your query. Try rephrasing or check the Trace tab for details.',
          text_response: 'Something went wrong processing your query. Try rephrasing or check the Trace tab for details.',
          needs_clarification: false,
          clarification_prompt: null,
          debug_info: { error: errorDetail, error_type: 'HTTP_ERROR' },
        } as IntentMapResponse)

        const newItem: QueryHistoryItem = {
          id: Date.now().toString(),
          query: queryText,
          timestamp,
          duration: `${duration}ms`,
          tag: 'ERROR',
          count: 1,
        }
        setQueryHistory(prev => [newItem, ...prev.filter(h => h.query.toLowerCase().trim() !== newItem.query.toLowerCase().trim())].slice(0, 100))
        setIsLoading(false)
        refreshLLMStats()
        setHistoryVersion(v => v + 1)
        return
      }

      const data = await res.json()

      // NLQResponse from /api/v1/query — adapt to IntentMapResponse shape for GalaxyView
      // (GalaxyView will break rendering-wise, but this keeps the state plumbing working)
      const adapted: IntentMapResponse = {
        query: queryText,
        query_type: data.parsed_intent || data.response_type || 'QUERY',
        ambiguity_type: null,
        persona: data.persona || 'CFO',
        overall_confidence: data.confidence ?? 0,
        overall_data_quality: data.confidence ?? 0,
        node_count: 0,
        nodes: [],
        primary_node_id: null,
        primary_answer: data.answer || data.error_message || null,
        text_response: data.answer || data.error_message || null,
        needs_clarification: data.needs_clarification || false,
        clarification_prompt: data.clarification_prompt || null,
        dashboard: data.dashboard || null,
        dashboard_data: data.dashboard_data || null,
        response_type: data.response_type || 'text',
        debug_info: data.debug_info || null,
        provenance: data.provenance || null,
        data_source: data.data_source || null,
      } as IntentMapResponse

      // Auto-navigate based on response type:
      // - Financial statement → show FinancialStatementView in galaxy area
      // - Dashboard response → switch to dashboard view
      // - Non-dashboard response → switch to galaxy view (so result is visible)
      if (data.response_type === 'financial_statement' && data.financial_statement_data) {
        setFinancialStatementData(data.financial_statement_data)
        setViewMode('galaxy')
        setGalaxyResponse(adapted)
      } else if (data.response_type === 'bridge_chart' && data.bridge_chart_data) {
        setBridgeChartData(data.bridge_chart_data)
        setViewMode('galaxy')
        setGalaxyResponse(adapted)
      } else if (data.response_type === 'dashboard' && data.dashboard) {
        setDashboardSchema(data.dashboard)
        setDashboardWidgetData(data.dashboard_data || {})
        // Persist to sessionStorage so dashboard survives view mode switches
        try {
          sessionStorage.setItem('aos_dashboard_schema', JSON.stringify(data.dashboard))
          sessionStorage.setItem('aos_dashboard_data', JSON.stringify(data.dashboard_data || {}))
        } catch { /* sessionStorage full or unavailable — non-fatal */ }
        setViewMode('dashboard')
        setGalaxyResponse(null)
      } else {
        setViewMode('galaxy')
        setGalaxyResponse(adapted)
      }

      const newItem: QueryHistoryItem = {
        id: Date.now().toString(),
        query: queryText,
        timestamp,
        duration: `${duration}ms`,
        tag: data.parsed_intent || data.response_type || 'query',
        count: 1,
      }
      setQueryHistory(prev => [newItem, ...prev.filter(h => h.query.toLowerCase().trim() !== newItem.query.toLowerCase().trim())].slice(0, 100))
    } catch (error) {
      console.error('Network error — backend unreachable:', error)
      const duration = Math.round(performance.now() - startTime)
      setLastDuration(`${duration}ms`)
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
        primary_answer: 'Cannot reach the backend server. Make sure both services are running.',
        text_response: 'Cannot reach the backend server. Make sure both services are running.',
        needs_clarification: false,
        clarification_prompt: null,
        debug_info: { error: String(error), error_type: 'NETWORK_ERROR' },
      } as IntentMapResponse)
    }

    setIsLoading(false)
    refreshLLMStats()
    setHistoryVersion(v => v + 1)
  }, [sessionId, selectedPersona])

  // ── Parent iframe communication ────────────────────────────────────
  // Listens for postMessage commands from the AOS platform shell.
  // Supported actions:
  //   { action: 'navigateTo', tab: 'galaxy' | 'dashboard' | 'reports' | 'guide' }
  //   { action: 'setPersona', persona: 'CFO' | 'CRO' | 'COO' | 'CTO' | 'CHRO' }
  //   { action: 'submitQuery', query: '...' }
  //   { action: 'reportNavigate', entity?: 'meridian'|'cascadia'|'combined', tab?: string }
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const data = event.data
      if (!data || typeof data !== 'object' || !data.action) return

      console.log('[NLQ] postMessage received:', data)

      switch (data.action) {
        case 'navigateTo': {
          const validTabs: ViewMode[] = ['galaxy', 'dashboard', 'guide', 'reports']
          if (validTabs.includes(data.tab)) {
            setViewMode(data.tab as ViewMode)
          } else {
            console.warn(`[NLQ] Unknown tab: ${data.tab}`)
          }
          break
        }
        case 'setPersona': {
          const validPersonas: Persona[] = ['CFO', 'CRO', 'COO', 'CTO', 'CHRO']
          if (validPersonas.includes(data.persona)) {
            setSelectedPersona(data.persona as Persona)
          }
          break
        }
        case 'submitQuery': {
          if (typeof data.query === 'string' && data.query.trim()) {
            setViewMode('galaxy')
            submitQuery(data.query)
          }
          break
        }
        case 'reportNavigate': {
          // Switch to Reports view and dispatch internal navigation event
          // so ReportPortal can update entity/tab state.
          // ReportPortal is lazy-loaded and conditionally rendered — it only
          // mounts after setViewMode triggers a re-render + Suspense resolves.
          // Delay the event so the listener is attached before it fires.
          setViewMode('reports')
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('aos-report-navigate', {
              detail: { entity: data.entity, tab: data.tab },
            }))
          }, 500)
          break
        }
        default:
          console.log(`[NLQ] Unknown action: ${data.action}`)
      }
    }

    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [submitQuery])

  // Handle persona selection - submit persona dashboard query through unified endpoint
  const handlePersonaSelect = useCallback((persona: Persona) => {
    setSelectedPersona(persona)
    const personaConfig = personaOptions.find(p => p.value === persona)
    if (personaConfig) {
      submitQuery(personaConfig.query)
    }
  }, [submitQuery])

  // Load default dashboard when user first navigates to the Dashboard tab
  // (not on mount — Ask tab is the landing page)
  useEffect(() => {
    if (viewMode === 'dashboard' && !hasLoadedDefaultDashboard) {
      setHasLoadedDefaultDashboard(true)
      const personaConfig = personaOptions.find(p => p.value === selectedPersona)
      if (personaConfig) {
        submitQuery(personaConfig.query)
      }
    }
  }, [viewMode, hasLoadedDefaultDashboard, selectedPersona, submitQuery])

  // Handle form submit
  const handleSubmit = useCallback(() => {
    const currentQuery = queryRef.current
    if (currentQuery.trim()) {
      submitQuery(currentQuery)
      setTourQuerySubmitted(true)
    }
  }, [submitQuery])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  // Handle drill-down from dashboard tiles - submit through unified query endpoint
  const handleDashboardDrillDown = useCallback((drillQuery: string) => {
    setViewMode('galaxy')
    submitQuery(drillQuery)
  }, [submitQuery])

  // Handle dashboard refinement from DashboardRenderer
  // Keeps App.tsx state in sync with DashboardRenderer's internal state
  const handleDashboardRefinement = useCallback((newSchema: DashboardSchema, widgetData?: Record<string, any>) => {
    setDashboardSchema(newSchema)
    if (widgetData) {
      setDashboardWidgetData(widgetData)
    }
    // Persist refined dashboard to sessionStorage
    try {
      sessionStorage.setItem('aos_dashboard_schema', JSON.stringify(newSchema))
      if (widgetData) {
        sessionStorage.setItem('aos_dashboard_data', JSON.stringify(widgetData))
      }
    } catch { /* non-fatal */ }
  }, [])

  // Handle navigation from DashboardRenderer when it detects a factual query
  // (should go to Galaxy space instead of refining the dashboard)
  const handleNavigateToGalaxy = useCallback((queryText: string) => {
    // Switch to galaxy view and submit the query
    setViewMode('galaxy')
    submitQuery(queryText)
  }, [submitQuery])

  // ── Landing page handler ──
  const handleLandingStart = useCallback((_persona: 'business' | 'technology') => {
    setShowLanding(false)
    setTourVisible(true)
    setTourQuerySubmitted(false)
  }, [])

  // ── Tour callbacks ──
  const handleTourDismiss = useCallback(() => {
    setTourVisible(false)
    localStorage.setItem('nlq_tour_completed', '1')
  }, [])

  const handleTourNavigate = useCallback((view: ViewMode) => {
    setViewMode(view)
  }, [])

  const handleTourFocusSearch = useCallback(() => {
    // Switch to galaxy first so the input is in the DOM
    setViewMode('galaxy')
    setTimeout(() => searchInputRef.current?.focus(), 100)
  }, [])

  // Launch demo (opens landing page overlay)
  const startDemo = useCallback(() => {
    setShowLanding(true)
  }, [])

  // Tour step-enter handler — runs actions when specific steps become active
  const handleTourStepEnter = useCallback((stepIndex: number) => {
    // Step 2 = Dashboard View → open persona dropdown and select CTO
    if (stepIndex === 2) {
      setTimeout(() => {
        const select = document.getElementById('dashboard-persona-select') as HTMLSelectElement | null
        if (select) {
          select.focus()
          select.size = select.options.length
          setTimeout(() => {
            select.size = 1
            handlePersonaSelect('CTO' as Persona)
          }, 1200)
        }
      }, 600)
    }
    // Step 4 = What-If → switch back to CFO and open the scenario panel
    if (stepIndex === 4) {
      handlePersonaSelect('CFO' as Persona)
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent('tour:open-whatif'))
      }, 800)
    }
  }, [handlePersonaSelect])

  // Public method to re-trigger tour (called from UserGuide)
  const startTour = useCallback(() => {
    setViewMode('galaxy')
    setTourQuerySubmitted(false)
    setTourVisible(true)
  }, [])

  // Global Escape key — close overlays in App scope (sidebar, mobile menu, landing)
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (showLanding) { setShowLanding(false); return }
      if (mobileMenuOpen) { setMobileMenuOpen(false); return }
      if (sidebarOpen) { setSidebarOpen(false); return }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [showLanding, mobileMenuOpen, sidebarOpen])

  const hasGalaxyResponse = galaxyResponse !== null

  return (
    <div className="h-screen bg-slate-950 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="border-b border-slate-800 relative z-[60]">
        {/* Mobile Header Row */}
        <div className="flex items-center justify-between px-4 py-3 md:hidden">
          <div className="flex items-center gap-2">
            <span className="text-cyan-400 text-xl font-bold">NLQ</span>
            <DataPipelineStatus dataMode={dataMode} />
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
                Ask
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
              <button
                onClick={() => setViewMode('reports')}
                className={`min-h-[44px] min-w-[44px] px-2 rounded-md text-xs font-medium transition-colors ${
                  viewMode === 'reports'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Reports
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
                <button
                  onClick={() => { setViewMode('reports'); setMobileMenuOpen(false); }}
                  className={`min-h-[44px] px-4 py-2 rounded-lg transition-colors ${
                    viewMode === 'reports'
                      ? 'bg-slate-700 text-white'
                      : 'bg-slate-800 text-cyan-400 hover:bg-slate-700'
                  }`}
                >
                  Reports
                </button>
                <div className="flex items-center gap-3 text-slate-500 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500 text-xs">Data:</span>
                    <select
                      value={dataMode}
                      onChange={(e) => setDataMode(e.target.value as 'live' | 'demo')}
                      className="bg-slate-800 text-slate-300 text-xs rounded-md px-2 py-1 border border-slate-700 focus:border-cyan-400 focus:outline-none cursor-pointer"
                    >
                      <option value="live">Live</option>
                      <option value="demo">Demo</option>
                    </select>
                  </div>
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
                  id="nav-tab-galaxy"
                  onClick={() => setViewMode('galaxy')}
                  className={`min-h-[44px] px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    viewMode === 'galaxy'
                      ? 'bg-slate-700 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Ask
                </button>
                <button
                  id="nav-tab-dashboard"
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
                  id="nav-tab-guide"
                  onClick={() => setViewMode('guide')}
                  className={`min-h-[44px] px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    viewMode === 'guide'
                      ? 'bg-slate-700 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  User Guide
                </button>
                <button
                  id="nav-tab-reports"
                  onClick={() => setViewMode('reports')}
                  className={`min-h-[44px] px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    viewMode === 'reports'
                      ? 'bg-slate-700 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Reports
                </button>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4 text-slate-500 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-slate-500 text-xs">Data:</span>
              <select
                value={dataMode}
                onChange={(e) => setDataMode(e.target.value as 'live' | 'demo')}
                className="bg-slate-800 text-slate-300 text-xs rounded-md px-2 py-1 border border-slate-700 focus:border-cyan-400 focus:outline-none cursor-pointer"
              >
                <option value="live">Live</option>
                <option value="demo">Demo</option>
              </select>
            </div>
            <DataPipelineStatus dataMode={dataMode} />
            <LLMCallCounter />
            {lastDuration && <span className="text-slate-400">{lastDuration}</span>}
            <button
              onClick={startDemo}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors border border-cyan-400 text-cyan-400 hover:bg-cyan-400/10"
            >
              Tour
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Main Content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Results Area */}
          <div className="flex-1 overflow-hidden">
            {/* Dashboard View - Always uses DashboardRenderer with full controls */}
            {viewMode === 'dashboard' && (
              <Suspense fallback={<div className="flex-1 flex items-center justify-center"><svg className="w-8 h-8 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg></div>}>
              <div className="h-full overflow-hidden flex flex-col">
                {/* DashboardRenderer - Full builder functionality with integrated persona selector */}
                <div className="flex-1 overflow-hidden">
                  <DashboardRenderer
                    initialSchema={dashboardSchema || undefined}
                    initialWidgetData={dashboardWidgetData}
                    onDrillDown={handleDashboardDrillDown}
                    onRefinement={handleDashboardRefinement}
                    onNavigateToGalaxy={handleNavigateToGalaxy}
                    showRefinementInput={false}
                    refinePresets={personaOptions.find(p => p.value === selectedPersona)?.refinePresets || []}
                    persona={selectedPersona}
                    personaOptions={personaOptions.map(p => ({ label: p.label, value: p.value }))}
                    onPersonaChange={(value) => handlePersonaSelect(value as Persona)}
                    isGenerating={isGeneratingDashboard}
                    dataMode={dataMode}
                    sessionId={sessionId}
                  />
                </div>

                {/* Error display */}
                {dashboardError && (
                  <div className="px-6 py-3 bg-red-900/20 border-t border-red-800/50 text-red-400 text-sm">
                    {dashboardError}
                  </div>
                )}
              </div>
              </Suspense>
            )}

            {/* Galaxy View — chatbox centered, visual appears above when results load */}
            {viewMode === 'galaxy' && (
              <div className="h-full flex flex-col overflow-hidden">
                {/* Financial statement, Bridge chart, or Galaxy visualization */}
                {financialStatementData ? (
                  <div id="financial-statement-visual" className="flex-1 overflow-auto min-h-0">
                    <Suspense fallback={<div className="flex-1 flex items-center justify-center"><svg className="w-8 h-8 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg></div>}>
                    <FinancialStatementView
                      data={financialStatementData}
                      sessionId={sessionId}
                    />
                    </Suspense>
                  </div>
                ) : bridgeChartData ? (
                  <div id="bridge-chart-visual" className="flex-1 overflow-auto min-h-0">
                    <Suspense fallback={<div className="flex-1 flex items-center justify-center"><svg className="w-8 h-8 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg></div>}>
                    <BridgeChart
                      data={bridgeChartData}
                      sessionId={sessionId}
                    />
                    </Suspense>
                  </div>
                ) : hasGalaxyResponse && (
                  <div id="galaxy-visual" className="flex-1 overflow-hidden min-h-0">
                    <Suspense fallback={<div className="flex-1 flex items-center justify-center"><svg className="w-8 h-8 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg></div>}>
                    <GalaxyView
                      data={galaxyResponse}
                    />
                    </Suspense>
                  </div>
                )}

                {/* Loading state — replaces visual area while loading */}
                {isLoading && !hasGalaxyResponse && (
                  <div className="flex-1 flex items-center justify-center">
                    <div className="flex flex-col items-center gap-3">
                      <svg className="w-8 h-8 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      <p className="text-slate-400 text-sm">Analyzing query...</p>
                    </div>
                  </div>
                )}

                {/* Top spacer — pushes chatbox to vertical center when no results */}
                {!hasGalaxyResponse && !isLoading && (
                  <div className="flex-1" />
                )}

                {/* Chatbox — centered in the page, below the visual */}
                <div className={`flex flex-col items-center px-6 ${hasGalaxyResponse ? 'pt-3 pb-3 border-t border-slate-800/50' : 'pb-4'}`}>
                  {/* DCL loading banner — shown when in live mode but no ingested data yet */}
                  {dataMode === 'live' && !liveDataAvailable && (
                    <div className="w-full max-w-2xl mb-3 px-4 py-2.5 bg-amber-900/30 border border-amber-600/40 rounded-lg flex items-center gap-3">
                      <svg className="w-4 h-4 animate-spin text-amber-400 flex-shrink-0" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-amber-200">
                          Waiting for DCL live data pipeline
                          <span className="text-amber-400/70 font-mono ml-2 text-xs">{dclWaitSeconds}s</span>
                        </p>
                        <p className="text-xs text-amber-200/50 mt-0.5">
                          Queries will return empty results until ingested data is available. Switch to Demo to use sample data.
                        </p>
                      </div>
                    </div>
                  )}
                  <div className="w-full max-w-2xl">
                    <div className="relative">
                      <input
                        ref={searchInputRef}
                        id="nlq-search-input"
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Ask any question, use a preset below, or just say hi..."
                        className="w-full px-4 py-3 bg-slate-800/80 border border-slate-700 rounded-xl text-slate-200 text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 shadow-lg shadow-black/20"
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

                  {/* Quick Action Buttons */}
                  <div id="nlq-quick-actions" className="relative w-full max-w-2xl mt-3">
                    <div className="absolute left-0 top-0 bottom-0 w-6 bg-gradient-to-r from-slate-950 to-transparent z-10 pointer-events-none" />
                    <div className="absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-slate-950 to-transparent z-10 pointer-events-none" />
                    <div className="flex items-center gap-2 overflow-x-auto px-6 py-1 scrollbar-hide">
                      {quickActions.map((action) => (
                        <button
                          key={action}
                          onClick={() => { submitQuery(action); setTourQuerySubmitted(true) }}
                          className="flex-shrink-0 px-3 py-1 bg-cyan-900/30 border border-cyan-700/50 rounded-full text-cyan-300 text-xs hover:bg-cyan-800/40 hover:text-cyan-200 transition-colors whitespace-nowrap"
                        >
                          {action}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Bottom spacer — pushes chatbox to vertical center when no results */}
                {!hasGalaxyResponse && !isLoading && (
                  <div className="flex-1" />
                )}
              </div>
            )}

            {/* User Guide View */}
            {viewMode === 'guide' && (
              <Suspense fallback={<div className="flex-1 flex items-center justify-center"><svg className="w-8 h-8 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg></div>}>
              <UserGuide onStartTour={startTour} />
              </Suspense>
            )}

            {/* Reports Portal View */}
            {viewMode === 'reports' && (
              <Suspense fallback={<div className="flex-1 flex items-center justify-center"><svg className="w-8 h-8 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg></div>}>
                <ReportPortal onClose={() => setViewMode('galaxy')} />
              </Suspense>
            )}
          </div>
        </main>

        {/* Sidebar Toggle Button - Desktop only */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="hidden md:flex absolute right-0 top-1/2 -translate-y-1/2 z-10 min-w-[28px] px-1 py-3 bg-slate-800 border border-slate-700 rounded-l-lg hover:bg-slate-700 transition-colors flex-col items-center justify-center gap-1"
          style={{ right: sidebarOpen ? '283px' : '0' }}
        >
          <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {sidebarOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            )}
          </svg>
          <span className="text-[10px] text-slate-400 font-medium" style={{ writingMode: 'vertical-rl' }}>History</span>
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
            {(['History', 'Learning', 'Data Gaps', 'Trace'] as PanelTab[]).map((tab) => (
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
                        onClick={() => submitQuery(item.query)}
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
                refreshInterval={sidebarOpen ? 5000 : 0}
                maxEntries={50}
              />
            )}

            {panelTab === 'Data Gaps' && (
              <InsufficientDataPanel
                refreshInterval={sidebarOpen ? 5000 : 0}
                maxEntries={50}
              />
            )}

            {panelTab === 'Trace' && (
              <DebugTracePanel
                trace={(galaxyResponse?.debug_info?.nlq_diag_trace as string[]) ?? null}
                debugInfo={galaxyResponse?.debug_info ?? null}
              />
            )}

          </div>
        </aside>
      </div>

      {/* Landing Page Overlay (user-triggered) */}
      {showLanding && (
        <div className="fixed inset-0 z-[9999]">
          <LandingPage onStart={handleLandingStart} />
        </div>
      )}

      {/* Product Tour Overlay */}
      <ProductTour
        visible={tourVisible}
        onDismiss={handleTourDismiss}
        onNavigate={handleTourNavigate}
        onFocusSearch={handleTourFocusSearch}
        querySubmitted={tourQuerySubmitted}
        currentView={viewMode}
        onStepEnter={handleTourStepEnter}
      />
    </div>
  )
}

export default App
