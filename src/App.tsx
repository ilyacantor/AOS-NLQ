import { useState } from 'react'
import { GalaxyView, IntentMapResponse } from './components/galaxy'
import { Dashboard } from './components/dashboard'
import { RAGLearningPanel, LLMCallCounter } from './components/rag'

interface QueryHistoryItem {
  id: string
  query: string
  timestamp: string
  duration: string
  tag: string
}

interface RelatedMetric {
  metric: string
  display_name: string
  value: number | string | null
  formatted_value: string | null
  period: string | null
  confidence: number
  match_type: string
  rationale: string | null
  domain?: string
}

interface NLQResponse {
  success: boolean
  answer?: string
  value?: number | string
  unit?: string
  confidence: number
  parsed_intent?: string
  resolved_metric?: string
  resolved_period?: string
  error_code?: string
  error_message?: string
  related_metrics?: RelatedMetric[]
}

type ViewMode = 'text' | 'galaxy' | 'dashboard'
type Persona = 'CFO' | 'CRO' | 'COO' | 'CTO' | 'People'
type PanelTab = 'History' | 'Learning' | 'Debug'
type QueryMode = 'static' | 'ai'

const quickActions = [
  // Dashboards
  'CFO dashboard',
  'CRO dashboard',
  'COO dashboard',
  'CTO dashboard',
  '2025 KPIs',
  // CFO
  'whats the margin',
  'are we profitable',
  // CRO
  'how\'s pipeline looking',
  'churn?',
  // COO
  'are we efficient',
  'magic number',
  // CTO
  'platform stable?',
  'how\'s velocity',
  // People
  'who is the CEO',
  'pto days',
  '401k match',
]

// Helper to detect dashboard requests
const isDashboardQuery = (q: string): Persona | null => {
  const lower = q.toLowerCase()
  if (lower.includes('cfo dashboard') || lower.includes('finance dashboard')) return 'CFO'
  if (lower.includes('cro dashboard') || lower.includes('sales dashboard')) return 'CRO'
  if (lower.includes('coo dashboard') || lower.includes('ops dashboard') || lower.includes('operations dashboard')) return 'COO'
  if (lower.includes('cto dashboard') || lower.includes('tech dashboard') || lower.includes('engineering dashboard')) return 'CTO'
  if (lower.includes('people dashboard') || lower.includes('hr dashboard')) return 'People'
  return null
}

