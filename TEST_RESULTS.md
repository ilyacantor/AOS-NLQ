# AOS-NLQ Test Results - Ground Truth Validation

**Test Date:** 2026-01-28
**Fact Base Version:** Multi-Persona v1.0

## Summary

All ground truth queries have been validated against the fact base. The data layer is **100% accurate**.

| Persona | Questions Tested | Passed | Failed |
|---------|------------------|--------|--------|
| CFO     | 11               | 11     | 0      |
| CRO     | 15               | 15     | 0      |
| COO     | 29               | 29     | 0      |
| CTO     | 33               | 33     | 0      |
| **Total** | **88**         | **88** | **0**  |

---

## CFO Questions - Ground Truth Validation

| ID | Question | Metric | Period | Expected | Actual | Status |
|----|----------|--------|--------|----------|--------|--------|
| F1 | What was revenue in 2024? | revenue | 2024 | $100.0M | $100.0M | ✓ |
| F2 | What was revenue in 2025? | revenue | 2025 | $150.0M | $150.0M | ✓ |
| F3 | What was gross margin % in 2025? | gross_margin_pct | 2025 | 65.0% | 65.0% | ✓ |
| F4 | What was operating margin % in 2025? | operating_margin_pct | 2025 | 35.0% | 35.0% | ✓ |
| F5 | What was COGS in 2025? | cogs | 2025 | $52.5M | $52.5M | ✓ |
| F6 | What was SG&A in 2025? | sga | 2025 | $45.0M | $45.0M | ✓ |
| F7 | What was cash in 2025? | cash | 2025 | $41.42M | $41.42M | ✓ |
| F8 | What was AR in 2025? | ar | 2025 | $20.71M | $20.71M | ✓ |
| F9 | What was Q4 2025 revenue? | revenue | 2025-Q4 | $42.0M | $42.0M | ✓ |
| F10 | What was gross profit Q4 2025? | gross_profit | 2025-Q4 | $27.3M | $27.3M | ✓ |
| F11 | What was net income in 2025? | net_income | 2025 | $28.13M | $28.13M | ✓ |

---

## CRO Questions - Ground Truth Validation

| ID | Question | Metric | Period | Expected | Actual | Status |
|----|----------|--------|--------|----------|--------|--------|
| C1 | What were total bookings in 2024? | bookings | 2024 | $115.0M | $115.0M | ✓ |
| C2 | What was ARR in 2025? | arr | 2025 | $142.5M | $142.5M | ✓ |
| C3 | What was new logo revenue in 2024? | new_logo_revenue | 2024 | $25.0M | $25.0M | ✓ |
| C4 | What was expansion revenue in 2025? | expansion_revenue | 2025 | $25.0M | $25.0M | ✓ |
| C5 | What was our win rate in 2024? | win_rate | 2024 | 40% | 40% | ✓ |
| C6 | What was the sales pipeline in 2025? | pipeline | 2025 | $431.25M | $431.25M | ✓ |
| C7 | How many customers in 2024? | customer_count | 2024 | 800 | 800 | ✓ |
| C8 | What was NRR in 2025? | nrr | 2025 | 118% | 118% | ✓ |
| C9 | What was gross churn in 2024? | gross_churn_pct | 2024 | 8% | 8% | ✓ |
| C10 | What was avg deal size in 2025? | avg_deal_size | 2025 | $0.15M | $0.15M | ✓ |
| C16 | What were Q4 2025 bookings? | bookings | 2025-Q4 | $55.725M | $55.725M | ✓ |
| C17 | What was win rate in Q3 2025? | win_rate | 2025-Q3 | 43% | 43% | ✓ |
| C18 | How many new logos in Q4 2025? | new_logos | 2025-Q4 | 55 | 55 | ✓ |
| C19 | What was Q2 2025 pipeline created? | pipeline | 2025-Q2 | $97.875M | $97.875M | ✓ |
| C20 | What were Q1 2025 bookings? | bookings | 2025-Q1 | $34.5M | $34.5M | ✓ |

---

## COO Questions - Ground Truth Validation

