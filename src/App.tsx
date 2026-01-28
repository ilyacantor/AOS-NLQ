import { useState } from 'react'
import { GalaxyView, IntentMapResponse } from './components/galaxy'

interface QueryHistoryItem {
  id: string
  query: string
  timestamp: string
  duration: string
  tag: string
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
}

type ViewMode = 'text' | 'galaxy'
type PanelTab = 'History' | 'Debug'

const quickActions = [
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
]

function App() {
  const [query, setQuery] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('galaxy')
  const [panelTab, setPanelTab] = useState<PanelTab>('History')
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [textResponse, setTextResponse] = useState<NLQResponse | null>(null)
  const [galaxyResponse, setGalaxyResponse] = useState<IntentMapResponse | null>(null)
  const [lastQuery, setLastQuery] = useState('')
  const [lastDuration, setLastDuration] = useState('')

  const handleSubmit = async (queryText?: string) => {
    const textToSubmit = queryText ?? query
    if (!textToSubmit.trim()) return

    setIsLoading(true)
    setQuery(textToSubmit)
    setTextResponse(null)
    setGalaxyResponse(null)
    const now = new Date()
    const timestamp = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    const startTime = performance.now()

    try {
      // Fetch from intent-map endpoint for Galaxy view
      const endpoint = viewMode === 'galaxy' ? '/api/v1/intent-map' : '/api/v1/query'
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: textToSubmit,
          reference_date: '2026-01-27'
        })
      })

      const data = await res.json()
      const duration = Math.round(performance.now() - startTime)

      if (viewMode === 'galaxy') {
        setGalaxyResponse(data as IntentMapResponse)
      } else {
        setTextResponse(data as NLQResponse)
      }

      setLastQuery(textToSubmit)
      setLastDuration(`${duration}ms`)

      const newItem: QueryHistoryItem = {
        id: Date.now().toString(),
        query: textToSubmit,
        timestamp: timestamp,
        duration: `${duration}ms`,
        tag: viewMode === 'galaxy'
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

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-cyan-400 text-2xl font-bold">AOS</span>
            <span className="text-slate-300 text-lg">Intent Map</span>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center gap-1 ml-8 bg-slate-900 rounded-lg p-1">
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
          </div>
        </div>

        <div className="text-slate-500 text-sm">
          {lastDuration && <span className="text-slate-400">{lastDuration}</span>}
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Main Content */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Query Input Section - Always at top middle */}
          <div className="flex flex-col items-center pt-6 pb-4 px-8">
            <div className="text-slate-500 text-sm mb-4">
              Using dataset: <span className="text-slate-300">nlq_test</span>{' '}
              <span className="text-slate-600">(reference: 2026-01-27)</span>
            </div>

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

            {/* Quick Action Buttons - Always visible */}
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

          {/* Results Area */}
          <div className="flex-1 overflow-hidden">
            {/* Galaxy View */}
            {viewMode === 'galaxy' && galaxyResponse && (
              <div className="h-full overflow-hidden">
                <GalaxyView data={galaxyResponse} />
              </div>
            )}

            {/* Text View */}
            {viewMode === 'text' && textResponse && (
              <div className="h-full overflow-y-auto p-8">
                <div className="max-w-3xl mx-auto bg-slate-900 border border-slate-700 rounded-xl p-6">
                  {/* Query echo */}
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
                    <>
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
                    </>
                  ) : (
                    /* Error display */
                    <div className="p-4 bg-red-900/20 border border-red-800/50 rounded-lg">
                      <div className="text-red-400 font-medium mb-1">{textResponse.error_code}</div>
                      <div className="text-red-300/80 text-sm">{textResponse.error_message}</div>
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

        {/* Right Sidebar - History Panel */}
        <aside className="w-72 border-l border-slate-800 flex flex-col bg-slate-900/30">
          {/* Panel Tabs */}
          <div className="flex border-b border-slate-800">
            {(['History', 'Debug'] as PanelTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setPanelTab(tab)}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
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
