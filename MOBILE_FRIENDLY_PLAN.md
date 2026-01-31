# NLQ App - Mobile-Friendly Implementation Plan

> **Created**: 2026-01-31
> **Status**: Planning
> **Target**: Full mobile responsiveness across all viewports (320px - 2560px+)

---

## Executive Summary

The NLQ app is currently **desktop-first with minimal responsive design**. While the technical foundation (Tailwind CSS, proper viewport meta tag) is solid, the app uses fixed pixel widths throughout and lacks breakpoint-aware layouts.

**Key Finding**: Only 3 instances of responsive prefixes (`sm:`, `md:`) exist in the entire codebase.

---

## Current State Assessment

| Area | Current State | Mobile Ready? |
|------|---------------|---------------|
| Viewport Meta | Correct `width=device-width` | ✓ Yes |
| Tailwind Setup | v4.1.18 configured | ✓ Yes |
| Breakpoint Usage | 3 instances only | ✗ No |
| Sidebar | Fixed 283px width | ✗ No |
| Header | Dense controls | ✗ No |
| Galaxy SVG | Fixed 700x700px | ✗ No |
| Dashboard Grid | No responsive columns | ✗ No |
| Touch Support | Mouse events only | ✗ No |
| Charts | ResponsiveContainer | ⚠️ Partial |

---

## Breakpoint Strategy

Using Tailwind's default breakpoints, aligned with common device sizes:

| Breakpoint | Width | Target Devices |
|------------|-------|----------------|
| Default (mobile-first) | 0-639px | Phones (portrait) |
| `sm:` | 640px+ | Phones (landscape), small tablets |
| `md:` | 768px+ | Tablets (portrait) |
| `lg:` | 1024px+ | Tablets (landscape), small laptops |
| `xl:` | 1280px+ | Laptops, desktops |
| `2xl:` | 1536px+ | Large monitors |

---

## Implementation Phases

### Phase 1: Foundation & Layout (Priority: CRITICAL)

**Goal**: Core layout works on all screen sizes without horizontal scroll

#### 1.1 App.tsx - Main Layout Restructure

**Current Issues**:
- Sidebar fixed at `w-[283px]` - overflows on mobile
- Main content area doesn't adapt
- Header controls too dense

**Changes**:
```tsx
// BEFORE (current)
<aside className="w-[283px] shrink-0 ...">

// AFTER (responsive)
<aside className={`
  fixed inset-y-0 right-0 z-40
  w-full sm:w-80 lg:w-[283px]
  transform transition-transform duration-300
  ${sidebarOpen ? 'translate-x-0' : 'translate-x-full'}
  lg:relative lg:translate-x-0
`}>
```

**Implementation Tasks**:
- [ ] Make sidebar a mobile drawer (full-width overlay on mobile)
- [ ] Add mobile hamburger menu button
- [ ] Implement sidebar backdrop overlay on mobile
- [ ] Add close button inside sidebar on mobile
- [ ] Adjust main content padding for mobile

**Files to modify**:
- `/src/App.tsx`
- `/src/index.css` (add overlay styles)

#### 1.2 Header - Responsive Controls

**Current Issues**:
- View mode buttons, toggle, persona buttons all in one row
- No room on mobile screens

**Changes**:
```tsx
// Responsive header layout
<header className="flex flex-col sm:flex-row ...">
  {/* Top row: Logo + hamburger (mobile) / Logo + main controls (desktop) */}
  <div className="flex items-center justify-between">
    <Logo />
    <button className="lg:hidden">☰</button> {/* Mobile menu */}
  </div>

  {/* Bottom row on mobile / inline on desktop */}
  <div className="flex flex-wrap gap-2 sm:gap-4 ...">
    {/* Controls collapse into icons on mobile */}
  </div>
</header>
```

**Implementation Tasks**:
- [ ] Split header into 2 rows on mobile
- [ ] Add hamburger menu icon (mobile only)
- [ ] Collapse button labels to icons on mobile
- [ ] Stack persona buttons in 2 rows on mobile
- [ ] Add header height CSS variable for content offset

---

### Phase 2: Galaxy View Responsiveness (Priority: HIGH)

**Goal**: Galaxy visualization scales to viewport and works with touch

#### 2.1 GalaxyView.tsx - SVG Scaling

