# NLQ Live Mode — Structural Test Results

> Generated: 2026-03-10 17:12:05
> Endpoint: `POST http://127.0.0.1:8005/api/v1/query` with `data_mode=live`
> Validators: structural shape only (not numeric accuracy)

## Summary: 12/30 passed (40%)

| Shape | Pass | Total |
|-------|------|-------|
| POINT | 8 | 10 |
| BREAKDOWN | 2 | 12 |
| RANKING | 0 | 5 |
| INGEST_STATUS | 2 | 3 |

## Detailed Results

| # | Question | Shape | Result | Answer (excerpt) | data_source | Failure Reason |
|---|----------|-------|--------|------------------|-------------|----------------|
| Q01 | What is our current ARR? | POINT | PASS | Arr for 2026-Q1 is $0.0M | live | — |
| Q03 | What is our win rate? | POINT | PASS | Win Rate Pct for 2026-Q1 is 35.6% | live | — |
| Q05 | What is our current uptime? | POINT | PASS | Uptime for 2026-Q1 is 0.0% | live | — |
| Q06 | What is MTTR for P1 incidents? | POINT | **FAIL** | I'm stumped! But I can definitely help with: • Financial metrics (revenue, margi | — | NO_NUMERIC_VALUE (answer='I'm stumped! But I can definitely help with:
• Financial metrics (revenue, margi') |
| Q07 | What is our current headcount? | POINT | PASS | Headcount for 2026-Q1 is 32041.0 | live | — |
| Q08 | What is our attrition rate? | POINT | PASS | Attrition Rate Pct for 2026-Q1 is 13.4% | live | — |
| Q11 | What is our gross margin? | POINT | PASS | Gross Margin for 2026-Q1 is 39.6% | live | — |
| Q18 | What is our NRR? | POINT | PASS | Nrr for 2026-Q1 is 0.0% | live | — |
| Q27 | What is our engagement score? | POINT | PASS | Employee Engagement for 2026-Q1 is 0.0 | live | — |
| Q28 | What is our offer acceptance rate? | POINT | **FAIL** | I recognize **Offer Acceptance Rate Pct** (Percentage of job offers accepted), b | — | NO_NUMERIC_VALUE (answer='I recognize **Offer Acceptance Rate Pct** (Percentage of job offers accepted), b') |
| Q02 | Show revenue by region | BREAKDOWN | PASS | Here's revenue by region | live | — |
| Q12 | Show revenue by segment | BREAKDOWN | **FAIL** | Revenue by segment resolved via graph resolution. | dcl | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q13 | What is DSO by segment? | BREAKDOWN | **FAIL** | No data available for dso by segment. Try breaking down by: customer, segment, r | — | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q15 | What is our cloud spend by category? | BREAKDOWN | PASS | Here's cloud spend by resource_type | live | — |
| Q16 | Show pipeline by stage | BREAKDOWN | **FAIL** | No data available for pipeline by stage. Try breaking down by: rep, stage, regio | — | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q17 | What is churn rate by segment? | BREAKDOWN | **FAIL** | No data available for churn rate pct by segment. Try breaking down by: segment,  | — | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q19 | Show NRR by cohort | BREAKDOWN | **FAIL** | No data available for nrr by cohort. Try breaking down by: segment, region, coho | — | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q21 | What is deploy frequency by service? | BREAKDOWN | **FAIL** | No data available for deploy frequency by service. Try breaking down by: service | — | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q22 | Show uptime by service | BREAKDOWN | **FAIL** | No data available for uptime pct by service. Try breaking down by: service. | — | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q24 | What is SLA compliance by team? | BREAKDOWN | **FAIL** | No data available for sla compliance pct by team. Try breaking down by: team, ti | — | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q26 | What is headcount by department? | BREAKDOWN | **FAIL** | Headcount by department resolved via graph resolution. | dcl | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q29 | What is throughput by team? | BREAKDOWN | **FAIL** | No data available for throughput by team. Try breaking down by: team, work_type, | — | NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0) |
| Q04 | Which customer has the highest churn risk? | RANKING | **FAIL** | Churn Rate data ranked by customer is not available in the current data connecti | — | ENTITY_OK (Churn Rate) but NO_VALUE (answer='Churn Rate data ranked by customer is not available in the current data connection. This ranking req') |
| Q14 | Which product has the highest gross margin? | RANKING | **FAIL** | Gross Margin data ranked by product is not available in the current data connect | — | ENTITY_OK (Gross Margin) but NO_VALUE (answer='Gross Margin data ranked by product is not available in the current data connection. This ranking re') |
| Q20 | Which segment has the highest churn? | RANKING | **FAIL** | Churn Rate data ranked by segment is not available in the current data connectio | — | ENTITY_OK (Churn Rate) but NO_VALUE (answer='Churn Rate data ranked by segment is not available in the current data connection. This ranking requ') |
| Q23 | Which service deploys the most? | RANKING | **FAIL** | Slo Attainment data ranked by service is not available in the current data conne | — | ENTITY_OK (Slo Attainment) but NO_VALUE (answer='Slo Attainment data ranked by service is not available in the current data connection. This ranking ') |
| Q25 | Which team has the lowest SLA compliance? | RANKING | **FAIL** | Slo Attainment data ranked by team is not available in the current data connecti | — | ENTITY_OK (Slo Attainment) but NO_VALUE (answer='Slo Attainment data ranked by team is not available in the current data connection. This ranking req') |
| Q09 | How many data sources are connected? | INGEST_STATUS | PASS | There are 91 source systems connected: adp, airtable, alllabs inc, allmind inc,  | — | — |
| Q10 | Which source system has the most ingested rows? | INGEST_STATUS | **FAIL** | Quota Attainment data ranked by service is not available in the current data con | — | INGEST_REJECTION: 'not available' found in answer |
| Q30 | How many total rows have been ingested? | INGEST_STATUS | PASS | There are 245,982 rows ingested across all sources. | — | — |