| ID | Question | Metric | Period | Expected | Actual | Status |
|----|----------|--------|--------|----------|--------|--------|
| O1 | What was total headcount in 2024? | headcount | 2024 | 250 | 250 | ✓ |
| O2 | What was total headcount in 2025? | headcount | 2025 | 350 | 350 | ✓ |
| O3 | What was engineering headcount in 2025? | engineering_headcount | 2025 | 115 | 115 | ✓ |
| O4 | What was sales headcount in 2024? | sales_headcount | 2024 | 45 | 45 | ✓ |
| O5 | What was G&A headcount in 2025? | ga_headcount | 2025 | 60 | 60 | ✓ |
| O6 | What was CS headcount in 2025? | cs_headcount | 2025 | 50 | 50 | ✓ |
| O7 | How many people in marketing 2025? | marketing_headcount | 2025 | 35 | 35 | ✓ |
| O8 | What was product headcount in 2025? | product_headcount | 2025 | 30 | 30 | ✓ |
| O11 | What was revenue per employee in 2024? | revenue_per_employee | 2024 | $0.4M | $0.4M | ✓ |
| O12 | What was revenue per employee in 2025? | revenue_per_employee | 2025 | $0.429M | $0.429M | ✓ |
| O13 | What was cost per employee in 2025? | cost_per_employee | 2025 | $0.175M | $0.175M | ✓ |
| O14 | What was magic number in 2025? | magic_number | 2025 | 0.85 | 0.85 | ✓ |
| O15 | What was CAC payback in 2024? | cac_payback_months | 2024 | 18 months | 18 months | ✓ |
| O16 | What was LTV/CAC in 2025? | ltv_cac | 2025 | 3.5x | 3.5x | ✓ |
| O17 | What was burn multiple in 2025? | burn_multiple | 2025 | 0.9x | 0.9x | ✓ |
| O21 | What was implementation time in 2024? | implementation_days | 2024 | 45 days | 45 days | ✓ |
| O22 | What was time to value in 2025? | time_to_value_days | 2025 | 50 days | 50 days | ✓ |
| O23 | What was support ticket volume in 2025? | support_tickets | 2025 | 15,000 | 15,000 | ✓ |
| O24 | What was first response time in 2025? | first_response_hours | 2025 | 3.2 hours | 3.2 hours | ✓ |
| O25 | What was resolution time in 2024? | resolution_hours | 2024 | 24 hours | 24 hours | ✓ |
| O26 | What was CSAT in 2025? | csat | 2025 | 4.4 | 4.4 | ✓ |
| O27 | What was NPS in 2025? | nps | 2025 | 48 | 48 | ✓ |
| O31 | What was PS utilization in 2025? | ps_utilization | 2025 | 76% | 76% | ✓ |
| O32 | What was engineering utilization in 2025? | engineering_utilization | 2025 | 80% | 80% | ✓ |
| O33 | What was support utilization in 2024? | support_utilization | 2024 | 85% | 85% | ✓ |
| O46 | What was Q4 2025 headcount? | headcount | 2025-Q4 | 350 | 350 | ✓ |
| O47 | How many hires in Q2 2025? | hires | 2025-Q2 | 30 | 30 | ✓ |
| O48 | What was Q3 2025 attrition? | attrition | 2025-Q3 | 8 | 8 | ✓ |
| O49 | What was Q1 2025 attrition rate? | attrition_rate | 2025-Q1 | 2.8% | 2.8% | ✓ |

---

## CTO Questions - Ground Truth Validation