**Current Issues**:
- Fixed 700x700px SVG dimensions
- Fixed 293px left panel
- No touch event handling

**Changes**:
```tsx
// Use viewBox with dynamic container sizing
const containerRef = useRef<HTMLDivElement>(null);
const [dimensions, setDimensions] = useState({ width: 700, height: 500 });

useEffect(() => {
  const updateDimensions = () => {
    if (containerRef.current) {
      const { width, height } = containerRef.current.getBoundingClientRect();
      setDimensions({ width, height: Math.min(height, width * 0.8) });
    }
  };

  const resizeObserver = new ResizeObserver(updateDimensions);
  if (containerRef.current) resizeObserver.observe(containerRef.current);
  return () => resizeObserver.disconnect();
}, []);

<svg
  viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
  className="w-full h-auto"
  preserveAspectRatio="xMidYMid meet"
>
```

**Implementation Tasks**:
- [ ] Add ResizeObserver for dynamic SVG sizing
- [ ] Convert fixed pixel SVG to viewBox-based
- [ ] Make left query panel stack above visualization on mobile
- [ ] Adjust node sizes for touch targets (min 44x44px)
- [ ] Add touch event handlers for node interaction

**Files to modify**:
- `/src/components/galaxy/GalaxyView.tsx`
- `/src/components/galaxy/GalaxyVisualization.tsx`
- `/src/components/galaxy/GalaxyNode.tsx`

#### 2.2 Query Input Area

**Changes**:
```tsx
// Stack layout on mobile
<div className="flex flex-col lg:flex-row gap-4">
  {/* Query input: full width on mobile, constrained on desktop */}
  <div className="w-full lg:max-w-2xl">
    <input className="w-full px-4 py-3 text-base lg:text-lg" />
  </div>

  {/* Quick actions: horizontal scroll on mobile */}
  <div className="flex gap-2 overflow-x-auto pb-2 lg:flex-wrap lg:overflow-visible">
    {quickActions.map(action => (
      <button className="whitespace-nowrap px-3 py-2 text-sm" />
    ))}
  </div>
</div>
```

**Implementation Tasks**:
- [ ] Make query input full-width on mobile
- [ ] Add horizontal scroll for quick action buttons on mobile
- [ ] Increase touch target size for buttons

---

### Phase 3: Dashboard Grid Responsiveness (Priority: HIGH)

**Goal**: Dashboard tiles reflow based on screen size

#### 3.1 DashboardRenderer.tsx - Responsive GridLayout

**Current Issues**:
- Fixed 12-column grid
- No breakpoint definitions for react-grid-layout
- Tiles don't reflow on resize

**Changes**:
```tsx
import { Responsive, WidthProvider } from 'react-grid-layout';

const ResponsiveGridLayout = WidthProvider(Responsive);

// Define responsive breakpoints
const breakpoints = { lg: 1024, md: 768, sm: 640, xs: 480, xxs: 0 };
const cols = { lg: 12, md: 8, sm: 6, xs: 4, xxs: 2 };

// Generate layouts for each breakpoint
const generateResponsiveLayouts = (tiles: DashboardTile[]) => ({
  lg: tiles.map(tile => ({ ...tile.position, i: tile.id })),
  md: tiles.map(tile => ({
    ...tile.position,
    i: tile.id,
    w: Math.min(tile.position.w, 8),
    x: Math.min(tile.position.x, 8 - tile.position.w)
  })),
  sm: tiles.map(tile => ({
    i: tile.id,
    x: 0,
    y: tile.position.y,
    w: 6,  // Full width on small
    h: tile.position.h
  })),
  xs: tiles.map(tile => ({
    i: tile.id,
    x: 0,
    y: tile.position.y,
    w: 4,
    h: tile.position.h
  })),
  xxs: tiles.map(tile => ({
    i: tile.id,
    x: 0,
    y: tile.position.y,
    w: 2,
    h: Math.max(tile.position.h, 2)  // Ensure minimum height
  }))
});

<ResponsiveGridLayout
  layouts={generateResponsiveLayouts(tiles)}
  breakpoints={breakpoints}
  cols={cols}
  rowHeight={80}
  isDraggable={!isMobile}  // Disable drag on mobile
  isResizable={!isMobile}  // Disable resize on mobile
  margin={[12, 12]}
>
```

