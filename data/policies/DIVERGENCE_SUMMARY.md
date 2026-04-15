# Meridian + Cascadia: Policy Divergence Summary

This document identifies every accounting policy area where Meridian Partners (acquirer, meridian) and Cascadia Process Solutions (target, cascadia) apply different treatments. These are the six COFA conflicts explicitly designed into the Farm financial models, plus additional structural divergences that affect combined reporting.

---

## Designed COFA Conflicts (from Farm configs)

These six conflicts are intentional — they exist in the generated financial data and are the primary test cases for Mai's harmonization reasoning.

### 1. Benefits Treatment in COGS

- **Meridian:** Consultant compensation includes benefits — bundled into a single COGS line (62% of COGS, ~$1,891M). There is no separate benefits line.
- **Cascadia:** Benefits are a distinct COGS line item (10.1% of COGS, ~$72M), separate from labor compensation (onshore/offshore/nearshore lines).
- **Impact on combined financials:** Gross margins are not directly comparable. Meridian's COGS composition shows one large compensation line; Cascadia's shows labor and benefits separately. Any combined COGS analysis must either reclassify Cascadia's benefits into labor lines or split Meridian's compensation into labor + benefits. Without reclassification, Meridian appears to have higher per-head labor costs and Cascadia appears to have lower labor costs with an unexplained benefits line.

### 2. Sales & Marketing Reporting

- **Meridian:** Sales and Marketing are reported as two separate OpEx line items — Sales at 4% of revenue ($200M) and Marketing at 2.5% of revenue ($125M).
- **Cascadia:** Sales & Marketing are bundled into a single OpEx line at 13.2% of revenue ($132M).
- **Impact on combined financials:** The combined entity cannot produce a consistent S&M breakdown without reclassification. Segment-level comparisons of sales efficiency (cost per deal) or marketing efficiency (pipeline per dollar) are impossible across legacy segments. Cascadia's bundled S&M as a percentage of revenue (13.2%) appears much higher than Meridian's combined (6.5%), but this partly reflects different business models — BPM has longer sales cycles (150 days vs. 120) and fewer, larger deals.

### 3. Recruiting Cost Capitalization

- **Meridian:** All recruiting costs are expensed as incurred — 1% of revenue ($50M/year) flows through OpEx immediately.
- **Cascadia:** Recruiting costs tied to new contract wins are capitalized — $8M/year is capitalized as a contract acquisition cost and amortized over the average contract duration (3.5 years). General recruiting is expensed.
- **Impact on combined financials:** $8M/year of Cascadia's recruiting cost appears on the balance sheet (amortizing intangible) rather than in period OpEx. If unharmonized, Cascadia's operating expenses are understated by $8M/year relative to what they would be under Meridian's treatment. Combined operating income comparisons across segments are distorted by this asymmetry.

### 4. Automation Development Capitalization

- **Meridian:** All technology and R&D costs are expensed as incurred — 1.5% of revenue ($75M/year) in R&D flows through OpEx.
- **Cascadia:** $12M/year of automation platform development is capitalized as intangible assets (part of $95M starting intangibles balance). The remaining technology & automation costs ($68M of the $80M total) are expensed.
- **Impact on combined financials:** Similar to recruiting: $12M/year of Cascadia's technology costs are on the balance sheet rather than in period OpEx. Combined with the recruiting capitalization, $20M/year of Cascadia costs would be expensed under Meridian's treatment. This is the largest single source of COFA non-comparability in operating expenses.

### 5. Depreciation Method

- **Meridian:** Straight-line depreciation over 5-year useful life for all asset classes. D&A is 2% of revenue ($100M/year).
- **Cascadia:** Accelerated depreciation over 3-year useful life for delivery center equipment and capitalized intangibles.
- **Impact on combined financials:** On equivalent asset values, Cascadia's method produces ~67% of total depreciation in years 1-2, while Meridian's produces 40% over the same period. Combined D&A expense will show a blend of two depreciation curves. Year-over-year changes in combined D&A will not correlate cleanly with capex changes because the two methods respond differently to the same asset additions. PP&E net book values are not comparable — a 2-year-old asset at Cascadia has a much lower NBV than the same asset at Meridian.

### 6. Revenue Gross-Up (Contractor Markup)

- **Meridian:** Books contractor markup as revenue — when using subcontractors, only the markup (difference between billing rate and contractor cost) is recognized as revenue.
- **Cascadia:** Books the full FTE rate as revenue — when deploying FTEs (including those subcontracted), the full contracted rate is recognized as revenue.
- **Impact on combined financials:** An approximately $50M delta in top-line revenue comparison at comparable service delivery levels. Cascadia's revenue per engagement appears higher, but so do its COGS. Revenue and COGS are both inflated relative to Meridian's treatment for economically equivalent arrangements. Combined revenue totals will overstate organic growth if the two treatments are not harmonized. Revenue-based metrics (revenue per employee, S&M as % of revenue) are distorted by the gross-up.

