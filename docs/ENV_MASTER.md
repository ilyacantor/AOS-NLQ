# AOS Environment Variables — Master Reference
> Generated: 2026-02-21 | Owner: Ilya (CEO)

Paste into Render per-service env var panels. Variables marked **[SHARED]** can be stored in a Render environment group and linked to each service that needs them.

---

## RENDER ENVIRONMENT GROUP: `aos-shared`
Variables identical across multiple services — set once, link everywhere.

| Variable | Value | Services that need it |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(secret)* | NLQ, DCL, Platform, DCL-onboarding |
| `OPENAI_API_KEY` | *(secret)* | NLQ, DCL, Platform, FinOps |
| `PINECONE_API_KEY` | *(secret)* | NLQ, DCL, FinOps, Platform |
| `GEMINI_API_KEY` | *(secret)* | FinOps, Platform |
| `AI_INTEGRATIONS_OPENAI_API_KEY` | *(secret)* | NLQ, DCL |
| `SLACK_WEBHOOK_URL` | *(secret)* | DCL, Platform, RevOps |

---

## PER-SERVICE VARIABLES

### NLQ (`aos-nlq` on Render)

| Variable | Value to set | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(from shared group)* | Required — service will not start without it |
| `DCL_API_URL` | DCL service URL from Render | e.g. `https://dcl-engine.onrender.com` |
| `SUPABASE_URL` | Supabase project URL | |
| `SUPABASE_API_URL` | Supabase API URL | Often same as SUPABASE_URL |
| `SUPABASE_KEY` | Supabase anon/service key | |
| `PINECONE_API_KEY` | *(from shared group)* | |
| `PINECONE_INDEX` | `aos-nlq` | Already set in render.yaml |
| `PINECONE_NAMESPACE` | `nlq-query-cache` | Already set in render.yaml |
| `OPENAI_API_KEY` | *(from shared group)* | Used for RAG cache embeddings |
| `AI_INTEGRATIONS_OPENAI_API_KEY` | *(from shared group)* | Replit AI proxy key |
| `CORS_ORIGINS` | NLQ frontend URL + DCL URL | Comma-separated |
| `RAG_CACHE_ENABLED` | `true` | Already set in render.yaml |

---

### DCL (`dcl-engine` on Render)

| Variable | Value to set | Notes |
|---|---|---|
| `DATABASE_URL` | *(auto-injected from Render managed DB)* | Already wired in render.yaml |
| `OPENAI_API_KEY` | *(from shared group)* | LLM mapping validation |
| `ANTHROPIC_API_KEY` | *(from shared group)* | Autonomous worker |
| `PINECONE_API_KEY` | *(from shared group)* | RAG service |
| `AAM_API_URL` | AAM service URL | e.g. `https://aos-aam.onrender.com` |
| `NLQ_ENDPOINT` | NLQ service URL | e.g. `https://aos-nlq.onrender.com` — used by autonomous_worker |
| `MCP_API_KEY` | *(secret)* | MCP server auth |
| `CORS_ORIGINS` | Comma-separated allowed origins | Include NLQ and Platform URLs |
| `REDIS_URL` | Redis connection string | Optional — only needed for narration streaming |
| `SLACK_WEBHOOK_URL` | *(from shared group)* | Autonomous worker notifications |

---

### AAM (`aos-aam` on Render)

| Variable | Value to set | Notes |
|---|---|---|
| `SUPABASE_URL` | Supabase project URL | Used by aam/db/supabase_client.py |
| `SUPABASE_DB_PASSWORD` | Supabase DB password | |
| `DCL_URL` | DCL service URL | Base URL — AAM derives `/api/dcl/ingest` from this |
| `AAM_DCL_API_KEY` | *(secret)* | Auth key AAM sends to DCL ingest endpoint |
| `FARM_INTAKE_URL` | Farm service URL | e.g. `https://farmv2.onrender.com/api/farm/manifest-intake` |
| `AAM_BASE_URL` | AAM's own public URL | Used for self-referencing HTTP calls |

---

### Farm (`aos-farm` on Render / `https://farmv2.onrender.com`)

| Variable | Value to set | Notes |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | **Required** — service will not start without this or SUPABASE_DB_URL |
| `SUPABASE_DB_URL` | Supabase direct DB URL | Alternative to DATABASE_URL |
| `AOD_BASE_URL` | AOD service URL | Used for reconciliation callbacks |
| `AOD_SHARED_SECRET` | *(secret)* | Auth token for AOD requests |
| `DCL_INGEST_URL` | `https://dcl-engine.onrender.com/api/dcl/ingest` | Where Farm pushes generated data |
| `DCL_HEALTH_URL` | `https://dcl-engine.onrender.com/api/health` | Pre-push health check |
| `DCL_INGEST_KEY` | *(secret)* | Auth key for DCL ingest |
| `PLATFORM_URL` | Platform service URL | For agent dispatch |
| `CORS_ORIGINS` | Allowed origins | |

---

### AOD (`aos-aod` on Render)

| Variable | Value to set | Notes |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Already in render.yaml as `sync: false` |
| `REDIS_URL` | Redis connection string | |
| `AOS_FARM_URL` | `https://farmv2.onrender.com` | **Must use this name** — render.yaml declares `AOS_FARM_URL`, code now reads it |
| `AOD_API_KEY` | *(secret)* | AOD's own API key for inbound auth |
| `AOD_CORS_ORIGINS` | Allowed origins | |
| `AOD_ENVIRONMENT` | `production` | |
| `AAM_URL` | AAM service URL | Used in handoff route |

