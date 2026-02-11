/**
 * ProductTour — 7-modal onboarding tour for the Business Persona.
 *
 * Uses absolute-positioned custom modals (no Driver.js highlight overlay)
 * with a pulsing laser dot that points at the relevant UI element.
 *
 * Tour flow:
 *  1. Welcome & Orientation  (laser → search bar)
 *  2. Quick-Start Presets     (laser → first preset pill)
 *  3. Galaxy View             (laser → Galaxy tab) — navigates to Galaxy first
 *  4. Dashboard View          (laser → Dashboard tab) — navigates to Dashboard first
 *  5. Refine Your Dashboard   (laser → refine input) — stays on Dashboard
 *  6. What-If Scenario        (laser → What-If button) — stays on Dashboard
 *  7. You're Ready            (laser → search bar)
 */

import { useState, useEffect, useCallback, useRef } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ViewMode = 'galaxy' | 'dashboard' | 'guide'

interface TourStep {
  title: string
  body: string
  primaryCTA: string
  secondaryCTA?: string
  targetSelector: string          // CSS selector for laser dot
  requiredView?: ViewMode         // view the app must show first
  onPrimary?: 'next' | 'tryit' | 'finish' | 'guide'
  onSecondary?: 'next' | 'finish' | 'guide'
}

interface ProductTourProps {
  /** Trigger visibility externally (e.g. from landing page or User Guide) */
  visible: boolean
  /** Dismiss callback */
  onDismiss: () => void
  /** Navigate to a view (galaxy / dashboard / guide) */
  onNavigate: (view: ViewMode) => void
  /** Focus the search bar so the user can type */
  onFocusSearch: () => void
  /** Called when user submits a query during the "Try It" step (resumes tour) */
  querySubmitted: boolean
  /** Current view mode so we know when navigation has completed */
  currentView: ViewMode
}

// ---------------------------------------------------------------------------
// Tour Steps
// ---------------------------------------------------------------------------

const STEPS: TourStep[] = [
  {
    title: 'Welcome to NLQ',
    body: 'This is your new command center for business data. Instead of digging through dashboards or waiting on analysts, just type a question in plain English — like you\'re asking a colleague.\n\nTry something simple: "revenue?", "how\'s pipeline looking?", or even just "hi."',
    primaryCTA: 'Try It — Type a Question',
    secondaryCTA: 'Show Me Around First',
    targetSelector: '#nlq-search-input',
    requiredView: 'galaxy',
    onPrimary: 'tryit',
    onSecondary: 'next',
  },
  {
    title: 'Not Sure What to Ask? Start Here',
    body: 'These preset buttons are common questions your team already asks. Tap any one to instantly generate a result — no typing needed.\n\nEach preset is tailored to a real business scenario: KPI overviews, P&L breakdowns, revenue drivers, pipeline health, and more.',
    primaryCTA: 'Got It — Next',
    targetSelector: '#nlq-quick-actions button:first-child',
    requiredView: 'galaxy',
    onPrimary: 'next',
  },
  {
    title: 'Galaxy View — See How Metrics Connect',
    body: 'When you ask a question, Galaxy View shows your answer as an interactive node map. The central node is your answer. Related metrics orbit around it so you can see the bigger picture at a glance.\n\nThe color of each node tells you how confident the system is: green means high confidence, yellow means moderate, and red means low. Click any node to expand its details in the side panel.',
    primaryCTA: 'Next',
    targetSelector: '#nav-tab-galaxy',
    requiredView: 'galaxy',
    onPrimary: 'next',
  },
  {
    title: 'Dashboard View — Your Executive Command Center',
    body: 'Switch to Dashboard View to see full executive dashboards with KPI cards, trend charts, regional maps, and more — all generated from a single question.\n\nDashboards are built for your role. The system auto-detects whether you\'re asking a finance, sales, ops, or people question and adjusts the layout accordingly. You\'ll see real values, trend arrows, and sparklines at a glance.',
    primaryCTA: 'Next',
    targetSelector: '#nav-tab-dashboard',
    requiredView: 'dashboard',
    onPrimary: 'next',
  },
  {
    title: 'Refine with Words, Not Clicks',
    body: 'Your dashboard isn\'t static. Use the refinement bar to modify it using natural language. Type commands like "add EBITDA card," "filter to AMER," or "show revenue by region" and the dashboard updates instantly.\n\nYou can also try the suggestion pills below the bar for common refinements — no guessing required.',
    primaryCTA: 'Next',
    targetSelector: '#dashboard-refine-input',
    requiredView: 'dashboard',
    onPrimary: 'next',
  },
  {
    title: 'What-If — Model Scenarios in Real Time',
    body: 'The What-If panel lets you test business scenarios without touching a spreadsheet. Adjust sliders for revenue growth, pricing, headcount, and operating expenses to see how changes would ripple across your KPIs.\n\nThe KPI Impact Preview updates live as you move each slider, showing you projected revenue, growth rate, margins, and more. When you\'re ready, apply the scenario to your dashboard or reset and try another.',
    primaryCTA: 'Next',
    targetSelector: '#dashboard-whatif-btn',
    requiredView: 'dashboard',
    onPrimary: 'next',
  },
  {
    title: "You're All Set",
    body: "That's everything you need to get started. Just remember: type any question in plain English, and NLQ handles the rest. No training, no SQL, no waiting.\n\nA few tips to keep in mind: you can ask follow-up questions to dig deeper, switch between Galaxy and Dashboard views anytime, and check the User Guide tab if you ever need a refresher.",
    primaryCTA: 'Start Exploring',
    secondaryCTA: 'Open User Guide',
    targetSelector: '#nlq-search-input',
    requiredView: 'galaxy',
    onPrimary: 'finish',
    onSecondary: 'guide',
  },
]

