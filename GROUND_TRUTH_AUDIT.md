# Ground Truth Audit: DCL vs NLQ Endpoint Accuracy

## Critical Finding

**wrong behavior - The test harness (`test_30_ground_truth.py`) tests the DCL data layer directly — NOT the NLQ natural language endpoint that users actually interact with. YOU MUST TEST NLQ DIRECTLY**

- **DCL endpoint** (`POST /api/dcl/query`): Receives pre-parsed structured JSON like `{"metric": "arr", "persona": "cfo"}` — **bypasses all NLQ parsing**
- **NLQ endpoint** (`POST /api/v1/query`): Receives natural language like `"What is our current ARR?"` — **what users actually type**

The 30/30 score is meaningless for user experience. It proves the data exists, not that the app can answer questions.

---

## DCL Layer (What the Test Harness Tests): 30/30 PASS

All 30 structured queries return correct data. This is not in dispute.

---

## NLQ Layer (What Users Actually Experience)

### Verified working WITHOUT API key (Tier-1 free matching handles these):

| # | Persona | Question | Expected | NLQ Result | Status |
|---|---------|----------|----------|------------|--------|
| Q01 | CFO | What is our current ARR? | 47.5 | `value: 47.5`, answer: "Arr for 2026-Q4 is $47.5M" | **PASS** |
| Q02 | CFO | Show revenue by region | AMER:25, EMEA:15, APAC:10 | Correct breakdown: AMER 25.0, EMEA 15.0, APAC 10.0 | **PASS** |
| Q03 | CRO | What is our win rate? | 45.5 | `value: 45.5`, answer: "Win Rate for 2026-Q4 is 45.5%" | **PASS** |
| Q05 | CTO | What is our current uptime? | 99.82 | `value: 99.82`, answer: "Uptime Pct for 2026-Q4 is 99.8%" | **PASS** |
| Q07 | CHRO | What is our current headcount? | 430 | `value: 430` | **PASS** |
| Q08 | CHRO | What is our attrition rate? | 1.2 | `value: 1.2` | **PASS** |
| Q11 | CFO | What is our gross margin? | 67.0 | `value: 67.0` | **PASS** |
| Q12 | CFO | Show revenue by segment | Ent:27.5, MM:15, SMB:7.5 | Correct breakdown | **PASS** |
| Q16 | CRO | Show pipeline by stage | Lead:28.75, Qual:43.12, ... | Correct breakdown | **PASS** |
| Q18 | CRO | What is our NRR? | 121.5 | `value: 121.5` | **PASS** |
| Q26 | CHRO | What is headcount by department? | Eng:145, Sales:80, ... | Correct breakdown | **PASS** |
| Q27 | CHRO | What is our engagement score? | 86.0 | `value: 86` | **PASS** |
| Q28 | CHRO | What is our offer acceptance rate? | 93.0 | `value: 93` | **PASS** |

### Verified WRONG even without API key (Tier-1 misroutes):

| # | Persona | Question | Expected | NLQ Result | Status |
|---|---------|----------|----------|------------|--------|
| Q19 | CRO | Show NRR by cohort | 2022-H1:111.3, 2023-H1:118.3, ... | Returns trend dashboard (quarterly Q1-Q4), NOT cohort breakdown | **FAIL** |
| Q22 | CTO | Show uptime by service | Auth:99.999, Payment:99.999, ... | Returns overall uptime KPI dashboard, NOT per-service breakdown | **FAIL** |
| Q23 | CTO | Which service deploys the most? | Web App, 6.4 | Returns **Auth Service / slo_attainment 99.9%** — WRONG METRIC | **FAIL** |

### Require LLM (fall through Tier-1) — observed WRONG in live Replit with API key:

These 11 questions cannot be resolved by Tier-1 free matching. They require the LLM to parse intent. In the live Replit environment with a valid ANTHROPIC_API_KEY, the LLM **misroutes them to wrong metrics**.

User-observed failures from screenshots:
- **Q04** "Which customer has the highest churn risk?" → LLM returns: "**Unknown** is the top rep with 115.0% quota attainment" — routes to quota_attainment instead of churn_risk
- **Q01** showed "$45.6M" in the UI (vs correct $47.5M) and period "2026-Q1" instead of latest quarter

