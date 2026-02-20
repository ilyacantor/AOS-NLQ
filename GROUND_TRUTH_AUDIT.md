# Ground Truth Audit: DCL vs NLQ Endpoint Accuracy

## Critical Finding

**The test harness (`test_30_ground_truth.py`) tests the DCL data layer directly — NOT the NLQ natural language endpoint that users actually interact with.**

- **DCL endpoint** (`POST /api/dcl/query`): Receives pre-parsed structured JSON like `{"metric": "arr", "persona": "cfo"}` — **bypasses all NLQ parsing**
- **NLQ endpoint** (`POST /api/v1/query`): Receives natural language like `"What is our current ARR?"` — **what users actually type**

The 30/30 score is meaningless for user experience. It proves the data exists, not that the app can answer questions.

---

## DCL Layer (What the Test Harness Tests): 30/30 PASS

All 30 structured queries return correct data. This is not in dispute.

---

## NLQ Layer (What Users Actually Experience): 13/30 PASS, 17/30 FAIL

| # | Persona | Question | Expected | NLQ Result | Status |
|---|---------|----------|----------|------------|--------|
| Q01 | CFO | What is our current ARR? | 47.5 | `value: 47.5`, answer: "Arr for 2026-Q4 is $47.5M" | **PASS** |
| Q02 | CFO | Show revenue by region | AMER:25, EMEA:15, APAC:10 | Correct breakdown returned | **PASS** |
| Q03 | CRO | What is our win rate? | 45.5 | `value: 45.5`, answer: "Win Rate for 2026-Q4 is 45.5%" | **PASS** |
| Q04 | CRO | Which customer has the highest churn risk? | RetailMax, 72 | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q05 | CTO | What is our current uptime? | 99.82 | `value: 99.82`, answer: "Uptime Pct for 2026-Q4 is 99.8%" | **PASS** |
| Q06 | CTO | What is MTTR for P1 incidents? | 1.5 | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q07 | CHRO | What is our current headcount? | 430 | `value: 430`, answer: "Headcount for 2026-Q4 is 430" | **PASS** |
| Q08 | CHRO | What is our attrition rate? | 1.2 | `value: 1.2`, answer: "Attrition Rate for 2026-Q4 is 1.2%" | **PASS** |
| Q09 | COO | How many data sources are connected? | 27 | "No live ingest data is currently available" | **FAIL** |
| Q10 | COO | Which source system has the most ingested rows? | Zendesk, 139200 | "No live ingest data is currently available" | **FAIL** |
| Q11 | CFO | What is our gross margin? | 67.0 | `value: 67.0`, answer: "Gross Margin for 2026-Q4 is 67.0%" | **PASS** |
| Q12 | CFO | Show revenue by segment | Ent:27.5, MM:15, SMB:7.5 | Correct breakdown returned | **PASS** |
| Q13 | CFO | What is DSO by segment? | Ent:49, MM:38, SMB:25 | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q14 | CFO | Which product has the highest gross margin? | Enterprise, 21.44 | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q15 | CFO | What is our cloud spend by category? | Compute:0.376, ... | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q16 | CRO | Show pipeline by stage | Lead:28.75, Qual:43.12, ... | Correct breakdown returned | **PASS** |
| Q17 | CRO | What is churn rate by segment? | Ent:4.0, MM:6.3, SMB:10.8 | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q18 | CRO | What is our NRR? | 121.5 | `value: 121.5`, answer: "Nrr for 2026-Q4 is 121.5%" | **PASS** |
| Q19 | CRO | Show NRR by cohort | 2022-H1:111.3, ... | Returns trend dashboard, NOT cohort breakdown | **FAIL** |
| Q20 | CRO | Which segment has the highest churn? | SMB, 10.8 | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q21 | CTO | What is deploy frequency by service? | Web App:6.4, ... | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q22 | CTO | Show uptime by service | Auth:99.999, ... | Returns uptime KPI dashboard, NOT service breakdown | **FAIL** |
| Q23 | CTO | Which service deploys the most? | Web App, 6.4 | Returns "Auth Service" with slo_attainment 99.9 — **WRONG METRIC** | **FAIL** |
| Q24 | CTO | What is SLA compliance by team? | Frontend:99.5, ... | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q25 | CTO | Which team has the lowest SLA compliance? | Data, 95.3 | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q26 | CHRO | What is headcount by department? | Eng:145, Sales:80, ... | Correct breakdown returned | **PASS** |
| Q27 | CHRO | What is our engagement score? | 86.0 | `value: 86`, answer: "Engagement Score for 2026-Q4 is 86" | **PASS** |
| Q28 | CHRO | What is our offer acceptance rate? | 93.0 | `value: 93`, answer: "Offer Acceptance Rate for 2026-Q4 is 93" | **PASS** |
| Q29 | COO | What is throughput by team? | Frontend:110, ... | `CONFIG_ERROR: ANTHROPIC_API_KEY not configured` | **FAIL** |
| Q30 | COO | How many total rows have been ingested? | 589120 | "No live ingest data is currently available" | **FAIL** |