**Implementation Tasks**:
- [ ] Convert to ResponsiveGridLayout
- [ ] Define column counts per breakpoint
- [ ] Generate mobile-friendly layouts (stacked single column)
- [ ] Disable drag/resize on mobile (prevents scroll conflicts)
- [ ] Reduce margins on mobile

**Files to modify**:
- `/src/components/generated-dashboard/DashboardRenderer.tsx`

#### 3.2 Dashboard Config Updates

Update JSON configs to include responsive hints:

```json
{
  "layout": {
    "type": "grid",
    "columns": { "lg": 12, "md": 8, "sm": 6, "xs": 4 },
    "rowHeight": { "lg": 80, "sm": 60 }
  },
  "tiles": [
    {
      "id": "revenue-kpi",
      "position": {
        "desktop": { "x": 0, "y": 0, "w": 3, "h": 2 },
        "mobile": { "x": 0, "y": 0, "w": 2, "h": 2 }
      }
    }
  ]
}
```

**Implementation Tasks**:
- [ ] Add responsive position definitions to tile configs
- [ ] Create layout generator function
- [ ] Update TypeScript types for responsive layouts

**Files to modify**:
- `/src/config/dashboards/*.json`
- `/src/types/generated-dashboard.ts`

---

### Phase 4: Component Touch Optimization (Priority: MEDIUM)

**Goal**: All interactive elements are touch-friendly

#### 4.1 Touch Target Sizes

Per WCAG guidelines, touch targets should be at least **44x44px**.

**Implementation Tasks**:
- [ ] Audit all buttons, ensure min-height: 44px on mobile
- [ ] Add padding to small icons
- [ ] Increase persona selector button sizes
- [ ] Add `touch-action` CSS properties where needed

**CSS additions**:
```css
/* In index.css */
@media (hover: none) and (pointer: coarse) {
  /* Touch device optimizations */
  .btn-touch {
    min-height: 44px;
    min-width: 44px;
  }

  .touch-scroll {
    -webkit-overflow-scrolling: touch;
  }
}
```

#### 4.2 Gesture Support

**Implementation Tasks**:
- [ ] Add swipe gesture for sidebar on mobile
- [ ] Add pinch-to-zoom for Galaxy visualization (optional)
- [ ] Add pull-to-refresh for dashboard (optional)

---

### Phase 5: Chart Responsiveness (Priority: MEDIUM)

**Goal**: Charts remain readable at all sizes

#### 5.1 Chart Sizing Adjustments

**Current State**: Recharts `ResponsiveContainer` provides good horizontal scaling.

**Additional Changes Needed**:
```tsx
// Adaptive font sizes
const getChartFontSize = () => {
  if (typeof window === 'undefined') return 12;
  return window.innerWidth < 640 ? 10 : 12;
};

// Adaptive legend position
<Legend
  layout={isMobile ? "horizontal" : "vertical"}
  align={isMobile ? "center" : "right"}
  verticalAlign={isMobile ? "bottom" : "middle"}
/>
```

**Implementation Tasks**:
- [ ] Add responsive font sizing for labels
- [ ] Reposition legends on mobile (bottom instead of right)
- [ ] Reduce chart padding on mobile
- [ ] Add horizontal scroll wrapper for wide charts if needed

**Files to modify**:
- `/src/components/dashboard/charts/*.tsx`
- `/src/components/dashboard/shared/*.tsx`

---

### Phase 6: User Guide Page (Priority: LOW)

**Current State**: Already has some responsive grids (`md:grid-cols-2`, `md:grid-cols-3`)

**Additional Tasks**:
- [ ] Ensure all images scale properly
- [ ] Test reading experience on mobile
- [ ] Add table horizontal scroll if needed

---

## Mobile-First CSS Additions

Add to `/src/index.css`:

