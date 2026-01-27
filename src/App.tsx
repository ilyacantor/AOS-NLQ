import { useState } from 'react'

interface QueryHistoryItem {
  id: string
  query: string
  timestamp: string
  duration: string
  tag: string
}

type TabType = 'Ask' | 'Graph' | 'Dashboard'
type PanelTab = 'History' | 'Debug'

const quickActions = [
  'Top 5 customers',
  'Top 10 customers',
  'Sales pipeline',
  'Current ARR',
  'Burn rate',
  'Idle resources',
  'Unallocated spend',
  'SLO status',
  'MTTR metrics',
]

function App() {
  const [query, setQuery] = useState('')
  const [activeTab, setActiveTab] = useState<TabType>('Ask')
  const [panelTab, setPanelTab] = useState<PanelTab>('History')
  const [queryHistory, setQueryHistory] = useState<QueryHistoryItem[]>([
    { id: '1', query: '"Top 3 customers in Q4?"', timestamp: '05:11 AM', duration: '22ms', tag: 'crm.top_customers' },
    { id: '2', query: '"Top 3 customers in Q4?"', timestamp: '04:49 AM', duration: '8ms', tag: 'crm.top_customers' },
    { id: '3', query: '"What\'s our revenue this month?"', timestamp: '04:47 AM', duration: '135ms', tag: 'finops.total_revenue' },
    { id: '4', query: 'What was the revenue for last year?', timestamp: '04:21 AM', duration: '15ms', tag: 'finops.total_revenue' },
    { id: '5', query: 'what are our total sales', timestamp: '04:20 AM', duration: '27ms', tag: 'finops.total_revenue' },
  ])
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (queryText?: string) => {
    const textToSubmit = queryText ?? query
    if (!textToSubmit.trim()) return

    setIsLoading(true)
    setQuery(textToSubmit)  // Show the query in the input
    const now = new Date()
    const timestamp = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })

    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 500))

    const newItem: QueryHistoryItem = {
      id: Date.now().toString(),
      query: textToSubmit,
      timestamp: timestamp,
      duration: `${Math.floor(Math.random() * 100) + 10}ms`,
      tag: 'nlq.query',
    }

    setQueryHistory(prev => [newItem, ...prev])
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
