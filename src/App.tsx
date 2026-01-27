import { useState } from 'react'

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

type TabType = 'Ask' | 'Graph' | 'Dashboard'
type PanelTab = 'History' | 'Debug'

const quickActions = [
  'What was revenue last year?',
  'What was revenue in 2024?',
  'What was net income in 2025?',
  'What was gross margin in 2024?',
  'What was COGS last year?',
  'What was operating profit in 2025?',
  'What was cash last quarter?',
  'What was AR in Q4 2025?',
]

function App() {
  const [query, setQuery] = useState('')
  const [activeTab, setActiveTab] = useState<TabType>('Ask')
  const [panelTab, setPanelTab] = useState<PanelTab>('History')
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [response, setResponse] = useState<NLQResponse | null>(null)
  const [lastQuery, setLastQuery] = useState('')
  const [lastDuration, setLastDuration] = useState('')

  const handleSubmit = async (queryText?: string) => {
    const textToSubmit = queryText ?? query
    if (!textToSubmit.trim()) return

    setIsLoading(true)
    setQuery(textToSubmit)
    setResponse(null)
    const now = new Date()
    const timestamp = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    const startTime = performance.now()

    try {
      const res = await fetch('/api/v1/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: textToSubmit,
          reference_date: '2026-01-27'
        })
      })

      const data: NLQResponse = await res.json()
      const duration = Math.round(performance.now() - startTime)

      setResponse(data)
      setLastQuery(textToSubmit)
      setLastDuration(`${duration}ms`)

      const newItem: QueryHistoryItem = {
        id: Date.now().toString(),
        query: textToSubmit,
        timestamp: timestamp,
        duration: `${duration}ms`,
        tag: data.resolved_metric || 'nlq.query',
      }

      setQueryHistory(prev => [newItem, ...prev])
    } catch (error) {
      console.error('Query failed:', error)
      setResponse({
        success: false,
        confidence: 0,
        error_code: 'NETWORK_ERROR',
        error_message: 'Failed to connect to backend. Is the server running?'
      })
    }

    setQuery('')
    setIsLoading(false)
  }

  const handleQuickAction = (action: string) => {
    // Immediately submit the quick action query
    handleSubmit(action)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header */}
      <header className="flex items-center gap-3 px-6 py-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <span className="text-cyan-400 text-2xl font-bold">DCL</span>
          <span className="text-slate-300 text-lg">Data Connectivity Layer</span>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1 ml-8">
          {(['Ask', 'Graph', 'Dashboard'] as TabType[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </header>

      {/* Main Content Area */}
      <div className="flex flex-1">
        {/* Center Content */}
        <main className="flex-1 flex flex-col items-center pt-12 px-8">
          {/* Dataset indicator */}
          <div className="text-slate-500 text-sm mb-6">
            Using dataset: <span className="text-slate-300">nlq_test</span>{' '}
            <span className="text-slate-600">(env)</span>
          </div>

          {/* Query Input */}
          <div className="w-full max-w-2xl">
            <div className="relative">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question..."
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
          <div className="flex flex-wrap justify-center gap-3 mt-8 max-w-3xl">
            {quickActions.map((action) => (
              <button
                key={action}
                onClick={() => handleQuickAction(action)}
                className="px-4 py-2 bg-slate-800/80 border border-slate-700 rounded-full text-slate-300 text-sm hover:bg-slate-700 hover:border-slate-600 transition-colors"
              >
                {action}
              </button>
            ))}
          </div>

          {/* Results Display */}
          {response && (
            <div className="w-full max-w-3xl mt-8 bg-slate-900 border border-slate-700 rounded-xl p-6">
              {/* Query echo */}
              <div className="flex items-center justify-between mb-4">
                <span className="text-slate-400 text-sm">{lastQuery}</span>
                <button
                  onClick={() => setResponse(null)}
                  className="text-slate-500 hover:text-slate-300"
                >
                  ✕
                </button>
              </div>

              {response.success ? (
                <>
                  {/* Answer */}
                  <div className="text-slate-200 text-lg mb-4 p-4 bg-slate-800/50 rounded-lg">
                    {response.answer}
                  </div>

                  {/* Metadata row */}
                  <div className="flex items-center gap-4 text-sm text-slate-400 mb-4">
                    <span>Definition: <span className="text-cyan-400">{response.resolved_metric}</span></span>
                    <span>Confidence: <span className="text-green-400">{Math.round(response.confidence * 100)}%</span></span>
                    <span>{lastDuration}</span>
                  </div>

                  {/* Value display */}
                  {response.value !== undefined && (
                    <div className="grid grid-cols-3 gap-4 p-4 bg-slate-800/30 rounded-lg">
                      <div>
                        <div className="text-slate-500 text-xs mb-1">Value</div>
                        <div className="text-slate-200 font-mono text-xl">
                          {response.unit === '%' ? `${response.value}%` : `$${response.value}M`}
                        </div>
                      </div>
                      <div>
                        <div className="text-slate-500 text-xs mb-1">Period</div>
                        <div className="text-slate-200">{response.resolved_period}</div>
                      </div>
                      <div>
                        <div className="text-slate-500 text-xs mb-1">Intent</div>
                        <div className="text-slate-200">{response.parsed_intent}</div>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                /* Error display */
                <div className="p-4 bg-red-900/20 border border-red-800/50 rounded-lg">
                  <div className="text-red-400 font-medium mb-1">{response.error_code}</div>
                  <div className="text-red-300/80 text-sm">{response.error_message}</div>
                </div>
              )}
            </div>
          )}
        </main>

        {/* Right Sidebar - History Panel */}
        <aside className="w-80 border-l border-slate-800 flex flex-col">
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
              <div className="p-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-slate-300 font-medium">History</h3>
                  <button className="text-slate-500 text-sm hover:text-slate-300">
                    Refresh
                  </button>
                </div>

                <div className="space-y-1">
                  {queryHistory.map((item) => (
                    <div
                      key={item.id}
                      className="p-3 rounded-lg hover:bg-slate-800/50 cursor-pointer transition-colors"
                    >
                      <p className="text-slate-200 text-sm truncate">{item.query}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-slate-500 text-xs">{item.timestamp}</span>
                        <span className="text-slate-600 text-xs">{item.duration}</span>
                        <span className="text-cyan-400/70 text-xs">{item.tag}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {panelTab === 'Debug' && (
              <div className="p-4">
                <div className="text-slate-500 text-sm">
                  Debug information will appear here
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}

export default App
