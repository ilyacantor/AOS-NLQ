interface UserGuideProps {
  onClose: () => void;
}

export function UserGuide({ onClose }: UserGuideProps) {
  return (
    <div className="h-full overflow-auto bg-slate-950 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold text-white">NLQ User Guide</h1>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition-colors"
          >
            Back to App
          </button>
        </div>

        <section className="mb-10">
          <h2 className="text-2xl font-semibold text-cyan-400 mb-4">What is NLQ?</h2>
          <p className="text-slate-300 leading-relaxed">
            NLQ (Natural Language Query) lets you ask business questions in plain English and get instant answers. 
            Instead of navigating complicated reports or writing database queries, just type your question like 
            you're asking a colleague.
          </p>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl font-semibold text-cyan-400 mb-4">Getting Started</h2>
          <div className="bg-slate-900 rounded-lg p-6 mb-4">
            <h3 className="text-lg font-medium text-white mb-3">Asking Your First Question</h3>
            <ol className="list-decimal list-inside text-slate-300 space-y-2">
              <li>Type your question in the search bar at the top of the screen</li>
              <li>Press Enter or click the search button</li>
              <li>View your answer in either Galaxy View or Dashboard View</li>
            </ol>
          </div>

          <h3 className="text-lg font-medium text-white mb-3">Example Questions You Can Ask</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-slate-900 rounded-lg p-4">
              <p className="text-slate-400 text-sm mb-2">Company revenue</p>
              <p className="text-cyan-300">"what's the revenue?" or just "revenue?"</p>
            </div>
            <div className="bg-slate-900 rounded-lg p-4">
              <p className="text-slate-400 text-sm mb-2">Profit margins</p>
              <p className="text-cyan-300">"what's the margin?" or "are we profitable?"</p>
            </div>
            <div className="bg-slate-900 rounded-lg p-4">
              <p className="text-slate-400 text-sm mb-2">Sales pipeline</p>
              <p className="text-cyan-300">"how's pipeline looking?"</p>
            </div>
            <div className="bg-slate-900 rounded-lg p-4">
              <p className="text-slate-400 text-sm mb-2">Customer churn</p>
              <p className="text-cyan-300">"churn?" or "what's our churn rate?"</p>
            </div>
            <div className="bg-slate-900 rounded-lg p-4">
              <p className="text-slate-400 text-sm mb-2">Team information</p>
              <p className="text-cyan-300">"who is the CEO?" or "how many employees?"</p>
            </div>
            <div className="bg-slate-900 rounded-lg p-4">
              <p className="text-slate-400 text-sm mb-2">Key metrics overview</p>
              <p className="text-cyan-300">"2025 results" or "show me the KPIs"</p>
            </div>
          </div>
          <p className="text-slate-400 mt-4 text-sm">
            Tip: You don't need to use formal language. Questions like "margin?" or "churn?" 
            work just as well as complete sentences.
          </p>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl font-semibold text-cyan-400 mb-4">View Modes</h2>
          
          <div className="space-y-6">
            <div className="bg-slate-900 rounded-lg p-6">
              <h3 className="text-lg font-medium text-white mb-3">Galaxy View (Visual Mode)</h3>
              <p className="text-slate-300 mb-3">Galaxy View shows your answer as an interactive visualization:</p>
              <ul className="list-disc list-inside text-slate-300 space-y-2">
                <li><span className="text-white">Center Node:</span> Your main answer appears in the middle</li>
                <li><span className="text-white">Connected Nodes:</span> Related metrics appear around the center</li>
                <li><span className="text-white">Color Coding:</span>
                  <ul className="list-none ml-6 mt-1 space-y-1">
                    <li><span className="text-green-400">Green border</span> = High confidence answer</li>
                    <li><span className="text-yellow-400">Yellow border</span> = Medium confidence</li>
                    <li><span className="text-red-400">Red border</span> = Lower confidence (may need verification)</li>
                  </ul>
                </li>
              </ul>
            </div>

            <div className="bg-slate-900 rounded-lg p-6">
              <h3 className="text-lg font-medium text-white mb-3">Dashboard View</h3>
              <p className="text-slate-300 mb-3">For overview questions, you'll see a full dashboard with:</p>
              <ul className="list-disc list-inside text-slate-300 space-y-2">
                <li>Key performance indicators (KPIs) in card format</li>
                <li>Charts and visualizations</li>
                <li>Trend indicators showing if metrics are up or down</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl font-semibold text-cyan-400 mb-4">Dashboard Features</h2>
          
          <div className="space-y-6">
            <div className="bg-slate-900 rounded-lg p-6">
              <h3 className="text-lg font-medium text-white mb-3">Persona Dashboards</h3>
              <p className="text-slate-300 mb-3">Ask for role-specific views:</p>
              <ul className="list-disc list-inside text-slate-300 space-y-2">
                <li><span className="text-cyan-300">"CFO dashboard"</span> - Financial metrics (Revenue, Margins, Profitability)</li>
                <li><span className="text-cyan-300">"CRO dashboard"</span> - Sales metrics (Pipeline, Bookings, Win Rate)</li>
                <li><span className="text-cyan-300">"COO dashboard"</span> - Operations metrics (Efficiency, Headcount, NPS)</li>
                <li><span className="text-cyan-300">"CTO dashboard"</span> - Technology metrics (Uptime, Velocity, Deployments)</li>
                <li><span className="text-cyan-300">"CHRO dashboard"</span> - People metrics (Headcount, Turnover, Satisfaction)</li>
              </ul>
            </div>

            <div className="bg-slate-900 rounded-lg p-6">
              <h3 className="text-lg font-medium text-white mb-3">Customizing Your Dashboard</h3>
              <p className="text-slate-300 mb-3">Once a dashboard loads, you can:</p>
              <ul className="list-disc list-inside text-slate-300 space-y-2">
                <li><span className="text-white">Move widgets:</span> Click and drag any card to reposition it</li>
                <li><span className="text-white">Resize widgets:</span> Drag the corner of any card to make it larger or smaller</li>
                <li><span className="text-white">Refine the view:</span> Use the "Refine..." box at the top to make changes</li>
              </ul>
            </div>

            <div className="bg-slate-900 rounded-lg p-6">
              <h3 className="text-lg font-medium text-white mb-3">Refining Your Dashboard</h3>
              <p className="text-slate-300 mb-3">The refinement box lets you modify what you see. Try commands like:</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
                <code className="bg-slate-800 px-3 py-2 rounded text-cyan-300 text-sm">"Add a pipeline chart"</code>
                <code className="bg-slate-800 px-3 py-2 rounded text-cyan-300 text-sm">"Make the revenue card bigger"</code>
                <code className="bg-slate-800 px-3 py-2 rounded text-cyan-300 text-sm">"Show this as a bar chart"</code>
                <code className="bg-slate-800 px-3 py-2 rounded text-cyan-300 text-sm">"Remove the churn metric"</code>
              </div>
            </div>

            <div className="bg-slate-900 rounded-lg p-6">
              <h3 className="text-lg font-medium text-white mb-3">Saving Your Work</h3>
              <ul className="list-disc list-inside text-slate-300 space-y-2">
                <li><span className="text-white">Save:</span> Keep your customized layout</li>
                <li><span className="text-white">Template:</span> Save it as a reusable template</li>
                <li><span className="text-white">Load:</span> Open a previously saved dashboard</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl font-semibold text-cyan-400 mb-4">Tips for Best Results</h2>
          <div className="bg-slate-900 rounded-lg p-6">
            <ul className="list-disc list-inside text-slate-300 space-y-3">
              <li>
                <span className="text-white">Be specific when needed:</span> Instead of "sales?" try "Q4 sales by region"
              </li>
              <li>
                <span className="text-white">Use quick actions:</span> Click the buttons below the search bar for instant answers
              </li>
              <li>
                <span className="text-white">Check history:</span> Click the panel on the right to see previous questions
              </li>
            </ul>
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl font-semibold text-cyan-400 mb-4">Understanding Your Answers</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-slate-900 rounded-lg p-4">
              <h3 className="text-lg font-medium text-white mb-2">Confidence Levels</h3>
              <ul className="text-slate-300 space-y-1 text-sm">
                <li><span className="text-green-400">High:</span> Strong match</li>
                <li><span className="text-yellow-400">Medium:</span> Good match</li>
                <li><span className="text-red-400">Low:</span> Best guess</li>
              </ul>
            </div>
            <div className="bg-slate-900 rounded-lg p-4">
              <h3 className="text-lg font-medium text-white mb-2">Time Periods</h3>
              <p className="text-slate-300 text-sm">
                Answers show what period the data covers (Q4 2024, YTD, etc.)
              </p>
            </div>
            <div className="bg-slate-900 rounded-lg p-4">
              <h3 className="text-lg font-medium text-white mb-2">Trend Arrows</h3>
              <ul className="text-slate-300 space-y-1 text-sm">
                <li><span className="text-green-400">↑</span> Improving</li>
                <li><span className="text-red-400">↓</span> Declining</li>
                <li><span className="text-slate-400">→</span> Stable</li>
              </ul>
            </div>
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl font-semibold text-cyan-400 mb-4">Troubleshooting</h2>
          <div className="space-y-4">
            <div className="bg-slate-900 rounded-lg p-4">
              <h3 className="text-white font-medium mb-2">"I'm not getting the expected answer"</h3>
              <p className="text-slate-300 text-sm">
                Try rephrasing with more specific terms. Instead of "money" → "revenue" or "profit"
              </p>
            </div>
            <div className="bg-slate-900 rounded-lg p-4">
              <h3 className="text-white font-medium mb-2">"The dashboard looks different"</h3>
              <p className="text-slate-300 text-sm">
                Layouts can be customized. Click the Reset button to return to defaults.
              </p>
            </div>
            <div className="bg-slate-900 rounded-lg p-4">
              <h3 className="text-white font-medium mb-2">"I want to start fresh"</h3>
              <p className="text-slate-300 text-sm">
                Refresh the page to clear your session and start with a new query.
              </p>
            </div>
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-2xl font-semibold text-cyan-400 mb-4">Keyboard Shortcuts</h2>
          <div className="bg-slate-900 rounded-lg p-6">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="pb-3 text-slate-400">Action</th>
                  <th className="pb-3 text-slate-400">Shortcut</th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                <tr className="border-b border-slate-800">
                  <td className="py-3">Submit question</td>
                  <td className="py-3"><code className="bg-slate-800 px-2 py-1 rounded">Enter</code></td>
                </tr>
                <tr className="border-b border-slate-800">
                  <td className="py-3">Clear search box</td>
                  <td className="py-3"><code className="bg-slate-800 px-2 py-1 rounded">Escape</code></td>
                </tr>
                <tr>
                  <td className="py-3">Toggle side panel</td>
                  <td className="py-3">Click the arrow button</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <div className="text-center py-8 border-t border-slate-800">
          <p className="text-slate-400 italic">
            NLQ - Ask questions in plain English, get answers instantly.
          </p>
          <button
            onClick={onClose}
            className="mt-4 px-6 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 transition-colors"
          >
            Back to App
          </button>
        </div>
      </div>
    </div>
  );
}