## Failure Analysis

### Q06 — What is MTTR for P1 incidents?
- **Shape**: POINT
- **Reason**: `NO_NUMERIC_VALUE (answer='I'm stumped! But I can definitely help with:
• Financial metrics (revenue, margi')`
- **data_source**: `n/a`
- **answer**: I'm stumped! But I can definitely help with:
• Financial metrics (revenue, margin, profit)
• Sales metrics (pipeline, bo
- **value**: `None`
- **resolved_metric**: `mttr_p1_hours`
- **parsed_intent**: `POINT_QUERY`

### Q28 — What is our offer acceptance rate?
- **Shape**: POINT
- **Reason**: `NO_NUMERIC_VALUE (answer='I recognize **Offer Acceptance Rate Pct** (Percentage of job offers accepted), b')`
- **data_source**: `n/a`
- **answer**: I recognize **Offer Acceptance Rate Pct** (Percentage of job offers accepted), but I don't have data for it right now. T
- **value**: `None`
- **resolved_metric**: `offer_acceptance_rate_pct`
- **parsed_intent**: `POINT_QUERY`

### Q12 — Show revenue by segment
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `dcl`
- **answer**: Revenue by segment resolved via graph resolution.
- **value**: `None`
- **resolved_metric**: `revenue`
- **parsed_intent**: `GRAPH_RESOLUTION`

### Q13 — What is DSO by segment?
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `n/a`
- **answer**: No data available for dso by segment. Try breaking down by: customer, segment, region.
- **value**: `None`
- **resolved_metric**: `dso`
- **parsed_intent**: `DATA_NOT_AVAILABLE`

### Q16 — Show pipeline by stage
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `n/a`
- **answer**: No data available for pipeline by stage. Try breaking down by: rep, stage, region, segment.
- **value**: `None`
- **resolved_metric**: `pipeline`
- **parsed_intent**: `DATA_NOT_AVAILABLE`

### Q17 — What is churn rate by segment?
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `n/a`
- **answer**: No data available for churn rate pct by segment. Try breaking down by: segment, region, cohort.
- **value**: `None`
- **resolved_metric**: `churn_rate_pct`
- **parsed_intent**: `DATA_NOT_AVAILABLE`

### Q19 — Show NRR by cohort
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `n/a`
- **answer**: No data available for nrr by cohort. Try breaking down by: segment, region, cohort.
- **value**: `None`
- **resolved_metric**: `nrr`
- **parsed_intent**: `DATA_NOT_AVAILABLE`

### Q21 — What is deploy frequency by service?
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `n/a`
- **answer**: No data available for deploy frequency by service. Try breaking down by: service, team, environment.
- **value**: `None`
- **resolved_metric**: `deploy_frequency`
- **parsed_intent**: `DATA_NOT_AVAILABLE`

### Q22 — Show uptime by service
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `n/a`
- **answer**: No data available for uptime pct by service. Try breaking down by: service.
- **value**: `None`
- **resolved_metric**: `uptime_pct`
- **parsed_intent**: `DATA_NOT_AVAILABLE`

### Q24 — What is SLA compliance by team?
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `n/a`
- **answer**: No data available for sla compliance pct by team. Try breaking down by: team, tier, work_type.
- **value**: `None`
- **resolved_metric**: `sla_compliance_pct`
- **parsed_intent**: `DATA_NOT_AVAILABLE`

### Q26 — What is headcount by department?
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `dcl`
- **answer**: Headcount by department resolved via graph resolution.
- **value**: `None`
- **resolved_metric**: `headcount`
- **parsed_intent**: `GRAPH_RESOLUTION`

### Q29 — What is throughput by team?
- **Shape**: BREAKDOWN
- **Reason**: `NO_BREAKDOWN_DATA (dashboard_data=null, related_metrics_count=0)`
- **data_source**: `n/a`
- **answer**: No data available for throughput by team. Try breaking down by: team, work_type, priority.
- **value**: `None`
- **resolved_metric**: `throughput`
- **parsed_intent**: `DATA_NOT_AVAILABLE`

### Q04 — Which customer has the highest churn risk?
- **Shape**: RANKING
- **Reason**: `ENTITY_OK (Churn Rate) but NO_VALUE (answer='Churn Rate data ranked by customer is not available in the current data connection. This ranking req')`
- **data_source**: `n/a`
- **answer**: Churn Rate data ranked by customer is not available in the current data connection. This ranking requires dimensional da
- **value**: `None`
- **resolved_metric**: `churn_rate_pct`
- **parsed_intent**: `POINT_QUERY`

### Q14 — Which product has the highest gross margin?
- **Shape**: RANKING
- **Reason**: `ENTITY_OK (Gross Margin) but NO_VALUE (answer='Gross Margin data ranked by product is not available in the current data connection. This ranking re')`
- **data_source**: `n/a`
- **answer**: Gross Margin data ranked by product is not available in the current data connection. This ranking requires dimensional d
- **value**: `None`
- **resolved_metric**: `gross_margin_pct`
- **parsed_intent**: `POINT_QUERY`

### Q20 — Which segment has the highest churn?
- **Shape**: RANKING
- **Reason**: `ENTITY_OK (Churn Rate) but NO_VALUE (answer='Churn Rate data ranked by segment is not available in the current data connection. This ranking requ')`
- **data_source**: `n/a`
- **answer**: Churn Rate data ranked by segment is not available in the current data connection. This ranking requires dimensional dat
- **value**: `None`
- **resolved_metric**: `churn_rate_pct`
- **parsed_intent**: `POINT_QUERY`

### Q23 — Which service deploys the most?
- **Shape**: RANKING
- **Reason**: `ENTITY_OK (Slo Attainment) but NO_VALUE (answer='Slo Attainment data ranked by service is not available in the current data connection. This ranking ')`
- **data_source**: `n/a`
- **answer**: Slo Attainment data ranked by service is not available in the current data connection. This ranking requires dimensional
- **value**: `None`
- **resolved_metric**: `slo_attainment_pct`
- **parsed_intent**: `POINT_QUERY`

### Q25 — Which team has the lowest SLA compliance?
- **Shape**: RANKING
- **Reason**: `ENTITY_OK (Slo Attainment) but NO_VALUE (answer='Slo Attainment data ranked by team is not available in the current data connection. This ranking req')`
- **data_source**: `n/a`
- **answer**: Slo Attainment data ranked by team is not available in the current data connection. This ranking requires dimensional da
- **value**: `None`
- **resolved_metric**: `slo_attainment_pct`
- **parsed_intent**: `POINT_QUERY`

### Q10 — Which source system has the most ingested rows?
- **Shape**: INGEST_STATUS
- **Reason**: `INGEST_REJECTION: 'not available' found in answer`
- **data_source**: `n/a`
- **answer**: Quota Attainment data ranked by service is not available in the current data connection. This ranking requires dimension
- **value**: `None`
- **resolved_metric**: `quota_attainment_pct`
- **parsed_intent**: `POINT_QUERY`