// ---------------------------------------------------------------------------
// Laser Dot component
// ---------------------------------------------------------------------------

function LaserDot({ targetSelector }: { targetSelector: string }) {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const rafRef = useRef<number>(0)

  useEffect(() => {
    let mounted = true

    const update = () => {
      if (!mounted) return
      const el = document.querySelector(targetSelector)
      if (el) {
        const rect = el.getBoundingClientRect()
        setPos({
          top: rect.top + rect.height / 2,
          left: rect.left + rect.width / 2,
        })
      } else {
        setPos(null)
      }
      rafRef.current = requestAnimationFrame(update)
    }

    // Small delay to let view transitions settle
    const timer = setTimeout(() => {
      update()
    }, 200)

    return () => {
      mounted = false
      clearTimeout(timer)
      cancelAnimationFrame(rafRef.current)
    }
  }, [targetSelector])

  if (!pos) return null

  return (
    <div
      className="fixed z-[10001] pointer-events-none"
      style={{ top: pos.top - 8, left: pos.left - 8 }}
    >
      {/* Outer glow ring */}
      <div
        className="absolute inset-0 w-4 h-4 rounded-full"
        style={{
          background: 'rgba(11, 202, 217, 0.3)',
          animation: 'laser-pulse 2s ease-in-out infinite',
        }}
      />
      {/* Inner dot */}
      <div
        className="w-4 h-4 rounded-full"
        style={{ background: '#0bcad9', boxShadow: '0 0 12px 4px rgba(11,202,217,0.5)' }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step Indicator Dots
// ---------------------------------------------------------------------------

function StepDots({ total, current }: { total: number; current: number }) {
  return (
    <div className="flex items-center gap-1.5 mt-5">
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={`w-2 h-2 rounded-full transition-colors ${
            i === current ? 'bg-cyan-400' : 'bg-slate-600'
          }`}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Modal Card
// ---------------------------------------------------------------------------

function TourModal({
  step,
  stepIndex,
  totalSteps,
  onPrimary,
  onSecondary,
  onSkip,
}: {
  step: TourStep
  stepIndex: number
  totalSteps: number
  onPrimary: () => void
  onSecondary?: () => void
  onSkip: () => void
}) {
  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center px-4">
      {/* Overlay */}
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(2, 6, 23, 0.85)' }}
        onClick={onSkip}
      />

      {/* Modal Card */}
      <div
        className="relative bg-slate-800/95 border border-cyan-500/30 rounded-xl shadow-2xl max-w-[420px] w-full p-6"
        style={{ fontFamily: "'Quicksand', sans-serif" }}
      >
        {/* Close button */}
        <button
          onClick={onSkip}
          className="absolute top-3 right-3 text-slate-500 hover:text-slate-300 transition-colors"
          aria-label="Close tour"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {/* Title */}
        <h2 className="text-xl font-semibold text-white mb-3 pr-6">{step.title}</h2>

        {/* Body — render newlines as paragraph breaks */}
        <div className="text-sm text-slate-300 leading-relaxed space-y-3">
          {step.body.split('\n\n').map((para, i) => (
            <p key={i}>{para}</p>
          ))}
        </div>

        {/* CTA Buttons */}
        <div className="flex items-center gap-3 mt-5">
          <button
            onClick={onPrimary}
            className="px-5 py-2 rounded-lg text-sm font-semibold transition-colors"
            style={{ background: '#0bcad9', color: '#020617' }}
          >
            {step.primaryCTA}
          </button>
          {step.secondaryCTA && onSecondary && (
            <button
              onClick={onSecondary}
              className="px-5 py-2 rounded-lg text-sm font-semibold border transition-colors"
              style={{ borderColor: '#0bcad9', color: '#0bcad9' }}
            >
              {step.secondaryCTA}
            </button>
          )}
        </div>

        {/* Step indicator + Skip */}
        <div className="flex items-center justify-between">
          <StepDots total={totalSteps} current={stepIndex} />
          <button
            onClick={onSkip}
            className="text-xs text-slate-500 hover:text-slate-400 transition-colors mt-5"
          >
            Skip Tour
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main ProductTour
// ---------------------------------------------------------------------------

export function ProductTour({
  visible,
  onDismiss,
  onNavigate,
  onFocusSearch,
  querySubmitted,
  currentView,
}: ProductTourProps) {
  const [stepIndex, setStepIndex] = useState(0)
  // "tryit" pauses the modals; user's next query submission resumes
  const [paused, setPaused] = useState(false)
  // Track whether we're waiting for a view navigation to complete
  const [pendingView, setPendingView] = useState<ViewMode | null>(null)

  const step = STEPS[stepIndex]

  // Reset when tour becomes visible
  useEffect(() => {
    if (visible) {
      setStepIndex(0)
      setPaused(false)
      setPendingView(null)
    }
  }, [visible])

  // Resume after user submits a query during "Try It"
  useEffect(() => {
    if (paused && querySubmitted) {
      setPaused(false)
      setStepIndex(1) // move to step 2 (Quick-Start Presets)
    }
  }, [paused, querySubmitted])

  // Navigate to the required view before showing the step
  useEffect(() => {
    if (!visible || paused) return

    const requiredView = step?.requiredView
    if (requiredView && currentView !== requiredView) {
      setPendingView(requiredView)
      onNavigate(requiredView)
    } else {
      setPendingView(null)
    }
  }, [visible, paused, stepIndex, currentView, step?.requiredView, onNavigate])

  // When the current view matches pendingView, clear the wait
  useEffect(() => {
    if (pendingView && currentView === pendingView) {
      setPendingView(null)
    }
  }, [currentView, pendingView])

  const advance = useCallback(() => {
    if (stepIndex < STEPS.length - 1) {
      setStepIndex(s => s + 1)
    } else {
      onDismiss()
    }
  }, [stepIndex, onDismiss])

  const handlePrimary = useCallback(() => {
    const action = step.onPrimary || 'next'
    switch (action) {
      case 'tryit':
        setPaused(true)
        onFocusSearch()
        break
      case 'next':
        advance()
        break
      case 'finish':
        onDismiss()
        onFocusSearch()
        break
      case 'guide':
        onDismiss()
        onNavigate('guide')
        break
    }
  }, [step, advance, onDismiss, onFocusSearch, onNavigate])

  const handleSecondary = useCallback(() => {
    const action = step.onSecondary || 'next'
    switch (action) {
      case 'next':
        advance()
        break
      case 'finish':
        onDismiss()
        onFocusSearch()
        break
      case 'guide':
        onDismiss()
        onNavigate('guide')
        break
    }
  }, [step, advance, onDismiss, onFocusSearch, onNavigate])

  if (!visible || paused) return null
  // Wait for view to switch before showing the modal
  if (pendingView) return null

  return (
    <>
      <LaserDot targetSelector={step.targetSelector} />
      <TourModal
        step={step}
        stepIndex={stepIndex}
        totalSteps={STEPS.length}
        onPrimary={handlePrimary}
        onSecondary={step.secondaryCTA ? handleSecondary : undefined}
        onSkip={onDismiss}
      />
    </>
  )
}