---

## Failure Breakdown

### Category 1: CONFIG_ERROR — ANTHROPIC_API_KEY not configured (11 failures)
**Q04, Q06, Q13, Q14, Q15, Q17, Q20, Q21, Q24, Q25, Q29**

These questions fall through the free Tier-1 synonym matching and require the LLM (Claude) to parse the intent. Without ANTHROPIC_API_KEY, they fail completely.

### Category 2: Ingest queries not routed (3 failures)
**Q09, Q10, Q30**

The NLQ endpoint returns "No live ingest data is currently available" instead of routing to the `/api/dcl/ingest/*` endpoints that have the data.

### Category 3: Wrong metric/wrong response type (3 failures)
**Q19, Q22, Q23**

- **Q19** "Show NRR by cohort" → Returns a trend dashboard (quarterly timeline), not the cohort breakdown (2022-H1, 2023-H1, etc.)
- **Q22** "Show uptime by service" → Returns a KPI+trend dashboard for overall uptime, not the per-service breakdown
- **Q23** "Which service deploys the most?" → Returns **Auth Service / slo_attainment 99.9%** instead of **Web App / deploy_frequency 6.4** — completely wrong metric

---

## Raw API Evidence

### Q04 — NLQ returns CONFIG_ERROR (DCL returns correct data)

**DCL (what test hits):**
```json
POST /api/dcl/query {"metric": "churn_risk", "dimensions": ["customer"], "order_by": "desc", "limit": 1, "persona": "cro"}
→ {"data": [{"customer": "RetailMax", "value": 72}]}
```

**NLQ (what user types):**
```json
POST /api/v1/query {"question": "Which customer has the highest churn risk?"}
→ {"success": false, "error_code": "CONFIG_ERROR", "error_message": "ANTHROPIC_API_KEY not configured"}
```

### Q23 — NLQ returns WRONG METRIC

**DCL (what test hits):**
```json
POST /api/dcl/query {"metric": "deploy_frequency", "dimensions": ["service"], "order_by": "desc", "limit": 1, "persona": "cto"}
→ {"data": [{"service": "Web App", "value": 6.4}]}
```

**NLQ (what user types):**
```json
POST /api/v1/query {"question": "Which service deploys the most?"}
→ {"answer": "**Auth Service** is the top service with 99.9% slo attainment.", "value": 99.9, "resolved_metric": "slo_attainment"}
```
Expected: Web App / deploy_frequency / 6.4. Got: Auth Service / slo_attainment / 99.9. **Completely wrong.**

### Q19 — NLQ returns trend instead of cohort breakdown

**DCL (what test hits):**
```json
POST /api/dcl/query {"metric": "nrr", "dimensions": ["cohort"], "persona": "cro"}
→ {"data": [{"cohort": "2022-H1", "value": 111.3}, {"cohort": "2023-H1", "value": 118.3}, {"cohort": "2024-H1", "value": 123.3}, {"cohort": "2025-H1", "value": 127.3}]}
```

**NLQ (what user types):**
```json
POST /api/v1/query {"question": "Show NRR by cohort"}
→ Returns quarterly trend data [114, 114.5, 115, ...] — NOT cohort breakdown
```

---

## Summary

| Layer | Score | What It Proves |
|-------|-------|----------------|
| DCL (structured queries) | **30/30** | Data exists and is correct |
| NLQ (natural language) | **13/30** | 43% of user questions answered correctly |

**The test harness gives a false sense of security by testing the data layer, not the user-facing NLQ layer.**