```css
@import "tailwindcss";

/* ============================================
   MOBILE-FIRST FOUNDATION
   ============================================ */

@layer theme {
  :root {
    --color-autonomous-cyan: #0bcad9;

    /* Responsive spacing tokens */
    --spacing-page-x: 1rem;
    --spacing-page-y: 1rem;
    --header-height: 56px;
    --sidebar-width: 100%;
  }

  @media (min-width: 640px) {
    :root {
      --spacing-page-x: 1.5rem;
      --sidebar-width: 320px;
    }
  }

  @media (min-width: 1024px) {
    :root {
      --spacing-page-x: 2rem;
      --sidebar-width: 283px;
    }
  }
}

@layer utilities {
  /* Safe area insets for notched devices */
  .safe-top {
    padding-top: env(safe-area-inset-top);
  }

  .safe-bottom {
    padding-bottom: env(safe-area-inset-bottom);
  }

  /* Prevent text selection on touch */
  .no-select {
    -webkit-user-select: none;
    user-select: none;
  }

  /* Hide scrollbar but keep functionality */
  .scrollbar-hide {
    -ms-overflow-style: none;
    scrollbar-width: none;
  }
  .scrollbar-hide::-webkit-scrollbar {
    display: none;
  }

  /* Touch scroll optimization */
  .touch-scroll {
    -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
  }
}

/* ============================================
   MOBILE SIDEBAR OVERLAY
   ============================================ */

.sidebar-backdrop {
  @apply fixed inset-0 bg-black/50 z-30;
  @apply transition-opacity duration-300;
  @apply lg:hidden;
}

.sidebar-backdrop.hidden {
  @apply opacity-0 pointer-events-none;
}

/* ============================================
   RESPONSIVE GRID LAYOUT OVERRIDES
   ============================================ */

.react-grid-layout {
  @apply touch-scroll;
}

@media (max-width: 639px) {
  /* Stack all grid items on mobile */
  .react-grid-item {
    position: relative !important;
    transform: none !important;
    width: 100% !important;
    margin-bottom: 1rem;
  }
}
```

---

## Implementation Order

### Sprint 1: Core Layout (3-4 hours)
1. App.tsx layout restructure
2. Mobile sidebar drawer
3. Responsive header

### Sprint 2: Galaxy View (2-3 hours)
1. SVG dynamic sizing
2. Query panel stacking
3. Touch events for nodes

### Sprint 3: Dashboard Grid (2-3 hours)
1. ResponsiveGridLayout implementation
2. Layout generation per breakpoint
3. Disable drag on mobile

### Sprint 4: Polish (1-2 hours)
1. Touch target sizes
2. Chart legend repositioning
3. Testing across devices

---

## Testing Checklist

### Viewport Testing
- [ ] iPhone SE (375px)
- [ ] iPhone 14 (390px)
- [ ] iPhone 14 Pro Max (430px)
- [ ] iPad Mini (768px)
- [ ] iPad Pro (1024px)
- [ ] Desktop (1280px+)

### Interaction Testing
- [ ] Sidebar opens/closes on mobile
- [ ] Touch scrolling works smoothly
- [ ] No horizontal overflow
- [ ] Galaxy nodes tappable
- [ ] Dashboard tiles readable
- [ ] Charts display correctly

### Orientation Testing
- [ ] Portrait on phones
- [ ] Landscape on phones
- [ ] Both orientations on tablets

---

## Files to Modify (Summary)

| File | Priority | Changes |
|------|----------|---------|
| `src/App.tsx` | CRITICAL | Layout restructure, mobile drawer |
| `src/index.css` | CRITICAL | Mobile-first utilities |
| `src/components/generated-dashboard/DashboardRenderer.tsx` | HIGH | ResponsiveGridLayout |
| `src/components/galaxy/GalaxyView.tsx` | HIGH | Dynamic SVG, touch |
| `src/components/galaxy/GalaxyVisualization.tsx` | HIGH | ViewBox scaling |
| `src/components/dashboard/charts/*.tsx` | MEDIUM | Legend positioning |
| `src/config/dashboards/*.json` | LOW | Responsive positions |
| `src/types/generated-dashboard.ts` | LOW | Type updates |

---

## Success Criteria

1. **No horizontal scroll** on any viewport 320px+
2. **Touch-friendly** all interactive elements ≥44x44px
3. **Readable content** on phone screens
4. **Smooth transitions** sidebar/layouts animate properly
5. **Performance** no jank during resize/scroll
6. **Accessibility** maintains keyboard navigation

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| react-grid-layout mobile issues | Test thoroughly; have fallback CSS-only grid |
| SVG performance on mobile | Reduce node count on small screens |
| Touch conflicts with scroll | Use `touch-action` CSS properties |
| Breaking desktop layout | Test desktop after each mobile change |

---

*Plan created by Claude Code | Ready for implementation*
