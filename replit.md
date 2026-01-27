# aos-nlq - Natural Language Query Engine

## Overview
aos-nlq is a standalone Natural Language Query interface for financial data. It sits on top of DCLv2 (Data Unification Engine), providing entities for downstream consumption to agents and humans.

**Current State:** Development mode - awaiting test data upload

## Project Architecture

### Core Components
- **app.py** - Main Streamlit application with AutonomOS branded UI
- **db.py** - Supabase PostgreSQL database connection utilities
- **dcl_client.py** - HTTP client for DCLv2 data unification engine

### Technology Stack
- **Frontend:** Streamlit with custom CSS (AutonomOS color palette)
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
- **2026-01-27:** Initial project setup with Streamlit UI and AutonomOS branding

## Running the Application
```bash
streamlit run app.py --server.port 5000
```

## User Preferences
- Dark mode interface (default, no light mode toggle)
- AutonomOS color palette with Cyan accents
- Quicksand font family

## Next Steps
1. Upload test data set for development
2. Configure DCLv2 endpoint connection
3. Implement NLQ processing logic
4. Add data visualization for results