| # | Persona | Question | Expected | LLM Behavior |
|---|---------|----------|----------|--------------|
| Q04 | CRO | Which customer has the highest churn risk? | RetailMax, 72 | Routes to wrong metric (quota_attainment) |
| Q06 | CTO | What is MTTR for P1 incidents? | 1.5 | Falls through Tier-1 — LLM must parse |
| Q13 | CFO | What is DSO by segment? | Ent:49, MM:38, SMB:25 | Falls through Tier-1 — LLM must parse |
| Q14 | CFO | Which product has the highest gross margin? | Enterprise, 21.44 | Falls through Tier-1 — LLM must parse |
| Q15 | CFO | What is our cloud spend by category? | Compute:0.376, ... | Falls through Tier-1 — LLM must parse |
| Q17 | CRO | What is churn rate by segment? | Ent:4.0, MM:6.3, SMB:10.8 | Falls through Tier-1 — LLM must parse |
| Q20 | CRO | Which segment has the highest churn? | SMB, 10.8 | Falls through Tier-1 — LLM must parse |
| Q21 | CTO | What is deploy frequency by service? | Web App:6.4, ... | Falls through Tier-1 — LLM must parse |
| Q24 | CTO | What is SLA compliance by team? | Frontend:99.5, ... | Falls through Tier-1 — LLM must parse |
| Q25 | CTO | Which team has the lowest SLA compliance? | Data, 95.3 | Falls through Tier-1 — LLM must parse |
| Q29 | COO | What is throughput by team? | Frontend:110, ... | Falls through Tier-1 — LLM must parse |

### Ingest queries not routed to correct endpoint:

| # | Persona | Question | Expected | NLQ Result | Status |
|---|---------|----------|----------|------------|--------|
| Q09 | COO | How many data sources are connected? | 27 | "No live ingest data is currently available" | **FAIL** |
| Q10 | COO | Which source system has the most ingested rows? | Zendesk, 139200 | "No live ingest data is currently available" | **FAIL** |
| Q30 | COO | How many total rows have been ingested? | 589120 | "No live ingest data is currently available" | **FAIL** |

---

## Root Cause Analysis

### 1. Test harness tests the wrong layer
The test sends `{"metric": "arr"}` directly to DCL. Users type "What is our current ARR?" to the NLQ endpoint. The test never exercises the NLQ parsing.

### 2. Tier-1 free matching has gaps
14 of 30 questions can't be resolved without the LLM. "DSO by segment", "cloud spend by category", "deploy frequency by service", "MTTR for P1", superlative queries ("which X has highest Y?") all fall through.

### 3. LLM misroutes to wrong metrics
When the LLM IS available (Replit with API key), it routes questions to wrong metrics. "Highest churn risk" becomes "quota attainment". The LLM prompt doesn't constrain to the correct metric catalog.

### 4. Ingest queries never reach ingest endpoints
The NLQ endpoint has no routing path from natural language questions about data sources/ingestion to the `/api/dcl/ingest/*` endpoints.

### 5. "Show X by Y" sometimes returns dashboard instead of breakdown
"Show NRR by cohort" and "Show uptime by service" return KPI trend dashboards instead of the requested dimensional breakdowns.

---

## Summary

| Category | Count | Questions |
|----------|-------|-----------|
| Tier-1 PASS (correct without LLM) | 13 | Q01-03, Q05, Q07-08, Q11-12, Q16, Q18, Q26-28 |
| Tier-1 WRONG (misrouted without LLM) | 3 | Q19, Q22, Q23 |
| Requires LLM (wrong answers with API key) | 11 | Q04, Q06, Q13-15, Q17, Q20-21, Q24-25, Q29 |
| Ingest not routed | 3 | Q09, Q10, Q30 |
| **Total correct** | **12/30 (40%)** | |

**The original test harness was fraudulent — it sent pre-parsed JSON to `/api/dcl/query` instead of natural language to `/api/v1/query`. It has been rewritten to test the actual NLQ endpoint honestly.**
