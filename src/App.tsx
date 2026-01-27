import { useState } from 'react'

interface QueryResult {
  query: string
  status: 'pending' | 'success' | 'error'
  message?: string
  data?: Record<string, unknown>[]
}

interface QueryHistoryItem {
  query: string
  timestamp: string
  status: 'pending' | 'success' | 'error'
}

function App() {
  const [query, setQuery] = useState('')
  const [dclEndpoint, setDclEndpoint] = useState('')
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([])
  const [currentResult, setCurrentResult] = useState<QueryResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async () => {
    if (!query.trim()) return

    setIsLoading(true)
    const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19)
    
    setQueryHistory(prev => [...prev, { query, timestamp, status: 'pending' }])

    await new Promise(resolve => setTimeout(resolve, 500))
    
    setCurrentResult({
      query,
      status: 'pending',
      message: 'Awaiting DCLv2 connection and test data'
    })
    
    setIsLoading(false)
  }

  const handleClear = () => {
    setCurrentResult(null)
    setQuery('')
  }

  return (
    <div className="min-h-screen bg-slate-950 flex">
      {/* Sidebar */}
      <aside className="w-72 bg-slate-900 border-r border-slate-700 flex flex-col">
        <div className="p-6 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">
            DCL Connection
          </h2>
          <input
            type="text"
            value={dclEndpoint}
            onChange={(e) => setDclEndpoint(e.target.value)}
            placeholder="https://api.dcl.example.com/v2"
            className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-slate-200 text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500"
          />
          <div className="mt-3 flex items-center gap-2">
            {dclEndpoint ? (
              <>
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                <span className="text-sm text-slate-400">DCL Ready</span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-slate-500" />
                <span className="text-sm text-slate-500">No endpoint configured</span>
              </>
            )}
          </div>
        </div>

        <div className="flex-1 p-6 overflow-y-auto">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">
            Query History
          </h2>
          {queryHistory.length > 0 ? (
            <div className="space-y-2">
              {[...queryHistory].reverse().slice(0, 10).map((item, i) => (
                <div
                  key={i}
                  className="p-3 bg-slate-800/50 border border-slate-700 rounded-lg hover:border-cyan-500/50 transition-colors cursor-pointer"
                >
                  <p className="text-cyan-400 text-sm truncate">{item.query}</p>
                  <p className="text-slate-500 text-xs mt-1">{item.timestamp}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500 text-sm">No queries yet</p>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col">
        {/* Header */}
        <header className="p-8 border-b border-slate-800">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
            aos-nlq
          </h1>
          <p className="text-slate-400 mt-2">
            Natural Language Query Interface for Financial Data | Powered by DCLv2
          </p>
        </header>

        {/* Query Area */}
        <div className="p-8">
          <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-6">
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask a question about your financial data...

Examples:
• Show me revenue trends for Q4 2024
• What are the top performing assets?
• Compare expense categories year over year"
              className="w-full h-32 px-4 py-3 bg-slate-900/50 border border-slate-600 rounded-lg text-slate-200 placeholder-slate-500 resize-none focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500"
            />
            <div className="mt-4 flex gap-3">
              <button
                onClick={handleSubmit}
                disabled={isLoading || !query.trim()}
                className="px-6 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-600 text-white font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Processing...' : 'Query'}
              </button>
              <button
                onClick={handleClear}
                className="px-6 py-2.5 bg-slate-700 text-slate-300 font-medium rounded-lg hover:bg-slate-600 transition-colors"
              >
                Clear
              </button>

              {/* Status Badge */}
              <div className="ml-auto flex items-center gap-3">
                {dclEndpoint ? (
                  <span className="px-3 py-1 bg-green-500/20 text-green-400 text-sm font-medium rounded-full">
                    DCL Connected
                  </span>
                ) : (
                  <span className="px-3 py-1 bg-yellow-500/20 text-yellow-400 text-sm font-medium rounded-full">
                    Awaiting Config
                  </span>
                )}
                <span className="text-slate-500 text-sm">
                  Queries: {queryHistory.length}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Results Area */}
        <div className="flex-1 px-8 pb-8">
          <h2 className="text-lg font-semibold text-slate-300 mb-4">Results</h2>
          <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-6 min-h-[200px]">
            {currentResult ? (
              <div>
                {currentResult.status === 'pending' && (
                  <div className="flex items-center gap-2 text-yellow-400">
                    <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span>{currentResult.message}</span>
                  </div>
                )}
                {currentResult.status === 'success' && currentResult.data && (
                  <div className="overflow-x-auto">
                    <pre className="text-slate-300 text-sm">
                      {JSON.stringify(currentResult.data, null, 2)}
                    </pre>
                  </div>
                )}
                {currentResult.status === 'error' && (
                  <div className="flex items-center gap-2 text-red-400">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>{currentResult.message}</span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-slate-500 text-center">
                Enter a query above to get started
              </p>
            )}
          </div>
        </div>

        {/* Footer */}
        <footer className="p-4 border-t border-slate-800 text-center">
          <p className="text-slate-500 text-sm">
            aos-nlq | Natural Language Query Engine | Dev Mode
          </p>
        </footer>
      </main>
    </div>
  )
}

export default App
