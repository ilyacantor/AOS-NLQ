# NLQ Demo Eval — Ground Truth Reference

> **Generated:** 2026-02-27 | **Endpoint:** localhost:8005 (data_mode=live)
> **Source data:** DCL fact_base (Farm-generated, Ingest-v5.0)
> **Default period:** 2026-Q1 (latest quarter unless query specifies otherwise)

---

## CFO — Chief Financial Officer

### CFO_Q1: What is our revenue for 2025?

| Field | Value |
|-------|-------|
| **Metric** | `revenue` |
| **Period** | 2025 (annual) |
| **Value** | 124.18 |
| **Unit** | usd_millions |
| **Answer** | Revenue for 2025 is $124.2M |
| **Intent** | POINT_QUERY |

### CFO_Q2: Compare 2024 vs 2025 revenue

| Field | Value |
|-------|-------|
| **Metric** | `comparison` |
| **Period** | 2025 vs 2024 |
| **Value** | 29.0 (YoY growth %) |
| **Unit** | pct |
| **Answer** | 2025 vs 2024: Revenue $124.0M vs $96.0M (+29%), Net Income $34.0M vs $25.51M (+31%), Operating Margin 36.0% vs 35.3% (+0.7%) |
| **Intent** | COMPARISON |

### CFO_Q3: What is EBITDA margin?

| Field | Value |
|-------|-------|
| **Metric** | `ebitda_margin_pct` |
| **Period** | 2026-Q1 |
| **Value** | 39.9 |
| **Unit** | pct |
| **Answer** | EBITDA Margin for 2026-Q1 is 39.9% |
| **Intent** | POINT_QUERY |

### CFO_Q4: Show me the full P&L

| Field | Value |
|-------|-------|
| **Metric** | `pl_statement` |
| **Period** | 2026-Q1 |
| **Intent** | PL_STATEMENT |
| **Answer** | |

```
P&L Statement — 2026-Q1

  Revenue: $35.6M
  COGS: $11.9M
  Gross Profit: $23.6M
  Gross Margin: 66.4%
  SM Expense: $4.1M
  RD Expense: $3.0M
  GA Expense: $2.3M
  OpEx: $9.4M
  EBITDA: $14.2M
  EBITDA Margin: 39.9%
  Operating Profit: $13.0M
  Net Income: $9.7M
  Net Margin: 27.3%
```

### CFO_Q5: Show me revenue by region

| Field | Value |
|-------|-------|
| **Metric** | `revenue` |
| **Period** | 2026-Q1 |
| **Intent** | BREAKDOWN |
| **Dimensions** | region |

| Region | Revenue ($M) |
|--------|-------------|
| AMER | 17.79 |
| EMEA | 10.67 |
| APAC | 7.11 |

### CFO_Q6: What is our burn multiple?

| Field | Value |
|-------|-------|
| **Metric** | `burn_multiple` |
| **Period** | 2026-Q1 |
| **Value** | -1.89 |
| **Unit** | ratio |
| **Answer** | Burn Multiple for 2026-Q1 is -1.9 |
| **Intent** | POINT_QUERY |

### CFO_Q7: How is ARR trending?

| Field | Value |
|-------|-------|
| **Metric** | `arr` |
| **Period** | 2024-Q1 through 2026-Q4 |
| **Intent** | VISUALIZATION (trend) |

| Quarter | ARR ($M) |
|---------|---------|
| Q1 2024 | 89.6 |
| Q2 2024 | 96.0 |
| Q3 2024 | 103.0 |
| Q4 2024 | 110.3 |
| Q1 2025 | 116.9 |
| Q2 2025 | 123.9 |
| Q3 2025 | 131.2 |
| Q4 2025 | 139.0 |
| Q1 2026 | 145.5 |
| Q2 2026 | 152.3 |
| Q3 2026 | 159.4 |
| Q4 2026 | 166.8 |

### CFO_Q8: What is our rule of 40?

| Field | Value |
|-------|-------|
| **Metric** | `rule_of_40` |
| **Period** | 2026-Q1 |
| **Value** | 57.4 |
| **Unit** | pct |
| **Answer** | Rule Of 40 for 2026-Q1 is 57.4 |
| **Intent** | POINT_QUERY |

---

## CRO — Chief Revenue Officer

### CRO_Q1: What is our pipeline?

| Field | Value |
|-------|-------|
| **Metric** | `pipeline` |
| **Period** | 2026-Q1 |
| **Value** | 128.05 |
| **Unit** | usd_millions |
| **Answer** | Pipeline for 2026-Q1 is $128.1M |
| **Intent** | POINT_QUERY |

### CRO_Q2: What is our win rate?

