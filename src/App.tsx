import { useState, useEffect, useCallback } from 'react'
import { GalaxyView, IntentMapResponse } from './components/galaxy'
import { Dashboard } from './components/dashboard'
import { RAGLearningPanel, LLMCallCounter, useSessionId } from './components/rag'
import { InsufficientDataPanel } from './components/rag/InsufficientDataPanel'
import { DashboardRenderer, DashboardSchema } from './components/generated-dashboard'

interface QueryHistoryItem {
  id: string
  query: string
  timestamp: string
  duration: string
  tag: string
  count: number  // For aggregation
}

type ViewMode = 'galaxy' | 'dashboard'
type Persona = 'CFO' | 'CRO' | 'COO' | 'CTO' | 'CHRO'
type PanelTab = 'History' | 'Learning' | 'Data Gaps' | 'Debug'
type QueryMode = 'static' | 'ai'
type DashboardMode = 'persona' | 'builder'

const personaOptions: { label: string; value: Persona }[] = [
  { label: 'CFO', value: 'CFO' },
  { label: 'CRO', value: 'CRO' },
  { label: 'COO', value: 'COO' },
  { label: 'CTO', value: 'CTO' },
  { label: 'CHRO', value: 'CHRO' },
]

const quickActions = [
  '2025 KPIs',
  'whats the margin',
  'are we profitable',
  'how\'s pipeline looking',
  'churn?',
  'are we efficient',
  'magic number',
  'platform stable?',
  'how\'s velocity',
  'who is the CEO',
  'pto days',
  '401k match',
]

/**
 * Aggregate duplicate queries in history, keeping the most recent and adding count
 */
function aggregateHistory(items: QueryHistoryItem[]): QueryHistoryItem[] {
  const queryMap = new Map<string, QueryHistoryItem>()

  // Process in order (newest first), aggregate duplicates
  for (const item of items) {
    const normalizedQuery = item.query.toLowerCase().trim()
    const existing = queryMap.get(normalizedQuery)

    if (existing) {
      // Update count on the existing (most recent) entry
      existing.count += 1
    } else {
      // First occurrence - keep it
      queryMap.set(normalizedQuery, { ...item, count: 1 })
    }
  }

  return Array.from(queryMap.values())
}