function App() {
  const [query, setQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('galaxy')
  const [queryMode, setQueryMode] = useState<QueryMode>('ai')  // Default to AI (Prod mode)
  const [dashboardPersona, setDashboardPersona] = useState<Persona>('CFO')
  const [panelTab, setPanelTab] = useState<PanelTab>('History')
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [textResponse, setTextResponse] = useState<NLQResponse | null>(null)
  const [galaxyResponse, setGalaxyResponse] = useState<IntentMapResponse | null>(null)
  const [lastQuery, setLastQuery] = useState('')
  const [lastDuration, setLastDuration] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const handleSubmit = async (queryText?: string, forceTextView?: boolean) => {
    const textToSubmit = queryText ?? query
    if (!textToSubmit.trim()) return

    // Check for dashboard query first
    const persona = isDashboardQuery(textToSubmit)
    if (persona) {
      setDashboardPersona(persona)
      setViewMode('dashboard')
      setQuery('')
      setLastQuery(textToSubmit)
      // Add to history
      const now = new Date()
      const timestamp = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
      const newItem: QueryHistoryItem = {
        id: Date.now().toString(),
        query: textToSubmit,
        timestamp: timestamp,
        duration: '0ms',
        tag: `${persona} Dashboard`,
      }
      setQueryHistory(prev => [newItem, ...prev])
      return
    }

    setIsLoading(true)
    setQuery(textToSubmit)
    setTextResponse(null)
    setGalaxyResponse(null)
    const now = new Date()
    const timestamp = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    const startTime = performance.now()

    // Determine the effective view mode (text view if forced from dashboard drill-down)
    const effectiveViewMode = forceTextView ? 'text' : viewMode

    try {
      // Fetch from appropriate endpoint based on view mode
      // Galaxy uses intent-map endpoint, Text uses query endpoint
      const endpoint = effectiveViewMode === 'galaxy' ? '/api/v1/intent-map' : '/api/v1/query'
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: textToSubmit,
          reference_date: '2026-01-27',
          mode: queryMode  // Pass static/ai mode to backend
        })
      })

      const data = await res.json()
      const duration = Math.round(performance.now() - startTime)

      if (effectiveViewMode === 'galaxy') {
        setGalaxyResponse(data as IntentMapResponse)
      } else {
        // Text view or drill-down from dashboard
        setTextResponse(data as NLQResponse)
      }

      setLastQuery(textToSubmit)
      setLastDuration(`${duration}ms`)

      const newItem: QueryHistoryItem = {
        id: Date.now().toString(),
        query: textToSubmit,
        timestamp: timestamp,
        duration: `${duration}ms`,
        tag: effectiveViewMode === 'galaxy'
          ? (data as IntentMapResponse).query_type || 'intent-map'
          : (data as NLQResponse).resolved_metric || 'nlq.query',
      }

      setQueryHistory(prev => [newItem, ...prev])
    } catch (error) {
      console.error('Query failed:', error)
      if (viewMode === 'galaxy') {
        // Show error in text mode
        setTextResponse({
          success: false,
          confidence: 0,
          error_code: 'NETWORK_ERROR',
          error_message: 'Failed to connect to backend. Is the server running?'
        })
        setViewMode('text')
      } else {
        setTextResponse({
          success: false,
          confidence: 0,
          error_code: 'NETWORK_ERROR',
          error_message: 'Failed to connect to backend. Is the server running?'
        })
      }
    }

    setQuery('')
    setIsLoading(false)
  }

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

  const hasResponse = galaxyResponse || textResponse

  // No auto-query on mount - user can use quick actions or type a query

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-cyan-400 text-2xl font-bold">NLQ</span>
            <span className="text-slate-300 text-lg font-normal">Natural Language Query</span>
          </div>

          {/* View Mode Toggle */}
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
              Galaxy View
            </button>
            <button
              onClick={() => setViewMode('text')}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                viewMode === 'text'
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Text View
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
          {/* Query Input Section - Hidden in Dashboard view */}
          {viewMode !== 'dashboard' && (
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
              <div className="flex flex-wrap justify-center gap-2 mt-4 max-w-3xl">
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
            {/* Dashboard View */}
            {viewMode === 'dashboard' && (
              <div className="h-full overflow-hidden">
                <Dashboard
                  persona={dashboardPersona}
                  onNLQQuery={(q) => {
                    // Switch to text view for drill-down queries (more reliable than galaxy)
                    setViewMode('text')
                    // Set the query to show loading state immediately
                    setLastQuery(q)
                    // Submit the query with forceTextView=true to ensure text endpoint is used
                    handleSubmit(q, true)
                  }}
                />
              </div>
            )}

            {/* Galaxy View */}
            {viewMode === 'galaxy' && galaxyResponse && (
              <div className="h-full overflow-hidden">
                <GalaxyView data={galaxyResponse} />
              </div>
            )}

            {/* Text View */}
            {viewMode === 'text' && textResponse && (
              <div className="h-full overflow-y-auto p-8">
                <div className="max-w-4xl mx-auto">
                  {/* Query echo header */}
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-slate-400 text-sm">{lastQuery}</span>
                    <button
                      onClick={() => setTextResponse(null)}
                      className="text-slate-500 hover:text-slate-300"
                    >
                      ✕
                    </button>
                  </div>

                  {textResponse.success ? (
                    textResponse.parsed_intent === 'DASHBOARD' ? (
                      /* Dashboard View - with table */
                      <div className="flex gap-6">
                        {/* Main Table */}
                        <div className="flex-1 bg-slate-900 border border-slate-700 rounded-xl overflow-hidden">
                          <div className="p-4 border-b border-slate-700">
                            <h2 className="text-lg font-semibold text-white">
                              {textResponse.answer?.split('\n')[0]?.replace(/\*\*/g, '') || '2025 vs 2024 KPIs'}
                            </h2>
                          </div>
                          <div className="p-4">
                            {(() => {
                              const lines = (textResponse.answer || '').split('\n');
                              const tableLines = lines.filter(l => l.startsWith('|'));
                              if (tableLines.length > 2) {
                                const headers = tableLines[0].split('|').filter(c => c.trim());
                                const rows = tableLines.slice(2);
                                return (
                                  <table className="w-full text-sm">
                                    <thead>
                                      <tr className="border-b border-slate-700">
                                        {headers.map((h, i) => (
                                          <th key={i} className="px-3 py-2 text-left text-slate-400 font-medium">
                                            {h.trim()}
                                          </th>
                                        ))}
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {rows.map((row, rowIdx) => {
                                        const cells = row.split('|').filter(c => c.trim());
                                        const isPersonaRow = cells[0]?.includes('**');
                                        return (
                                          <tr key={rowIdx} className={`border-b border-slate-800 ${isPersonaRow ? 'bg-slate-800/30' : ''}`}>
                                            {cells.map((cell, cellIdx) => {
                                              const content = cell.trim().replace(/\*\*/g, '');
                                              const isChange = cellIdx === cells.length - 1;
                                              const isPositive = content.startsWith('+');
                                              const isNeutral = content === '0.0pp' || content === '0%';
                                              return (
                                                <td key={cellIdx} className={`px-3 py-2 ${
                                                  cellIdx === 0 && isPersonaRow ? 'font-semibold text-white' :
                                                  isChange ? (isPositive ? 'text-emerald-400' : isNeutral ? 'text-slate-400' : 'text-red-400') :
                                                  'text-slate-300'
                                                }`}>
                                                  {content}
                                                </td>
                                              );
                                            })}
                                          </tr>
                                        );
                                      })}
                                    </tbody>
                                  </table>
                                );
                              }
                              return <pre className="text-slate-300 whitespace-pre-wrap">{textResponse.answer}</pre>;
                            })()}
                          </div>
                        </div>

                        {/* Sidebar - Metrics by Persona */}
                        {textResponse.related_metrics && textResponse.related_metrics.length > 0 && (
                          <div className="w-64 flex-shrink-0">
                            <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
                              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
                                Metrics by Domain
                              </h3>
                              {(() => {
                                const domainColors: Record<string, string> = {
                                  finance: '#3B82F6', growth: '#EC4899', ops: '#10B981', product: '#8B5CF6', people: '#F97316'
                                };
                                const domainLabels: Record<string, string> = {
                                  finance: 'CFO', growth: 'CRO', ops: 'COO', product: 'CTO', people: 'People'
                                };
                                const byDomain = textResponse.related_metrics.reduce((acc, m) => {
                                  const d = (m as any).domain || 'finance';
                                  if (!acc[d]) acc[d] = [];
                                  acc[d].push(m);
                                  return acc;
                                }, {} as Record<string, typeof textResponse.related_metrics>);

                                return Object.entries(byDomain).map(([domain, metrics]) => (
                                  <div key={domain} className="mb-4">
                                    <div className="flex items-center gap-2 mb-2">
                                      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: domainColors[domain] }} />
                                      <span className="text-slate-400 text-xs font-medium">{domainLabels[domain] || domain}</span>
                                    </div>
                                    {metrics.map((m, i) => (
                                      <div key={i} className="flex justify-between text-xs py-1 border-b border-slate-800/50">
                                        <span className="text-slate-400">{m.display_name}</span>
                                        <span className="text-slate-200 font-mono">{m.formatted_value}</span>
                                      </div>
                                    ))}
                                  </div>
                                ));
                              })()}
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      /* Standard Text View */
                      <div className="bg-slate-900 border border-slate-700 rounded-xl p-6">
                        {/* Answer */}
                        <div className="text-slate-200 text-lg mb-4 p-4 bg-slate-800/50 rounded-lg">
                          {textResponse.answer}
                        </div>

                        {/* Metadata row */}
                        <div className="flex items-center gap-4 text-sm text-slate-400 mb-4">
                          <span>Definition: <span className="text-cyan-400">{textResponse.resolved_metric}</span></span>
                          <span>Confidence: <span className="text-green-400">{Math.round(textResponse.confidence * 100)}%</span></span>
                          <span>{lastDuration}</span>
                        </div>

                        {/* Value display */}
                        {textResponse.value !== undefined && (
                          <div className="grid grid-cols-3 gap-4 p-4 bg-slate-800/30 rounded-lg">
                            <div>
                              <div className="text-slate-500 text-xs mb-1">Value</div>
                              <div className="text-slate-200 font-mono text-xl">
                                {textResponse.unit === '%'
                                  ? `${Number(textResponse.value).toFixed(1)}%`
                                  : `$${Number(textResponse.value).toFixed(1)}M`}
                              </div>
                            </div>
                            <div>
                              <div className="text-slate-500 text-xs mb-1">Period</div>
                              <div className="text-slate-200">{textResponse.resolved_period}</div>
                            </div>
                            <div>
                              <div className="text-slate-500 text-xs mb-1">Intent</div>
                              <div className="text-slate-200">{textResponse.parsed_intent}</div>
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  ) : (
                    /* Error display */
                    <div className="bg-slate-900 border border-slate-700 rounded-xl p-6">
                      <div className="p-4 bg-red-900/20 border border-red-800/50 rounded-lg">
                        <div className="text-red-400 font-medium mb-1">{textResponse.error_code}</div>
                        <div className="text-red-300/80 text-sm">{textResponse.error_message}</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Empty State */}
            {!hasResponse && (
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

        {/* Right Sidebar - History Panel */}
        <aside className={`${sidebarOpen ? 'w-[283px]' : 'w-0 overflow-hidden'} border-l border-slate-800 flex flex-col bg-slate-900/30 transition-all duration-300`}>
          {/* Panel Tabs */}
          <div className="flex border-b border-slate-800">
            {(['History', 'Learning', 'Debug'] as PanelTab[]).map((tab) => (
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
                        <p className="text-slate-200 text-sm truncate">{item.query}</p>
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
                {textResponse && (
                  <div className="text-xs font-mono">
                    <div className="text-slate-400 mb-2">NLQResponse:</div>
                    <pre className="text-slate-500 whitespace-pre-wrap break-words overflow-x-auto">
                      {JSON.stringify(textResponse, null, 2)}
                    </pre>
                  </div>
                )}
                {!galaxyResponse && !textResponse && (
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