---

## Structural Divergences (Beyond Designed COFA Conflicts)

These differences arise from the fundamentally different business models, not from intentional accounting policy choices.

### Business Model and Revenue Mix

- **Meridian:** Project-based consultancy. 65% T&M, 35% fixed-fee. Recognition based on hours worked (T&M) or percentage-of-completion (fixed-fee). Average engagement $4.2M, 1,200 customers.
- **Cascadia:** BPM / managed services. 44% managed services (fixed monthly), 37% per-FTE, 19% per-transaction. Recognition based on monthly fees, FTE deployment, and transaction volumes. Average contract $5M ACV, 200 customers.
- **Impact on combined financials:** Revenue recognition methods differ across every revenue stream. Backlog profiles differ fundamentally — Cascadia has longer contracts (3.5 years average) with more predictable revenue; Meridian has shorter engagements with higher variance. Customer concentration risk differs materially — Cascadia has fewer, larger clients.

### Gross Margin Profile

- **Meridian:** 39% gross margin. Lower COGS percentage driven by higher billing rates and project-based delivery.
- **Cascadia:** 29% gross margin. Higher COGS percentage driven by labor-intensive delivery model with large offshore workforce.
- **Impact on combined financials:** Combined gross margin (~37% blended) obscures fundamentally different cost structures. Segment-level margin analysis is essential for understanding combined entity profitability.

### Capital Intensity

- **Meridian:** CapEx at 1.5% of revenue (~$75M/year). Asset-light consultancy model.
- **Cascadia:** CapEx at 3.5% of revenue (~$35M/year). Higher capital intensity from delivery center equipment, despite smaller revenue base.
- **Impact on combined financials:** Cascadia's capital intensity as a percentage of revenue is 2.3x Meridian's. Combined free cash flow will reflect a blended capital intensity that doesn't match either standalone entity.

### Regional Footprint

- **Meridian:** Four regions (AMER 45%, EMEA 30%, APAC 18%, LATAM 7%). Consultants co-located with clients.
- **Cascadia:** Three regions (AMER 55%, EMEA 25%, APAC 20%) for revenue, but delivery from 6 geos (India, Philippines, Costa Rica, Poland, US, UK). Revenue geo and delivery geo are decoupled.
- **Impact on combined financials:** Cascadia's offshore delivery creates FX exposure on costs (INR, PHP, CRC, PLN) that Meridian does not have. Combined regional reporting must handle the revenue-region vs. delivery-geo decoupling.

### Headcount Definition

- **Meridian:** 30,000 total (includes contractors). 15% annual attrition.
- **Cascadia:** 8,000 total (W-2 only, excludes contractors). 22% delivery attrition, 10% corporate attrition.
- **Impact on combined financials:** Headcount-based metrics (revenue per employee, cost per employee) are not comparable — Meridian's denominator includes contractors while Cascadia's excludes them. Combined headcount figures will be meaningless without a uniform counting methodology.

### Debt-to-Revenue Ratio

- **Meridian:** $500M debt / $5B revenue = 10%.
- **Cascadia:** $150M debt / $1B revenue = 15%.
- **Impact on combined financials:** Cascadia is more leveraged relative to its revenue. Combined debt metrics should be monitored at the segment level, not just consolidated.

---

## Gap Divergences

| Policy Area | Meridian Status | Cascadia Status | Harmonization Priority |
|-------------|----------------|-----------------|----------------------|
| Foreign currency | Gap (multi-region revenue) | Gap (multi-geo delivery costs) | High — both entities have unaddressed FX exposure, but on different sides (revenue vs. cost) |
| Goodwill impairment | Gap ($2.4B goodwill) | Gap ($320M goodwill) | High — combined $2.7B goodwill requires impairment testing methodology |
| Lease accounting | Gap | Gap | Medium — both entities have office/facility leases without ASC 842 documentation |
| Bad debt | Gap ($805M AR) | Gap ($144M AR) | Medium — combined AR exposure requires consistent credit loss methodology |
| SBC | Gap (likely material) | Gap (likely immaterial pre-close, material post-close) | Medium — acquirer equity grants will make this material for combined entity |
| Interest expense | Gap ($500M debt) | Gap ($150M debt) | Low — combined $650M debt requires consistent interest policy |
| Deferred tax | Gap (24% simplified) | Gap (22% simplified) | High — different effective rates, offshore operations, capitalization differences all create deferred tax complexity |
| Cash-to-accrual conversion | N/A (already accrual) | Gap (transitioning from cash basis) | Critical — Cascadia's historical financials on cash basis require restatement for comparability |
