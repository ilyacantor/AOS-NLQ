/**
 * LandingPage — Persona selection screen shown before the main NLQ app.
 *
 * Two choices: Business or Technology persona.
 * After selecting and clicking "Run Simulation", the tour starts.
 */

interface LandingPageProps {
  onStart: (persona: 'business' | 'technology') => void
}

export function LandingPage({ onStart }: LandingPageProps) {
  return (
    <div
      className="h-screen bg-slate-950 flex items-center justify-center px-4"
      style={{ fontFamily: "'Quicksand', sans-serif" }}
    >
      <div className="max-w-lg w-full text-center">
        {/* Logo / Title */}
        <h1 className="text-4xl font-bold text-white mb-2">
          <span className="text-cyan-400">NLQ</span>
        </h1>
        <p className="text-slate-400 text-lg mb-10">Natural Language Query</p>

        {/* Persona Cards */}
        <p className="text-slate-300 text-sm mb-5">Select your persona to get started</p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
          {/* Business Persona */}
          <button
            onClick={() => onStart('business')}
            className="group flex-1 bg-slate-800/80 border border-slate-700 hover:border-cyan-500/50 rounded-xl p-6 text-left transition-all hover:shadow-lg hover:shadow-cyan-900/20 cursor-pointer"
          >
            <div className="text-3xl mb-3">📊</div>
            <h2 className="text-lg font-semibold text-white group-hover:text-cyan-300 transition-colors">
              Business
            </h2>
            <p className="text-slate-400 text-sm mt-1">
              CFO, CRO, COO — Revenue, pipeline, margins, and executive dashboards
            </p>
          </button>

          {/* Technology Persona */}
          <button
            onClick={() => onStart('technology')}
            className="group flex-1 bg-slate-800/80 border border-slate-700 hover:border-cyan-500/50 rounded-xl p-6 text-left transition-all hover:shadow-lg hover:shadow-cyan-900/20 cursor-pointer opacity-50 pointer-events-none"
          >
            <div className="text-3xl mb-3">⚙️</div>
            <h2 className="text-lg font-semibold text-white group-hover:text-cyan-300 transition-colors">
              Technology
            </h2>
            <p className="text-slate-400 text-sm mt-1">
              CTO, Engineering — Uptime, velocity, deployments, and infra health
            </p>
            <span className="inline-block mt-2 text-xs text-slate-500 bg-slate-700/50 px-2 py-0.5 rounded">
              Coming Soon
            </span>
          </button>
        </div>
      </div>
    </div>
  )
}