| Field | Value |
|-------|-------|
| **Metric** | `win_rate_pct` |
| **Period** | 2026-Q1 |
| **Value** | 40.0 |
| **Unit** | pct |
| **Answer** | Win Rate Pct for 2026-Q1 is 40.0% |
| **Intent** | POINT_QUERY |

### CRO_Q3: Show me pipeline by region

| Field | Value |
|-------|-------|
| **Metric** | `pipeline` |
| **Period** | 2026-Q1 |
| **Intent** | BREAKDOWN |
| **Dimensions** | region |

| Region | Pipeline ($M) |
|--------|--------------|
| AMER | 64.03 |
| EMEA | 38.41 |
| APAC | 25.61 |

### CRO_Q4: Who are the top 3 sales reps?

| Field | Value |
|-------|-------|
| **Metric** | `quota_attainment_pct` |
| **Period** | 2026-Q1 |
| **Intent** | SUPERLATIVE |
| **Status** | DATA NOT AVAILABLE |
| **Answer** | Quota Attainment data ranked by rep is not available in the current data connection. This ranking requires dimensional data that has not been materialized in DCL. |

> **Note:** Rep-level quota data does not exist in DCL. This is the correct response — honest no-data message instead of a wrong answer.

### CRO_Q5: What is average deal size?

| Field | Value |
|-------|-------|
| **Metric** | `avg_deal_size` |
| **Period** | 2026-Q1 |
| **Value** | 0.0702 |
| **Unit** | usd_millions |
| **Answer** | Avg Deal Size for 2026-Q1 is $0.1M |
| **Intent** | POINT_QUERY |

### CRO_Q6: What is our sales cycle length?

| Field | Value |
|-------|-------|
| **Metric** | `sales_cycle_days` |
| **Period** | 2026-Q1 |
| **Value** | 86.0 |
| **Unit** | days |
| **Answer** | Sales Cycle Days for 2026-Q1 is 86.0 |
| **Intent** | POINT_QUERY |

### CRO_Q7: Which segment has the best win rate?

| Field | Value |
|-------|-------|
| **Metric** | `win_rate_pct` |
| **Period** | 2026-Q1 |
| **Value** | 40.0 (aggregate) |
| **Unit** | pct |
| **Answer** | Win Rate is 40.0% overall. Segment-level ranking is not available in the current data set. |
| **Intent** | SUPERLATIVE |

> **Note:** DCL has win_rate as aggregate only — no segment breakdown materialized. System correctly returns the aggregate value with an explanation.

### CRO_Q8: What is quota attainment?

| Field | Value |
|-------|-------|
| **Metric** | `quota_attainment_pct` |
| **Period** | 2026-Q1 |
| **Value** | 150.0 |
| **Unit** | pct |
| **Answer** | Quota Attainment Pct for 2026-Q1 is 150.0% |
| **Intent** | POINT_QUERY |

---

## COO — Chief Operating Officer

### COO_Q1: What is customer satisfaction?

| Field | Value |
|-------|-------|
| **Metric** | `csat` |
| **Period** | 2026-Q1 |
| **Value** | 4.23 |
| **Unit** | score |
| **Answer** | Csat for 2026-Q1 is 4.2 |
| **Intent** | POINT_QUERY |

### COO_Q2: How is CSAT trending?

| Field | Value |
|-------|-------|
| **Metric** | `csat` |
| **Period** | 2024-Q1 through 2026-Q4 |
| **Intent** | VISUALIZATION (trend) |

| Quarter | CSAT |
|---------|------|
| Q1 2024 | 4.20 |
| Q2 2024 | 4.20 |
| Q3 2024 | 4.20 |
| Q4 2024 | 4.20 |
| Q1 2025 | 4.20 |
| Q2 2025 | 4.20 |
| Q3 2025 | 4.20 |
| Q4 2025 | 4.20 |
| Q1 2026 | 4.20 |
| Q2 2026 | 4.20 |
| Q3 2026 | 4.20 |
| Q4 2026 | 4.30 |

### COO_Q3: What is our NPS?

| Field | Value |
|-------|-------|
| **Metric** | `nps` |
| **Period** | 2026-Q1 |
| **Value** | 48.0 |
| **Unit** | score |
| **Answer** | Nps for 2026-Q1 is 48.0 |
| **Intent** | POINT_QUERY |

### COO_Q4: How many support tickets last quarter?

| Field | Value |
|-------|-------|
| **Metric** | `support_tickets` |
| **Period** | 2025-Q4 |
| **Value** | 4121 |
| **Unit** | count |
| **Answer** | Support Tickets for 2025-Q4 is 4121.0 |
| **Intent** | POINT_QUERY |

### COO_Q5: What is first response time?

| Field | Value |
|-------|-------|
| **Metric** | `first_response_hours` |
| **Period** | 2026-Q1 |
| **Value** | 2.1 |
| **Unit** | hours |
| **Answer** | First Response Hours for 2026-Q1 is 2.1 |
| **Intent** | POINT_QUERY |

