/**
 * ProductTour — 6-modal onboarding tour for the Business Persona.
 *
 * Uses absolute-positioned custom modals (no overlay)
 * with a pulsing laser dot that points at the relevant UI element.
 *
 * Tour flow:
 *  1. Welcome & Orientation  (laser → search bar)
 *  2. Galaxy View             (laser → Galaxy tab)
 *  3. Dashboard View          (laser → Dashboard tab) — navigates to Dashboard
 *  4. Refine Your Dashboard   (laser → refine input) — stays on Dashboard
 *  5. What-If Scenario        (laser → What-If button) — stays on Dashboard
 *  6. Tour Complete           (laser → search bar)
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
  /** Fires when a step becomes active — stepIndex is 0-based */
  onStepEnter?: (stepIndex: number) => void
}

// ---------------------------------------------------------------------------
// Tour Steps
// ---------------------------------------------------------------------------

const STEPS: TourStep[] = [
  {
    title: 'Welcome to NLQ',
    body: 'This is your command center for information and action. Type a question in plain English or hit a preset.\n\nMention of "Dashboard" or "dash" will take you to the self-building dashboard.\n\nTip: You can drag this panel anywhere on screen.',
    primaryCTA: 'Next',
    targetSelector: '#nlq-search-input',
    requiredView: 'galaxy',
    onPrimary: 'next',
  },
  {
    title: 'Galaxy View — See How Metrics Connect',
    body: 'When you ask a question, Galaxy View shows your answer as an interactive node map. Related metrics orbit around it so you get more relevant information, and this is helpful in assuring intent is captured.\n\nThe color of each node tells you how confident the system is. Click any node to expand its details in the side panel.',
    primaryCTA: 'Next',
    targetSelector: '#galaxy-visual',
    requiredView: 'galaxy',
    onPrimary: 'next',
  },
  {
    title: 'Dashboard View',
    body: 'These are persona-based, self-generating, adjustable-on-the-fly dashboards driven by natural language prompts.\n\nThe drop-down is for selecting layouts pertinent to other personas.',
    primaryCTA: 'Next',
    targetSelector: '#dashboard-persona-select',
    requiredView: 'dashboard',
    onPrimary: 'next',
  },
  {
    title: 'Refine Your Dashboard',
    body: 'Use the refinement bar to modify it using natural language or presets to add or modify dashboard components.\n\nClicking on a KPI card will add a trend chart for that element.',
    primaryCTA: 'Next',
    targetSelector: '#dashboard-refine-input',
    requiredView: 'dashboard',
    onPrimary: 'next',
  },
  {
    title: 'What-If — Model Scenarios in Real Time',
    body: 'The What-If panel lets you test business scenarios. Adjust sliders for revenue growth, pricing, headcount, and operating expenses to see how changes would ripple across your KPIs (easily configurable).\n\nThe KPI Impact Preview updates live as you move each slider, showing you projected revenue, growth rate, margins, and more. Then you can apply the scenario to the forecast element in your dashboard.',
    primaryCTA: 'Next',
    targetSelector: '#dashboard-whatif-btn',
    requiredView: 'dashboard',
    onPrimary: 'next',
  },
  {
    title: 'Tour Complete',
    body: '• NLQ learns from every question, reducing and quickly eliminating the need for costly inference.\n\n• Sidebars contain History — easy to reuse prompts via one-click.\n\nMost importantly, the same context layer that serves you through natural language serves your AI agents through protocol.',
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
    <div className="flex items-center gap-1.5">
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
// Draggable, transparent floating card
// ---------------------------------------------------------------------------

function TourModal({
  step,
  stepIndex,
  totalSteps,
  onPrimary,
  onSecondary,
  onBack,
  onSkip,
}: {
  step: TourStep
  stepIndex: number
  totalSteps: number
  onPrimary: () => void
  onSecondary?: () => void
  onBack?: () => void
  onSkip: () => void
}) {
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: -9999, left: -9999 })
  const cardRef = useRef<HTMLDivElement>(null)
  const dragState = useRef<{ dragging: boolean; offsetX: number; offsetY: number }>({
    dragging: false, offsetX: 0, offsetY: 0,
  })
  // Track whether user has manually dragged — if so, stop auto-positioning
  const userDragged = useRef(false)

  // Auto-position near target (only if user hasn't dragged)
  useEffect(() => {
    if (userDragged.current) return

    const place = () => {
      const el = document.querySelector(step.targetSelector)
      if (!el) {
        setPos({ top: window.innerHeight - 320, left: window.innerWidth - 360 })
        return
      }
      const rect = el.getBoundingClientRect()
      const cardW = 340
      const cardH = cardRef.current?.offsetHeight || 260
      const pad = 16

      let top = rect.bottom + pad
      let left = rect.left + rect.width / 2 - cardW / 2

      if (left < pad) left = pad
      if (left + cardW > window.innerWidth - pad) left = window.innerWidth - pad - cardW
      if (top + cardH > window.innerHeight - pad) top = rect.top - cardH - pad
      if (top < pad) top = pad

      setPos({ top, left })
    }

    // Small delay for view transitions
    const timer = setTimeout(place, 80)
    window.addEventListener('resize', place)
    return () => { clearTimeout(timer); window.removeEventListener('resize', place) }
  }, [step.targetSelector, stepIndex])

  // Reset drag flag when step changes so card re-positions for each new step
  useEffect(() => {
    userDragged.current = false
  }, [stepIndex])

  // Drag handlers
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    // Only drag from the title bar area (not buttons)
    if ((e.target as HTMLElement).closest('button')) return
    dragState.current = { dragging: true, offsetX: e.clientX - pos.left, offsetY: e.clientY - pos.top }
    e.preventDefault()
  }, [pos])

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragState.current.dragging) return
      userDragged.current = true
      setPos({
        top: e.clientY - dragState.current.offsetY,
        left: e.clientX - dragState.current.offsetX,
      })
    }
    const onMouseUp = () => { dragState.current.dragging = false }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  return (
    <div
      ref={cardRef}
      onMouseDown={onMouseDown}
      className="fixed z-[10000] w-[340px] rounded-xl p-5 select-none"
      style={{
        fontFamily: "'Quicksand', sans-serif",
        top: pos.top,
        left: pos.left,
        background: 'rgba(15, 23, 42, 0.75)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: '1px solid rgba(11, 202, 217, 0.25)',
        boxShadow: '0 0 30px 2px rgba(11,202,217,0.08), 0 4px 24px rgba(0,0,0,0.4)',
        cursor: 'grab',
      }}
    >
      {/* Close button */}
      <button
        onClick={onSkip}
        className="absolute top-2.5 right-2.5 text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
        aria-label="Close tour"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Title */}
      <h2 className="text-base font-semibold text-white mb-2 pr-5">{step.title}</h2>

      {/* Body */}
      <div className="text-xs text-slate-300 leading-relaxed space-y-2">
        {step.body.split('\n\n').map((para, i) => (
          <p key={i}>{para}</p>
        ))}
      </div>

      {/* CTA Buttons */}
      <div className="flex items-center gap-2 mt-4">
        {onBack && (
          <button
            onClick={onBack}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
          >
            Back
          </button>
        )}
        <button
          onClick={onPrimary}
          className="px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          style={{ background: '#0bcad9', color: '#020617' }}
        >
          {step.primaryCTA}
        </button>
        {step.secondaryCTA && onSecondary && (
          <button
            onClick={onSecondary}
            className="px-4 py-1.5 rounded-lg text-xs font-semibold border transition-colors cursor-pointer"
            style={{ borderColor: '#0bcad9', color: '#0bcad9' }}
          >
            {step.secondaryCTA}
          </button>
        )}
      </div>

      {/* Step indicator + Skip */}
      <div className="flex items-center justify-between mt-3">
        <StepDots total={totalSteps} current={stepIndex} />
        <button
          onClick={onSkip}
          className="text-[10px] text-slate-500 hover:text-slate-400 transition-colors cursor-pointer"
        >
          Skip Tour
        </button>
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
  onStepEnter,
}: ProductTourProps) {
  const [stepIndex, setStepIndex] = useState(0)
  // "tryit" pauses the modals; user's next query submission resumes
  const [paused, setPaused] = useState(false)
  // Track previous stepIndex so we only navigate once per step change
  const prevStepRef = useRef(-1)

  const step = STEPS[stepIndex]

  // Reset when tour becomes visible
  useEffect(() => {
    if (visible) {
      setStepIndex(0)
      setPaused(false)
      prevStepRef.current = -1
    }
  }, [visible])

  // Resume after user submits a query during "Try It"
  useEffect(() => {
    if (paused && querySubmitted) {
      setPaused(false)
      setStepIndex(1) // move to step 2 (Quick-Start Presets)
    }
  }, [paused, querySubmitted])

  // Navigate to the required view ONCE when entering a new step
  // Does NOT react to user tab switches — the modal stays visible regardless
  useEffect(() => {
    if (!visible || paused) return
    if (stepIndex === prevStepRef.current) return
    prevStepRef.current = stepIndex

    const requiredView = step?.requiredView
    if (requiredView && currentView !== requiredView) {
      onNavigate(requiredView)
    }

    // Notify parent so it can run step-specific actions (e.g. open dropdown)
    onStepEnter?.(stepIndex)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, paused, stepIndex])

  const advance = useCallback(() => {
    if (stepIndex < STEPS.length - 1) {
      setStepIndex(s => s + 1)
    } else {
      onDismiss()
    }
  }, [stepIndex, onDismiss])

  const goBack = useCallback(() => {
    if (stepIndex > 0) {
      setStepIndex(s => s - 1)
    }
  }, [stepIndex])

  const handlePrimary = useCallback(() => {
    const action = step.onPrimary || 'next'
    switch (action) {
      case 'tryit':
        // Focus the search bar, then advance to next step
        onFocusSearch()
        advance()
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

  return (
    <>
      <LaserDot targetSelector={step.targetSelector} />
      <TourModal
        step={step}
        stepIndex={stepIndex}
        totalSteps={STEPS.length}
        onPrimary={handlePrimary}
        onSecondary={step.secondaryCTA ? handleSecondary : undefined}
        onBack={stepIndex > 0 ? goBack : undefined}
        onSkip={onDismiss}
      />
    </>
  )
}
