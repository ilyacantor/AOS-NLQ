# fact_base_v3.json - Complete Multi-Persona Expansion

## Overview

Fully expanded fact base with **31 top-level data structures**, **12 quarters** of dimensional data, and **36 sales reps** with complete performance tracking. All 5 personas now have drill-down capabilities.

---

## Data Statistics

| Metric | Value |
|--------|-------|
| File size | 178 KB |
| Quarters | 12 (2024-Q1 → 2026-Q4) |
| Sales reps | 36 (22 in 2024, 29 in 2025, 36 in 2026) |
| Metrics per quarter | ~80 |
| Dimensional breakdowns | 27 (all quarterly) |

---

## Persona-Specific Drill-Downs

### CFO Persona
| Dimension | Structure | Sample Query |
|-----------|-----------|--------------|
| `revenue_by_region` | AMER/EMEA/APAC × 12 quarters | "Q3 EMEA revenue" |
| `revenue_by_segment` | Enterprise/Mid-Market/SMB × 12 quarters | "Enterprise revenue trend" |
| `revenue_by_product` | 4 products × 12 quarters | "Professional tier growth" |
| `ebitda_by_region` | AMER/EMEA/APAC × 12 quarters | "APAC profitability" |
| `customer_segments` | Per-segment revenue, deal size, churn, NRR | "Enterprise vs SMB churn" |

**New metrics added to quarterly:** `depreciation`, `amortization`, `d_and_a`, `ebitda`, `ebitda_margin_pct`

---

### CRO Persona
| Dimension | Structure | Sample Query |
|-----------|-----------|--------------|
| `quota_by_rep` | 22-36 reps × 12 quarters | "Show reps below quota" |
| `pipeline_by_rep` | Per-rep pipeline, qualified, deal count | "John Mitchell's pipeline" |
| `win_rate_by_rep` | Per-rep win rates × 12 quarters | "Top performers by win rate" |
| `pipeline_by_stage` | 5 stages × 12 quarters | "Deals in Negotiation this quarter" |
| `pipeline_by_region` | AMER/EMEA/APAC × 12 quarters | "EMEA pipeline vs last quarter" |
| `stage_conversion_rates` | 4 conversion metrics × 12 quarters | "Proposal to Negotiation rate" |
| `stalled_deals` | 2 deals per quarter with rep/stage/days | "Which deals need attention?" |
| `top_deals` | Top 5 per year with rep/region/segment | "Largest deal this year" |
| `sales_reps` | 36 reps with region, territory, hire date | "Reps in DACH territory" |

---

### COO Persona
| Dimension | Structure | Sample Query |
|-----------|-----------|--------------|
| `support_tickets_by_tier` | Tier1/Tier2/Tier3 × 12 quarters | "Tier 3 escalation trend" |
| `support_tickets_by_category` | 5 categories × 12 quarters | "Technical vs Billing tickets" |
| `csat_by_segment` | Enterprise/Mid-Market/SMB × 12 quarters | "SMB satisfaction trend" |
| `implementation_by_segment` | Days by segment × 12 quarters | "Enterprise implementation time" |
| `customer_segments` | Churn, NRR by segment × 12 quarters | "Mid-Market retention" |

**Quarterly metrics:** `implementation_days`, `time_to_value_days`, `first_response_hours`, `resolution_hours`, `ps_utilization`, `support_utilization`

---

### CTO Persona
| Dimension | Structure | Sample Query |
|-----------|-----------|--------------|
| `engineering_by_team` | 7 teams × 12 quarters | "Platform team headcount" |
| `velocity_by_team` | Sprint velocity by team × 12 quarters | "Backend vs Frontend velocity" |
| `incidents_by_service` | 6 services × 12 quarters | "API incidents this quarter" |
| `cloud_spend_by_category` | 5 categories × 12 quarters | "Compute vs Storage costs" |

**Quarterly metrics:** `features_shipped`, `story_points`, `sprint_velocity`, `uptime_pct`, `downtime_hours`, `p1_incidents`, `p2_incidents`, `mttr_p1_hours`, `mttr_p2_hours`, `tech_debt_pct`, `code_coverage_pct`, `deploys_per_week`, `deployment_success_pct`, `lead_time_days`, `change_failure_rate`, `cloud_spend`, `engineering_utilization`, `bug_escape_rate`, `critical_bugs`, `security_vulns`, `api_requests_millions`

---

### CHRO Persona
| Dimension | Structure | Sample Query |
|-----------|-----------|--------------|
| `headcount_by_department` | 8 departments × 12 quarters | "Engineering growth rate" |
| `attrition_by_department` | Attrition by dept × 12 quarters | "Sales turnover" |
| `engagement_by_department` | Score by dept × 12 quarters | "Product team engagement" |
| `time_to_fill_by_department` | Days by dept × 12 quarters | "Engineering hiring velocity" |

**Quarterly metrics:** `headcount`, `hires`, `attrition`, `attrition_rate`, `open_roles`, `time_to_fill_days`, `offer_acceptance_rate`, `employee_satisfaction`, `engagement_score`, `training_hours_per_employee`

---

## Drill-Down Paths Enabled

```
Revenue → Region → (rep via quota_by_rep region mapping)
Revenue → Segment → (churn, NRR, deal size)
Revenue → Product
Pipeline → Region → Rep
Pipeline → Stage → (stalled deals)
Quota → Rep → (attainment trend)
Engineering → Team → (velocity, headcount)
Support → Tier
Support → Category
Incidents → Service
Cloud → Category
Headcount → Department → (attrition, engagement, TTF)
CSAT → Segment
Implementation → Segment
```

---

## Rep Performance Tiers (Built-in)

| Tier | Reps | Characteristics |
|------|------|-----------------|
| Top | Michael Brown, Sarah Williams, Wei Zhang, Anna Schmidt, Emily Davis | 106%+ attainment, 45%+ win rate |
| Solid | John Mitchell, David Rodriguez, Jennifer Taylor, Pierre Dubois, others | 100-103% attainment, 40-44% win rate |
| Developing | Lisa Chen, Amanda Foster, Robert Kim, Thomas Anderson, others | 94-97% attainment, 33-38% win rate |
| New | Jessica Wong, Brandon Scott, Ashley Moore, Henrik Nielsen, others | Ramping, smaller quotas |

---

## Key Formulas Used

- **EBITDA** = Operating Profit + Depreciation + Amortization
- **D&A** = Revenue × 3.5% (2% depreciation + 1.5% amortization)
- **Quota attainment** = Actual / Quota × 100
- **Pipeline coverage** implied by rep pipeline / quota ratio (~3x)
- **Regional splits** = 50/30/20 (AMER/EMEA/APAC)
- **Segment splits** = 55/30/15 (Enterprise/Mid-Market/SMB)

---

## Usage

```bash
# Replace existing fact base
cp fact_base_v3.json src/nlq/knowledge/fact_base.json
```

The loader auto-discovers all new fields. No code changes needed.

---

## What's NOT Included (Future Consideration)

- Individual deal/opportunity records (would need separate deals table)
- Customer-level data (individual accounts)
- Activity metrics by rep (calls, emails, meetings)
- Forecast vs actual by rep
- Real-time data connections