| ID | Question | Metric | Period | Expected | Actual | Status |
|----|----------|--------|--------|----------|--------|--------|
| T1 | What was engineering headcount in 2024? | engineering_headcount | 2024 | 80 | 80 | ✓ |
| T2 | What was engineering headcount in 2025? | engineering_headcount | 2025 | 115 | 115 | ✓ |
| T3 | How many features shipped in 2025? | features_shipped | 2025 | 72 | 72 | ✓ |
| T4 | What was sprint velocity in 2025? | sprint_velocity | 2025 | 60 | 60 | ✓ |
| T5 | What were total story points in 2024? | story_points | 2024 | 2,400 | 2,400 | ✓ |
| T6 | What was product headcount in 2025? | product_headcount | 2025 | 30 | 30 | ✓ |
| T7 | How many features shipped in 2024? | features_shipped | 2024 | 48 | 48 | ✓ |
| T11 | What was uptime in 2024? | uptime_pct | 2024 | 99.5% | 99.5% | ✓ |
| T12 | What was uptime in 2025? | uptime_pct | 2025 | 99.8% | 99.8% | ✓ |
| T13 | How many P1 incidents in 2025? | p1_incidents | 2025 | 6 | 6 | ✓ |
| T14 | How many P2 incidents in 2024? | p2_incidents | 2024 | 36 | 36 | ✓ |
| T15 | What was MTTR for P1 in 2025? | mttr_p1_hours | 2025 | 1.8 hours | 1.8 hours | ✓ |
| T16 | What was MTTR for P2 in 2025? | mttr_p2_hours | 2025 | 6.0 hours | 6.0 hours | ✓ |
| T17 | What was total downtime in 2024? | downtime_hours | 2024 | 43.8 hours | 43.8 hours | ✓ |
| T21 | What was tech debt score in 2024? | tech_debt_pct | 2024 | 35% | 35% | ✓ |
| T22 | What was tech debt in 2025? | tech_debt_pct | 2025 | 28% | 28% | ✓ |
| T23 | What was code coverage in 2025? | code_coverage_pct | 2025 | 75% | 75% | ✓ |
| T24 | What was bug escape rate in 2025? | bug_escape_rate | 2025 | 5% | 5% | ✓ |
| T25 | How many critical bugs in 2025? | critical_bugs | 2025 | 8 | 8 | ✓ |
| T26 | How many security vulns in 2024? | security_vulns | 2024 | 6 | 6 | ✓ |
| T31 | How many deploys per week in 2025? | deploys_per_week | 2025 | 15 | 15 | ✓ |
| T32 | What was deployment success rate 2025? | deployment_success_pct | 2025 | 97% | 97% | ✓ |
| T33 | What was lead time in 2024? | lead_time_days | 2024 | 14 days | 14 days | ✓ |
| T34 | What was lead time in 2025? | lead_time_days | 2025 | 7 days | 7 days | ✓ |
| T35 | What was change failure rate in 2025? | change_failure_rate | 2025 | 8% | 8% | ✓ |
| T41 | What was cloud spend in 2024? | cloud_spend | 2024 | $2.4M | $2.4M | ✓ |
| T42 | What was cloud spend in 2025? | cloud_spend | 2025 | $3.2M | $3.2M | ✓ |
| T43 | What was cloud spend % of revenue 2025? | cloud_spend_pct_revenue | 2025 | 2.1% | 2.1% | ✓ |
| T44 | What was cost per transaction in 2025? | cost_per_transaction | 2025 | $0.009 | $0.009 | ✓ |
| T45 | What were monthly API requests in 2025? | api_requests_millions | 2025 | 280M | 280M | ✓ |
| T51 | Features shipped in Q4 2025? | features_shipped | 2025-Q4 | 21 | 21 | ✓ |
| T52 | What was Q2 2025 velocity? | story_points | 2025-Q2 | 875 | 875 | ✓ |
| T53 | How many P1 incidents in Q3 2025? | p1_incidents | 2025-Q3 | 1 | 1 | ✓ |

---

## Metric Synonym Mappings (For Query Parsing)

The following synonyms should be mapped to canonical metrics:

| User Term | Canonical Metric |
|-----------|-----------------|
| sales | revenue |
| total revenue | revenue |
| TCV | bookings |
| ACV | bookings |
| close rate | win_rate |
| sales funnel | pipeline |
| new business bookings | new_logo_revenue |
| churn | gross_churn_pct |
| total headcount | headcount |
| employees | headcount |
| staff | headcount |
| team size | headcount |
| CAC payback | cac_payback_months |
| payback period | cac_payback_months |
| LTV CAC | ltv_cac |
| uptime | uptime_pct |
| velocity | sprint_velocity |
| MTTR | mttr_p1_hours |
| tech debt | tech_debt_pct |
| code coverage | code_coverage_pct |

---

## Test Environment Notes

1. **Data Source:** `/data/fact_base.json`
2. **Schema:** All 88+ metrics defined in `/src/nlq/knowledge/schema.py`
3. **Periods Covered:** 2024, 2025, 2026 (annual) + all quarters
4. **Personas:** CFO, CRO, COO, CTO, People

## Known Issues

1. **API Key Required:** The Claude LLM parsing requires `ANTHROPIC_API_KEY` environment variable
2. **Static Mode:** Cache must be seeded for static mode to return results
3. **Query Parsing:** Natural language queries require LLM for parsing to canonical metric names

## Recommendations

1. Ensure `ANTHROPIC_API_KEY` is set in Replit secrets
2. Use **AI mode** for new/unseen queries (requires LLM)
3. Use **Static mode** only for cached queries (no LLM cost)
4. The fact base data is 100% accurate - any query issues are in the parsing layer