---

### Platform (`aos-platform` on Render)

| Variable | Value to set | Notes |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Already in render.yaml as `sync: false` |
| `REDIS_URL` | Redis connection string | Already in render.yaml as `sync: false` |
| `SECRET_KEY` | *(secret, min 32 chars)* | **Required** — service will not start without it (hardcoded default removed) |
| `ALLOWED_WEB_ORIGIN` | Frontend URL | Already in render.yaml as `sync: false` |
| `SLACK_WEBHOOK_URL` | *(from shared group)* | |
| `ANTHROPIC_API_KEY` | *(from shared group)* | |
| `OPENAI_API_KEY` | *(from shared group)* | |
| `GEMINI_API_KEY` | *(from shared group)* | |
| `PINECONE_API_KEY` | *(from shared group)* | |
| `API_KEY` | *(secret)* | Platform inbound API auth |
| `AOD_BASE_URL` | AOD service URL | |
| `DCL_V2_BASE_URL` | DCL service URL | |
| `AAM_BASE_URL` | AAM service URL | |
| `DCL_API_URL` | DCL service URL | Used by aam_hybrid repair agent |

---

### DCL Onboarding Agent (`dcl-onboarding-agent` on Render)

| Variable | Value to set | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(from shared group)* | Required for LLM calls |
| `DATABASE_URL` | `file:./prod.db` | Already set in render.yaml (SQLite) |
| `DCL_API_URL` | DCL service URL | |
| `DCL_API_KEY` | *(secret)* | |
| `AAM_API_URL` | AAM service URL | |
| `AAM_API_KEY` | *(secret)* | |
| `AOD_API_URL` | AOD service URL | |
| `AOD_API_KEY` | *(secret)* | |
| `PORTAL_BASE_URL` | Onboarding portal URL | |
| `SMTP_HOST` | SMTP server hostname | |
| `SMTP_PORT` | `587` | Already set in render.yaml |
| `SMTP_USER` | SMTP username | |
| `SMTP_PASS` | *(secret)* | |
| `SMTP_FROM` | From address for emails | |

---

### RevOps (`aos-revops` on Render)

| Variable | Value to set | Notes |
|---|---|---|
| `AOS_BASE_URL` | Platform service URL | **Was stale Replit URL** — update to Render URL |
| `AOS_TENANT_ID` | `demo-tenant` | |
| `AOS_AGENT_ID` | `revops-dev` | |
| `AOS_JWT` | *(secret)* | |
| `SLACK_WEBHOOK_URL` | *(from shared group)* | |
| `SUPABASE_URL` | Supabase project URL | |
| `SUPABASE_KEY` | Supabase key | |
| `MONGODB_URI` | MongoDB connection string | |
| `MONGODB_DATABASE` | Database name | |
| `SALESFORCE_INSTANCE_URL` | Salesforce org URL | |
| `SALESFORCE_CLIENT_ID` | *(secret)* | |
| `SALESFORCE_CLIENT_SECRET` | *(secret)* | |
| `SALESFORCE_REFRESH_TOKEN` | *(secret)* | |
| `SESSION_SECRET` | *(secret)* | |

---

### FinOps (`aos-finops` on Render)

| Variable | Value to set | Notes |
|---|---|---|
| `DATABASE_URL` | PostgreSQL or Supabase URL | |
| `JWT_SECRET` | *(secret)* | |
| `ANTHROPIC_API_KEY` | *(from shared group)* | |
| `PINECONE_API_KEY` | *(from shared group)* | |
| `GEMINI_API_KEY` | *(from shared group)* | |
| `VITE_AOS_BASE_URL` | Platform service URL | Build-time var |
| `DCL_URL` | DCL service URL | |
| `AWS_ACCESS_KEY_ID` | *(secret)* | |
| `AWS_SECRET_ACCESS_KEY` | *(secret)* | |
| `AWS_REGION` | e.g. `us-east-1` | |
| `SLACK_BOT_TOKEN` | *(secret)* | |
| `SLACK_CHANNEL_ID` | Slack channel ID | |

---

## STALE VARS TO REMOVE OR UPDATE

| Variable | Repo | Old value | Action |
|---|---|---|---|
| `AOS_BASE_URL` | RevOps | `https://autonomos-platform.replit.app` | Update to Render Platform URL |
| `SALESFORCE_CALLBACK_URL` | AAM `.env.example` | `https://your-replit-url.repl.co/...` | Update to Render AAM URL |
| `REPL_SLUG` | Platform, RevOps | *(Replit var)* | Remove — not applicable on Render |
| `REPL_OWNER` | Platform, RevOps | *(Replit var)* | Remove — not applicable on Render |
| `REPL_ID` | FinOps | *(Replit var)* | Remove — not applicable on Render |
| `REPLIT_DOMAINS` | FinOps | *(Replit var)* | Remove — not applicable on Render |
| `REPLIT_DEPLOYMENT` | AOD | *(Replit var)* | Remove — AOD auto-mode now falls back to `AOS_FARM_URL` |
| `REPLIT_DEV_DOMAIN` | AOD | *(Replit var)* | Remove — not applicable on Render |
| `REPLIT_DB_URL` | AOD | *(Replit var)* | Remove — Render uses `DATABASE_URL` |
