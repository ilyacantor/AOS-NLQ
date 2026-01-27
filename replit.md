# aos-nlq - Natural Language Query Engine

## Overview
aos-nlq is a standalone Natural Language Query interface for financial data. It sits on top of DCLv2 (Data Unification Engine), providing entities for downstream consumption to agents and humans.

**Current State:** Development mode - awaiting test data upload

## Project Architecture

### Core Components
- **src/App.tsx** - Main React application with AutonomOS branded UI
- **src/index.css** - Tailwind v4 CSS with custom theme
- **db.py** - Supabase PostgreSQL database connection utilities
- **dcl_client.py** - HTTP client for DCLv2 data unification engine

### Technology Stack
- **Frontend:** React + Vite + TypeScript + Tailwind CSS v4
- **Database:** Supabase PostgreSQL (external)
- **DCL Integration:** HTTP/API client for DCLv2 entities

### Color Palette (AutonomOS)
- **Primary:** Cyan (#0bcad9)
- **Success:** Green (#22c55e)
- **Info:** Blue (#3b82f6)
- **AI/Intelligence:** Purple (#a855f7)
- **Background:** Slate (#020617, #0f172a)
- **Typography:** Quicksand (Google Fonts)

## Environment Variables
- `SUPABASE_URL` - PostgreSQL connection string for Supabase

## Recent Changes
- **2026-01-27:** Rebuilt with React + Vite + Tailwind v4 (migrated from Streamlit)
- **2026-01-27:** Fixed Tailwind v4 PostCSS config (requires `@tailwindcss/postcss` package)
- **2026-01-27:** Added production build scripts

## Running the Application
```bash
npm run dev      # Development
npm run build    # Production build
npm run start    # Serve production build
```

## Configuration Notes
- **postcss.config.js** - Uses `@tailwindcss/postcss` (required for Tailwind v4)
- **vite.config.ts** - Server configured with `allowedHosts: true` for Replit preview

## User Preferences
- Dark mode interface (default, no light mode toggle)
- AutonomOS color palette with Cyan accents
- Quicksand font family
- React + Tailwind frontend (NOT Streamlit)

## Next Steps
1. Upload test data set for development
2. Configure DCLv2 endpoint connection
3. Implement NLQ processing logic
4. Add data visualization for results