function App() {
  const [query, setQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('galaxy')
  const [queryMode, setQueryMode] = useState<QueryMode>('ai')
  const [dashboardPersona, setDashboardPersona] = useState<Persona>('CFO')
  const [dashboardMode, setDashboardMode] = useState<DashboardMode>('persona')
  const [panelTab, setPanelTab] = useState<PanelTab>('History')
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [galaxyResponse, setGalaxyResponse] = useState<IntentMapResponse | null>(null)
  const [lastQuery, setLastQuery] = useState('')
  const [lastDuration, setLastDuration] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [generatedDashboard, setGeneratedDashboard] = useState<DashboardSchema | null>(null)
  const [dashboardWidgetData, setDashboardWidgetData] = useState<Record<string, any>>({})
  const [hasLoadedDefault, setHasLoadedDefault] = useState(false)
  const sessionId = useSessionId()

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

  // Auto-query "2025 results" for Galaxy view on first load
  useEffect(() => {
    if (!hasLoadedDefault && viewMode === 'galaxy') {
      setHasLoadedDefault(true)
      handleSubmit('2025 results')
    }
  }, [hasLoadedDefault, viewMode])

  const handleSubmit = useCallback(async (queryText?: string) => {
    const textToSubmit = queryText ?? query
    if (!textToSubmit.trim()) return

    setIsLoading(true)
    setQuery('')
    setGalaxyResponse(null)
    const now = new Date()
    const timestamp = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    const startTime = performance.now()

    try {
      // Always use intent-map endpoint for Galaxy view
      const res = await fetch('/api/v1/intent-map', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: textToSubmit,
          reference_date: '2026-01-27',
          mode: queryMode,
          session_id: sessionId
        })
      })

      const data = await res.json()
      const duration = Math.round(performance.now() - startTime)

      setGalaxyResponse(data as IntentMapResponse)
      setLastQuery(textToSubmit)
      setLastDuration(`${duration}ms`)

      const newItem: QueryHistoryItem = {
        id: Date.now().toString(),
        query: textToSubmit,
        timestamp: timestamp,
        duration: `${duration}ms`,
        tag: (data as IntentMapResponse).query_type || 'intent-map',
        count: 1,
      }

      setQueryHistory(prev => aggregateHistory([newItem, ...prev]))
    } catch (error) {
      console.error('Query failed:', error)
      // Show error in galaxy response
      setGalaxyResponse({
        query: textToSubmit,
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
  }, [query, queryMode, sessionId])

  const handleQuickAction = (action: string) => {
    handleSubmit(action)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleHistoryClick = (historyQuery: string) => {
    handleSubmit(historyQuery)
  }

  // Handle drill-down from dashboard tiles - open in Galaxy view
  const handleDashboardDrillDown = (drillQuery: string) => {
    setViewMode('galaxy')
    setLastQuery(drillQuery)
    handleSubmit(drillQuery)
  }

  // Handle generated dashboard from builder refinement
  const handleDashboardRefinement = (newSchema: DashboardSchema) => {
    setGeneratedDashboard(newSchema)
    setDashboardWidgetData({})
    setDashboardMode('builder')
  }

  const hasGalaxyResponse = galaxyResponse !== null

  return (
    <div className="h-screen bg-slate-950 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-cyan-400 text-2xl font-bold">NLQ</span>
            <span className="text-slate-300 text-lg font-normal">Natural Language Query</span>
          </div>

          {/* View Mode Toggle - Only Galaxy and Dashboard */}
          <div className="flex items-center gap-2 ml-8">
            <span className="text-slate-500 text-sm">View:</span>
            <div className="flex items-center gap-1 bg-slate-900 rounded-lg p-1">
              <button
                onClick={() => setViewMode('galaxy')}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  viewMode === 'galaxy'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Galaxy
              </button>
              <button
                onClick={() => setViewMode('dashboard')}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  viewMode === 'dashboard'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Dashboard
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
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  queryMode === 'static'
                    ? 'bg-amber-600 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Static
              </button>
              <button
                onClick={() => setQueryMode('ai')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
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
      </header>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Main Content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Query Input Section - Only shown in Galaxy view */}
          {viewMode === 'galaxy' && (
            <div className="flex flex-col items-center pt-6 pb-4 px-8">
              {/* Query Input */}
              <div className="w-full max-w-2xl">
                <div className="relative">
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask any question, use a preset from below, or just say hi"
                    className="w-full px-5 py-4 bg-slate-900 border border-slate-700 rounded-xl text-slate-200 text-lg placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500"
                  />
                  {isLoading && (
                    <div className="absolute right-4 top-1/2 -translate-y-1/2">
                      <svg className="w-5 h-5 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                    </div>
                  )}
                </div>
              </div>

              {/* Quick Action Buttons */}
              <div className="flex flex-wrap justify-center items-center gap-2 mt-4 max-w-3xl">
                {quickActions.map((action) => (
                  <button
                    key={action}
                    onClick={() => handleQuickAction(action)}
                    className="px-3 py-1.5 bg-slate-800/80 border border-slate-700 rounded-full text-slate-300 text-xs hover:bg-slate-700 hover:border-slate-600 transition-colors"
                  >
                    {action}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Results Area */}
          <div className="flex-1 overflow-hidden">
            {/* Dashboard View - Unified with persona selector and builder */}
            {viewMode === 'dashboard' && (
              <div className="h-full overflow-hidden flex flex-col">
                {/* Dashboard Header with Controls */}
                <div className="flex-shrink-0 px-6 py-3 border-b border-slate-800 bg-slate-900/50">
                  <div className="flex items-center justify-between">
                    {/* Left: Persona Selector & Mode Toggle */}
                    <div className="flex items-center gap-4">
                      {/* Persona Selector */}
                      <div className="flex items-center gap-2">
                        <span className="text-slate-500 text-xs">Persona:</span>
                        <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-0.5">
                          {personaOptions.map((option) => (
                            <button
                              key={option.value}
                              onClick={() => {
                                setDashboardPersona(option.value)
                                setDashboardMode('persona')
                              }}
                              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                                dashboardPersona === option.value && dashboardMode === 'persona'
                                  ? 'bg-cyan-600 text-white'
                                  : 'text-slate-400 hover:text-slate-200'
                              }`}
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Builder Mode Toggle */}
                      {generatedDashboard && (
                        <button
                          onClick={() => setDashboardMode(dashboardMode === 'builder' ? 'persona' : 'builder')}
                          className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                            dashboardMode === 'builder'
                              ? 'bg-purple-600 text-white'
                              : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          {dashboardMode === 'builder' ? '← Back to Persona' : 'Generated Dashboard'}
                        </button>
                      )}
                    </div>

                    {/* Right: Help Text */}
                    <div className="text-slate-500 text-xs">
                      Click any tile to drill down in Galaxy view
                    </div>
                  </div>
                </div>

                {/* Dashboard Content */}
                <div className="flex-1 overflow-hidden">
                  {dashboardMode === 'persona' ? (
                    <Dashboard
                      persona={dashboardPersona}
                      onNLQQuery={handleDashboardDrillDown}
                    />
                  ) : (
                    <DashboardRenderer
                      initialSchema={generatedDashboard || undefined}
                      initialWidgetData={dashboardWidgetData}
                      onDrillDown={handleDashboardDrillDown}
                      onRefinement={handleDashboardRefinement}
                      showRefinementInput={true}
                    />
                  )}
                </div>
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
          </div>
        </main>

        {/* Hamburger Toggle Button */}
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-10 p-2 bg-slate-800 border border-slate-700 rounded-l-lg hover:bg-slate-700 transition-colors"
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

        {/* Right Sidebar */}
        <aside className={`${sidebarOpen ? 'w-[283px]' : 'w-0 overflow-hidden'} border-l border-slate-800 flex flex-col bg-slate-900/30 transition-all duration-300`}>
          {/* Panel Tabs */}
          <div className="flex border-b border-slate-800">
            {(['History', 'Learning', 'Data Gaps', 'Debug'] as PanelTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setPanelTab(tab)}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
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
                        onClick={() => handleHistoryClick(item.query)}
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

            {panelTab === 'Debug' && (
              <div className="p-3">
                {galaxyResponse && (
                  <div className="text-xs font-mono">
                    <div className="text-slate-400 mb-2">IntentMapResponse:</div>
                    <pre className="text-slate-500 whitespace-pre-wrap break-words overflow-x-auto">
                      {JSON.stringify(galaxyResponse, null, 2)}
                    </pre>
                  </div>
                )}
                {!galaxyResponse && (
                  <div className="text-slate-500 text-sm text-center py-8">
                    Run a query to see debug data
                  </div>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}

export default App