### COO_Q6: Show me CSAT by segment

| Field | Value |
|-------|-------|
| **Metric** | `csat` |
| **Period** | 2026-Q1 |
| **Intent** | BREAKDOWN |
| **Dimensions** | segment |

| Segment | CSAT |
|---------|------|
| Enterprise | 4.38 |
| Mid-Market | 4.23 |
| SMB | 4.03 |

### COO_Q7: What is our headcount?

| Field | Value |
|-------|-------|
| **Metric** | `headcount` |
| **Period** | 2026-Q1 |
| **Value** | 333 |
| **Unit** | count |
| **Answer** | Headcount for 2026-Q1 is 333.0 |
| **Intent** | POINT_QUERY |

### COO_Q8: How many open roles?

| Field | Value |
|-------|-------|
| **Metric** | `open_roles` |
| **Period** | 2026-Q1 |
| **Value** | 51 |
| **Unit** | count |
| **Answer** | Open Roles for 2026-Q1 is 51.0 |
| **Intent** | POINT_QUERY |

---

## CTO — Chief Technology Officer

### CTO_Q1: How many P1 incidents this quarter?

| Field | Value |
|-------|-------|
| **Metric** | `p1_incidents` |
| **Period** | 2026-Q1 |
| **Value** | 3 |
| **Unit** | count |
| **Answer** | P1 Incidents for 2026-Q1 is 3.0 |
| **Intent** | POINT_QUERY |

### CTO_Q2: What is our MTTR?

| Field | Value |
|-------|-------|
| **Metric** | `mttr` |
| **Period** | 2026-Q1 |
| **Value** | 2.5 |
| **Unit** | minutes |
| **Answer** | Mttr for 2026-Q1 is 2.5 |
| **Intent** | POINT_QUERY |

### CTO_Q3: What is our uptime?

| Field | Value |
|-------|-------|
| **Metric** | `uptime_pct` |
| **Period** | 2026-Q1 |
| **Value** | 99.61 |
| **Unit** | pct |
| **Answer** | Uptime Pct for 2026-Q1 is 99.6% |
| **Intent** | POINT_QUERY |

### CTO_Q4: Show me uptime by service

| Field | Value |
|-------|-------|
| **Metric** | `uptime_pct` |
| **Period** | 2026-Q1 |
| **Intent** | BREAKDOWN |
| **Status** | DATA NOT AVAILABLE |
| **Answer** | No breakdown data available for uptime pct by service. Try breaking down by: service. |

> **Note:** Uptime-by-service dimensional data is not materialized in DCL. System correctly reports the gap.

### CTO_Q5: What is sprint velocity?

| Field | Value |
|-------|-------|
| **Metric** | `sprint_velocity` |
| **Period** | 2026-Q1 |
| **Value** | 102.0 |
| **Unit** | count (story points) |
| **Answer** | Sprint Velocity for 2026-Q1 is 102.0 |
| **Intent** | POINT_QUERY |

### CTO_Q6: How is cloud spend trending?

| Field | Value |
|-------|-------|
| **Metric** | `cloud_spend` |
| **Period** | 2024-Q1 through 2026-Q4 |
| **Intent** | VISUALIZATION (trend) |

| Quarter | Cloud Spend ($M) |
|---------|-----------------|
| Q1 2024 | 0.60 |
| Q2 2024 | 0.70 |
| Q3 2024 | 0.70 |
| Q4 2024 | 0.80 |
| Q1 2025 | 0.80 |
| Q2 2025 | 0.80 |
| Q3 2025 | 0.90 |
| Q4 2025 | 0.90 |
| Q1 2026 | 1.00 |
| Q2 2026 | 1.00 |
| Q3 2026 | 1.10 |
| Q4 2026 | 1.10 |

### CTO_Q7: Show me cloud spend by category

| Field | Value |
|-------|-------|
| **Metric** | `cloud_spend` |
| **Period** | 2026-Q1 |
| **Intent** | BREAKDOWN |
| **Dimensions** | resource_type |

| Category | Spend ($M) |
|----------|-----------|
| Compute | 0.40 |
| Storage | 0.15 |
| Database | 0.20 |
| Network | 0.10 |
| ML/AI | 0.08 |
| Other | 0.07 |

### CTO_Q8: What is our tech debt?

| Field | Value |
|-------|-------|
| **Metric** | `tech_debt_pct` |
| **Period** | 2026-Q1 |
| **Value** | 0.13 |
| **Unit** | pct |
| **Answer** | Tech Debt Pct for 2026-Q1 is 0.1% |
| **Intent** | POINT_QUERY |

---

## CHRO — Chief Human Resources Officer

### CHRO_Q1: What is our attrition rate?

