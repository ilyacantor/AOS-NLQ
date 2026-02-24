# NLQ Live Mode — Structural Test Results

> Generated: 2026-02-24 07:06:04
> Endpoint: `POST http://127.0.0.1:8000/api/v1/query` with `data_mode=live`
> Validators: structural shape only (not numeric accuracy)

## Summary: 30/30 passed (100%)

| Shape | Pass | Total |
|-------|------|-------|
| POINT | 10 | 10 |
| BREAKDOWN | 12 | 12 |
| RANKING | 5 | 5 |
| INGEST_STATUS | 3 | 3 |

## Detailed Results

| # | Question | Shape | Result | Answer (excerpt) | data_source | Failure Reason |
|---|----------|-------|--------|------------------|-------------|----------------|
| Q01 | What is our current ARR? | POINT | PASS | Arr for 2026-Q1 is $35.6M | live | — |
| Q03 | What is our win rate? | POINT | PASS | Win Rate for 2026-Q1 is 44.0% | dcl | — |
| Q05 | What is our current uptime? | POINT | PASS | Uptime Pct for 2026-Q1 is 99.8% | dcl | — |
| Q06 | What is MTTR for P1 incidents? | POINT | PASS | Mttr for 2026-Q1 is 1.8 | dcl | — |
| Q07 | What is our current headcount? | POINT | PASS | Headcount for 2026-Q1 is 385.0 | dcl | — |
| Q08 | What is our attrition rate? | POINT | PASS | Attrition Rate for 2026-Q1 is 1.3% | dcl | — |
| Q11 | What is our gross margin? | POINT | PASS | Gross Margin for 2026-Q1 is 145183.7% | live | — |
| Q18 | What is our NRR? | POINT | PASS | Nrr for 2026-Q1 is 120.0% | dcl | — |
| Q27 | What is our engagement score? | POINT | PASS | Engagement Score for 2026-Q1 is 83.0 | dcl | — |
| Q28 | What is our offer acceptance rate? | POINT | PASS | Offer Acceptance Rate for 2026-Q1 is 90.0 | dcl | — |
| Q02 | Show revenue by region | BREAKDOWN | PASS | Here's revenue by region | dcl | — |
| Q12 | Show revenue by segment | BREAKDOWN | PASS | Here's revenue by segment | dcl | — |
| Q13 | What is DSO by segment? | BREAKDOWN | PASS | Here's dso by segment | dcl | — |
| Q15 | What is our cloud spend by category? | BREAKDOWN | PASS | Here's cloud cost by resource_type | dcl | — |
| Q16 | Show pipeline by stage | BREAKDOWN | PASS | Here's pipeline by stage | dcl | — |
| Q17 | What is churn rate by segment? | BREAKDOWN | PASS | Here's gross churn pct by segment | dcl | — |
| Q19 | Show NRR by cohort | BREAKDOWN | PASS | Here's nrr by cohort | dcl | — |
| Q21 | What is deploy frequency by service? | BREAKDOWN | PASS | Here's deploy frequency by service | dcl | — |
| Q22 | Show uptime by service | BREAKDOWN | PASS | Here's uptime pct by service | dcl | — |
| Q24 | What is SLA compliance by team? | BREAKDOWN | PASS | Here's sla compliance by team | dcl | — |
| Q26 | What is headcount by department? | BREAKDOWN | PASS | Here's headcount by department | dcl | — |
| Q29 | What is throughput by team? | BREAKDOWN | PASS | Here's throughput by team | dcl | — |
| Q04 | Which customer has the highest churn risk? | RANKING | PASS | Churn Rate for 2026-Q1 is 6.5 | dcl | — |
| Q14 | Which product has the highest gross margin? | RANKING | PASS | **Unknown** is the top product with 20.58% gross margin pct. | — | — |
| Q20 | Which segment has the highest churn? | RANKING | PASS | **Unknown** is the top segment with 11.3% gross churn pct. | — | — |
| Q23 | Which service deploys the most? | RANKING | PASS | **Unknown** is the top service with 99.9% slo attainment. | — | — |
| Q25 | Which team has the lowest SLA compliance? | RANKING | PASS | Breakdown for 2026-Q1: Revenue: 35.57 | — | — |
| Q09 | How many data sources are connected? | INGEST_STATUS | PASS | There are 208 source systems connected: AAM, adp, allsoft inc, apigee, asana, at | — | — |
| Q10 | Which source system has the most ingested rows? | INGEST_STATUS | PASS | Live ingest status: 208 source systems connected (AAM, adp, allsoft inc, apigee, | — | — |
| Q30 | How many total rows have been ingested? | INGEST_STATUS | PASS | There are 258,161 rows ingested across all sources. | — | — |