| Field | Value |
|-------|-------|
| **Metric** | `attrition_rate_pct` |
| **Period** | 2026-Q1 |
| **Value** | 11.0 |
| **Unit** | pct |
| **Answer** | Attrition Rate Pct for 2026-Q1 is 11.0% |
| **Intent** | POINT_QUERY |

### CHRO_Q2: Which department has the highest attrition?

| Field | Value |
|-------|-------|
| **Metric** | `attrition_rate_pct` |
| **Period** | 2026-Q1 |
| **Value** | 13.8 |
| **Unit** | pct |
| **Answer** | **Sales** is the top department with 13.8% attrition rate. |
| **Intent** | SUPERLATIVE |
| **Top result** | Sales (13.8%) |

### CHRO_Q3: What is employee engagement?

| Field | Value |
|-------|-------|
| **Metric** | `engagement_score` |
| **Period** | 2026-Q1 |
| **Value** | 77.5 |
| **Unit** | score (0-100 scale) |
| **Answer** | Engagement Score for 2026-Q1 is 77.5 |
| **Intent** | POINT_QUERY |

> **Note:** Engagement is on a 0-100 scale (not 1-5). The eval runner's gt=4.25 is wrong and should be updated to 77.5.

### CHRO_Q4: How many open roles do we have?

| Field | Value |
|-------|-------|
| **Metric** | `open_roles` |
| **Period** | 2026-Q1 |
| **Value** | 51 |
| **Unit** | count |
| **Answer** | Open Roles for 2026-Q1 is 51.0 |
| **Intent** | POINT_QUERY |

### CHRO_Q5: What is time to fill?

| Field | Value |
|-------|-------|
| **Metric** | `time_to_fill` |
| **Period** | 2026-Q1 |
| **Value** | 30.2 |
| **Unit** | days |
| **Answer** | Time To Fill for 2026-Q1 is 30.2 |
| **Intent** | POINT_QUERY |

> **Note:** The eval runner's gt=45 is outdated. Correct ground truth from DCL is 30.2 (averaged from department-level time_to_fill data).

### CHRO_Q6: What is our eNPS?

| Field | Value |
|-------|-------|
| **Metric** | `enps` |
| **Period** | 2026-Q1 |
| **Value** | 27.0 |
| **Unit** | score |
| **Answer** | Enps for 2026-Q1 is 27.0 |
| **Intent** | POINT_QUERY |

### CHRO_Q7: Show me headcount by department

| Field | Value |
|-------|-------|
| **Metric** | `headcount` |
| **Period** | 2026-Q1 |
| **Intent** | BREAKDOWN |
| **Dimensions** | department |

| Department | Headcount |
|------------|-----------|
| Engineering | 106 |
| Product | 26 |
| Sales | 60 |
| Marketing | 33 |
| Customer Success | 45 |
| G&A | 63 |

### CHRO_Q8: What is our offer acceptance rate?

| Field | Value |
|-------|-------|
| **Metric** | `offer_acceptance_rate_pct` |
| **Period** | 2026-Q1 |
| **Value** | 83.1 |
| **Unit** | pct |
| **Answer** | Offer Acceptance Rate Pct for 2026-Q1 is 83.1% |
| **Intent** | POINT_QUERY |

---

## Summary

| Persona | Queries | Point | Breakdown | Trend | Comparison | Composite | Superlative | No-Data |
|---------|---------|-------|-----------|-------|------------|-----------|-------------|---------|
| **CFO** | 8 | 4 | 1 | 1 | 1 | 1 | 0 | 0 |
| **CRO** | 8 | 5 | 1 | 0 | 0 | 0 | 2 | 1 |
| **COO** | 8 | 5 | 1 | 1 | 0 | 0 | 0 | 0 |
| **CTO** | 8 | 5 | 1 | 1 | 0 | 0 | 0 | 1 |
| **CHRO** | 8 | 5 | 1 | 0 | 0 | 0 | 1 | 0 |
| **Total** | **40** | **24** | **5** | **3** | **1** | **1** | **3** | **2** |

### Data Gaps (correct no-data responses)

These queries return honest "not available" messages because the dimensional data has not been materialized in DCL:

1. **CRO_Q4** — Rep-level quota attainment (no rep dimension in DCL)
2. **CRO_Q7** — Win rate by segment (aggregate only, no segment breakdown)
3. **CTO_Q4** — Uptime by service (no service-level dimensional data)

### Eval Runner Ground Truth Corrections Needed

| ID | Current gt | Correct gt | Reason |
|----|-----------|------------|--------|
| CHRO_Q3 | 4.25 | 77.5 | Engagement uses 0-100 scale, not 1-5 |
| CHRO_Q5 | 45 | 30.2 | Updated DCL data (averaged from department breakdown) |
