# AOS-NLQ Multi-Persona Test Suite

## Persona Domains

| Persona | Domain | Focus Areas |
|---------|--------|-------------|
| **CFO** | Finance | P&L, Balance Sheet, Cash, Margins, Profitability |
| **CRO** | Growth | Revenue, Bookings, Pipeline, Churn, Expansion, Quotas |
| **COO** | Operations | Headcount, Efficiency, Utilization, SLAs, COGS ratios |
| **CTO** | Product/Tech | Engineering, Uptime, Incidents, Velocity, Tech Debt |

---

# PART 1: FACT BASES

## CFO Fact Base (Existing - Finance Domain)

### P&L Data
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Revenue | $100.0M | $150.0M | $200.0M |
| COGS | $35.0M | $52.5M | $70.0M |
| Gross Profit | $65.0M | $97.5M | $130.0M |
| SG&A | $30.0M | $45.0M | $60.0M |
| Selling Expenses | $18.0M | $27.0M | $36.0M |
| G&A Expenses | $12.0M | $18.0M | $24.0M |
| Operating Profit | $35.0M | $52.5M | $70.0M |
| Net Income | $26.25M | $39.38M | $52.5M |

### Margins
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Gross Margin % | 65.0% | 65.0% | 65.0% |
| Operating Margin % | 35.0% | 35.0% | 35.0% |
| Net Margin % | 26.25% | 26.25% | 26.25% |

### Balance Sheet (Q4 each year)
| Metric | Q4 2024 | Q4 2025 | Q4 2026F |
|--------|---------|---------|----------|
| Cash | $27.61M | $41.42M | $55.23M |
| AR | $13.81M | $20.71M | $27.61M |
| AP | $4.10M | $6.15M | $8.20M |
| Deferred Revenue | $11.50M | $17.25M | $23.00M |
| Current Assets | $50.38M | $75.57M | $100.76M |
| Current Liabilities | $17.65M | $26.47M | $35.30M |

---

## CRO Fact Base (Growth Domain)

### Revenue & Bookings
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Revenue | $100.0M | $150.0M | $200.0M |
| Bookings (TCV) | $115.0M | $172.5M | $230.0M |
| ARR | $95.0M | $142.5M | $190.0M |
| New Logo Revenue | $25.0M | $35.0M | $45.0M |
| Expansion Revenue | $15.0M | $25.0M | $35.0M |
| Renewal Revenue | $60.0M | $90.0M | $120.0M |

### Pipeline & Conversion
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Sales Pipeline | $287.5M | $431.25M | $575.0M |
| Qualified Pipeline | $172.5M | $258.75M | $345.0M |
| Win Rate | 40% | 42% | 44% |
| Sales Cycle (days) | 90 | 85 | 80 |
| Avg Deal Size | $125K | $150K | $175K |

### Churn & Retention
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Gross Revenue Churn | 8% | 7% | 6% |
| Net Revenue Retention | 115% | 118% | 120% |
| Logo Churn | 12% | 10% | 8% |
| Customer Count | 800 | 950 | 1,100 |

### Quota & Attainment
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Sales Quota (Total) | $120.0M | $180.0M | $240.0M |
| Quota Attainment | 95.8% | 95.8% | 95.8% |
| Reps at Quota | 68% | 72% | 75% |
| Sales Headcount | 45 | 60 | 80 |
| Quota per Rep | $2.67M | $3.0M | $3.0M |

### Quarterly Breakdown (2025)
| Metric | Q1 | Q2 | Q3 | Q4 |
|--------|-----|-----|-----|-----|
| Bookings | $34.5M | $39.15M | $43.125M | $55.725M |
| Pipeline Created | $86.25M | $97.875M | $107.81M | $139.31M |
| Win Rate | 40% | 41% | 43% | 44% |
| New Logos | 35 | 40 | 45 | 55 |

---

## COO Fact Base (Operations Domain)

### Headcount & Efficiency
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Total Headcount | 250 | 350 | 450 |
| Revenue per Employee | $400K | $429K | $444K |
| Cost per Employee | $180K | $175K | $170K |
| Employee Growth Rate | 25% | 40% | 29% |

### Headcount by Function
| Function | 2024 | 2025 | 2026F |
|----------|------|------|-------|
| Sales | 45 | 60 | 80 |
| Marketing | 25 | 35 | 45 |
| Engineering | 80 | 115 | 150 |
| Product | 20 | 30 | 40 |
| Customer Success | 35 | 50 | 65 |
| G&A | 45 | 60 | 70 |

### Operational Efficiency
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Magic Number | 0.8 | 0.85 | 0.9 |
| CAC Payback (months) | 18 | 16 | 14 |
| LTV/CAC | 3.2x | 3.5x | 3.8x |
| Burn Multiple | 1.2x | 0.9x | 0.7x |

### Service Delivery
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Implementation Time (days) | 45 | 38 | 32 |
| Time to Value (days) | 60 | 50 | 42 |
| Support Ticket Volume | 12,000 | 15,000 | 18,000 |
| First Response Time (hrs) | 4.0 | 3.2 | 2.5 |
| Resolution Time (hrs) | 24 | 18 | 14 |
| CSAT Score | 4.2 | 4.4 | 4.6 |
| NPS | 42 | 48 | 55 |

### Utilization
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| PS Utilization | 72% | 76% | 80% |
| Engineering Utilization | 78% | 80% | 82% |
| Support Utilization | 85% | 82% | 80% |

### Quarterly Breakdown (2025)
| Metric | Q1 | Q2 | Q3 | Q4 |
|--------|-----|-----|-----|-----|
| Headcount | 285 | 310 | 330 | 350 |
| Hires | 25 | 30 | 28 | 32 |
| Attrition | 8 | 5 | 8 | 12 |
| Attrition Rate | 2.8% | 1.6% | 2.4% | 3.4% |

---

## CTO Fact Base (Product/Tech Domain)

### Product & Engineering
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Engineering Headcount | 80 | 115 | 150 |
| Product Headcount | 20 | 30 | 40 |
| Features Shipped | 48 | 72 | 96 |
| Story Points Completed | 2,400 | 3,600 | 4,800 |
| Sprint Velocity (avg) | 50 | 60 | 67 |

### Platform Reliability
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Uptime | 99.5% | 99.8% | 99.95% |
| Downtime (hrs/year) | 43.8 | 17.5 | 4.4 |
| P1 Incidents | 12 | 6 | 3 |
| P2 Incidents | 36 | 24 | 15 |
| MTTR (P1, hrs) | 2.5 | 1.8 | 1.0 |
| MTTR (P2, hrs) | 8.0 | 6.0 | 4.0 |

### Code Quality & Tech Debt
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Tech Debt Score | 35% | 28% | 20% |
| Code Coverage | 68% | 75% | 82% |
| Bug Escape Rate | 8% | 5% | 3% |
| Critical Bugs Open | 15 | 8 | 4 |
| Security Vulnerabilities | 6 | 3 | 1 |

### Deployment & DevOps
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Deploys per Week | 8 | 15 | 25 |
| Deployment Success Rate | 94% | 97% | 99% |
| Lead Time (days) | 14 | 7 | 3 |
| Change Failure Rate | 12% | 8% | 4% |

### Infrastructure & Costs
| Metric | 2024 | 2025 | 2026F |
|--------|------|------|-------|
| Cloud Spend | $2.4M | $3.2M | $4.0M |
| Cloud Spend % Revenue | 2.4% | 2.1% | 2.0% |
| Cost per Transaction | $0.012 | $0.009 | $0.007 |
| API Requests (M/month) | 150 | 280 | 450 |

### Quarterly Breakdown (2025)
| Metric | Q1 | Q2 | Q3 | Q4 |
|--------|-----|-----|-----|-----|
| Features Shipped | 15 | 18 | 18 | 21 |
| Story Points | 750 | 875 | 925 | 1,050 |
| P1 Incidents | 2 | 2 | 1 | 1 |
| Deploys | 150 | 180 | 200 | 250 |

---

# PART 2: DIRECT QUESTIONS (Precise - 100% Accuracy Required)

## CFO Questions (Already Exists - Q1-55)
*See existing test suite*

---

## CRO Questions (C1-C55)

### Absolute Date Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C1 | What were total bookings in 2024? | $115.0M |
| C2 | What was ARR in 2025? | $142.5M |
| C3 | What was new logo revenue in 2024? | $25.0M |
| C4 | What was expansion revenue in 2025? | $25.0M |
| C5 | What was our win rate in 2024? | 40% |
| C6 | What was the sales pipeline in 2025? | $431.25M |
| C7 | How many customers did we have in 2024? | 800 |
| C8 | What was net revenue retention in 2025? | 118% |
| C9 | What was gross revenue churn in 2024? | 8% |
| C10 | What was average deal size in 2025? | $150K |

### Relative Date Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C11 | What were bookings last year? | $172.5M (2025) |
| C12 | What's our ARR this year? | $190.0M (2026F) |
| C13 | What was win rate last quarter? | 44% (Q4 2025) |
| C14 | What's the pipeline this year? | $575.0M (2026F) |
| C15 | What was NRR last year? | 118% (2025) |

### Quarterly Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C16 | What were Q4 2025 bookings? | $55.725M |
| C17 | What was the win rate in Q3 2025? | 43% |
| C18 | How many new logos in Q4 2025? | 55 |
| C19 | What was Q2 2025 pipeline created? | $97.875M |
| C20 | What were Q1 2025 bookings? | $34.5M |

### Comparison Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C21 | How did bookings grow from 2024 to 2025? | +$57.5M (+50%) |
| C22 | Compare win rate 2024 vs 2025 | 40% → 42% (+2pts) |
| C23 | What was YoY ARR growth in 2025? | +50% |
| C24 | How did churn change from 2024 to 2025? | 8% → 7% (-1pt improvement) |
| C25 | Compare NRR 2024 vs 2025 | 115% → 118% (+3pts) |

### Quota & Attainment Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C26 | What was the sales quota in 2025? | $180.0M |
| C27 | What was quota attainment in 2024? | 95.8% |
| C28 | How many reps at quota in 2025? | 72% |
| C29 | What was quota per rep in 2025? | $3.0M |
| C30 | How many sales reps in 2025? | 60 |

### Churn & Retention Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C31 | What was logo churn in 2025? | 10% |
| C32 | What was renewal revenue in 2025? | $90.0M |
| C33 | What was customer count in 2025? | 950 |
| C34 | What was gross churn in 2026 forecast? | 6% |
| C35 | What's the NRR forecast for 2026? | 120% |

### Synonym Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C36 | What was TCV in 2025? | $172.5M (= bookings) |
| C37 | What was ACV in 2025? | $172.5M (= bookings, 1yr deals) |
| C38 | What were new business bookings in 2024? | $25.0M (= new logo revenue) |
| C39 | What was the close rate in 2025? | 42% (= win rate) |
| C40 | What was the sales funnel in 2025? | $431.25M (= pipeline) |

### Aggregation Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C41 | What was total H1 2025 bookings? | $73.65M |
| C42 | What was average quarterly bookings in 2025? | $43.125M |
| C43 | How many total new logos in 2025? | 175 |
| C44 | What was total pipeline created in 2025? | $431.25M |
| C45 | What was average quarterly win rate in 2025? | 42% |

### Forecast Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C46 | What's the bookings forecast for 2026? | $230.0M |
| C47 | What's projected win rate in 2026? | 44% |
| C48 | What's the 2026 customer count target? | 1,100 |
| C49 | What's forecast NRR for 2026? | 120% |
| C50 | What's the 2026 sales quota? | $240.0M |

### Breakdown Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| C51 | Break down 2025 revenue by type | New: $35M, Expansion: $25M, Renewal: $90M |
| C52 | What's the pipeline stage breakdown for 2025? | Total: $431.25M, Qualified: $258.75M |
| C53 | Break down bookings by quarter for 2025 | Q1: $34.5M, Q2: $39.15M, Q3: $43.125M, Q4: $55.725M |
| C54 | What's the quota attainment distribution? | 72% at quota (2025) |
| C55 | Break down new logos by quarter 2025 | Q1: 35, Q2: 40, Q3: 45, Q4: 55 |

---

## COO Questions (O1-O55)

### Headcount Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| O1 | What was total headcount in 2024? | 250 |
| O2 | What was total headcount in 2025? | 350 |
| O3 | What was engineering headcount in 2025? | 115 |
| O4 | What was sales headcount in 2024? | 45 |
| O5 | What was G&A headcount in 2025? | 60 |
| O6 | What was customer success headcount in 2025? | 50 |
| O7 | How many people in marketing in 2025? | 35 |
| O8 | What was product headcount in 2025? | 30 |
| O9 | What was headcount growth rate in 2025? | 40% |
| O10 | What's the 2026 headcount forecast? | 450 |

### Efficiency Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| O11 | What was revenue per employee in 2024? | $400K |
| O12 | What was revenue per employee in 2025? | $429K |
| O13 | What was cost per employee in 2025? | $175K |
| O14 | What was the magic number in 2025? | 0.85 |
| O15 | What was CAC payback in 2024? | 18 months |
| O16 | What was LTV/CAC in 2025? | 3.5x |
| O17 | What was burn multiple in 2025? | 0.9x |
| O18 | What's the 2026 magic number forecast? | 0.9 |
| O19 | What's the 2026 CAC payback forecast? | 14 months |
| O20 | What's LTV/CAC forecast for 2026? | 3.8x |

### Service Delivery Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| O21 | What was implementation time in 2024? | 45 days |
| O22 | What was time to value in 2025? | 50 days |
| O23 | What was support ticket volume in 2025? | 15,000 |
| O24 | What was first response time in 2025? | 3.2 hours |
| O25 | What was resolution time in 2024? | 24 hours |
| O26 | What was CSAT in 2025? | 4.4 |
| O27 | What was NPS in 2025? | 48 |
| O28 | What's the 2026 NPS target? | 55 |
| O29 | What's forecast resolution time for 2026? | 14 hours |
| O30 | What's the CSAT target for 2026? | 4.6 |

### Utilization Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| O31 | What was PS utilization in 2025? | 76% |
| O32 | What was engineering utilization in 2025? | 80% |
| O33 | What was support utilization in 2024? | 85% |
| O34 | What's PS utilization forecast for 2026? | 80% |
| O35 | What's the engineering utilization target? | 82% (2026) |

### Relative Date Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| O36 | What was headcount last year? | 350 (2025) |
| O37 | What's headcount this year? | 450 (2026F) |
| O38 | What was magic number last year? | 0.85 (2025) |
| O39 | What was NPS last year? | 48 (2025) |
| O40 | What was attrition last quarter? | 3.4% (Q4 2025) |

### Comparison Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| O41 | How did headcount grow from 2024 to 2025? | +100 (+40%) |
| O42 | Compare revenue per employee 2024 vs 2025 | $400K → $429K (+7.25%) |
| O43 | How did implementation time improve? | 45 → 38 days (-15.6%) |
| O44 | Compare NPS 2024 vs 2025 | 42 → 48 (+6 pts) |
| O45 | How did attrition change Q1 to Q4 2025? | 2.8% → 3.4% (+0.6pts) |

### Quarterly Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| O46 | What was Q4 2025 headcount? | 350 |
| O47 | How many hires in Q2 2025? | 30 |
| O48 | What was Q3 2025 attrition? | 8 people (2.4%) |
| O49 | What was Q1 2025 attrition rate? | 2.8% |
| O50 | How many hires in H1 2025? | 55 |

### Breakdown Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| O51 | Break down 2025 headcount by function | Sales: 60, Mktg: 35, Eng: 115, Prod: 30, CS: 50, G&A: 60 |
| O52 | Break down Q4 2025 attrition | 12 people, 3.4% rate |
| O53 | Break down hires by quarter 2025 | Q1: 25, Q2: 30, Q3: 28, Q4: 32 |
| O54 | What's the efficiency metrics breakdown? | Magic: 0.85, CAC: 16mo, LTV/CAC: 3.5x |
| O55 | Break down service metrics for 2025 | FRT: 3.2h, Resolution: 18h, CSAT: 4.4, NPS: 48 |

---

## CTO Questions (T1-T55)

### Engineering & Product Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| T1 | What was engineering headcount in 2024? | 80 |
| T2 | What was engineering headcount in 2025? | 115 |
| T3 | How many features shipped in 2025? | 72 |
| T4 | What was sprint velocity in 2025? | 60 story points |
| T5 | What were total story points in 2024? | 2,400 |
| T6 | What was product headcount in 2025? | 30 |
| T7 | How many features shipped in 2024? | 48 |
| T8 | What's the 2026 feature target? | 96 |
| T9 | What's the engineering headcount target for 2026? | 150 |
| T10 | What's the 2026 velocity target? | 67 story points |

### Reliability Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| T11 | What was uptime in 2024? | 99.5% |
| T12 | What was uptime in 2025? | 99.8% |
| T13 | How many P1 incidents in 2025? | 6 |
| T14 | How many P2 incidents in 2024? | 36 |
| T15 | What was MTTR for P1 in 2025? | 1.8 hours |
| T16 | What was MTTR for P2 in 2025? | 6.0 hours |
| T17 | What was total downtime in 2024? | 43.8 hours |
| T18 | What's the 2026 uptime target? | 99.95% |
| T19 | What's the P1 incident target for 2026? | 3 |
| T20 | What's the MTTR target for P1 in 2026? | 1.0 hour |

### Code Quality Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| T21 | What was tech debt score in 2024? | 35% |
| T22 | What was tech debt in 2025? | 28% |
| T23 | What was code coverage in 2025? | 75% |
| T24 | What was bug escape rate in 2025? | 5% |
| T25 | How many critical bugs open in 2025? | 8 |
| T26 | How many security vulnerabilities in 2024? | 6 |
| T27 | What's the 2026 tech debt target? | 20% |
| T28 | What's the code coverage target for 2026? | 82% |
| T29 | What's the bug escape rate target? | 3% (2026) |
| T30 | What's the security vuln target for 2026? | 1 |

### DevOps Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| T31 | How many deploys per week in 2025? | 15 |
| T32 | What was deployment success rate in 2025? | 97% |
| T33 | What was lead time in 2024? | 14 days |
| T34 | What was lead time in 2025? | 7 days |
| T35 | What was change failure rate in 2025? | 8% |
| T36 | What's the deploy target for 2026? | 25/week |
| T37 | What's the lead time target for 2026? | 3 days |
| T38 | What's the change failure rate target? | 4% (2026) |
| T39 | What was deployment success in 2024? | 94% |
| T40 | What's deployment success target for 2026? | 99% |

### Infrastructure Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| T41 | What was cloud spend in 2024? | $2.4M |
| T42 | What was cloud spend in 2025? | $3.2M |
| T43 | What was cloud spend % of revenue in 2025? | 2.1% |
| T44 | What was cost per transaction in 2025? | $0.009 |
| T45 | What were monthly API requests in 2025? | 280M |
| T46 | What's 2026 cloud spend forecast? | $4.0M |
| T47 | What's the cloud spend % target for 2026? | 2.0% |
| T48 | What's cost per transaction target? | $0.007 (2026) |
| T49 | What's the API request forecast for 2026? | 450M/month |
| T50 | How did cloud spend grow 2024 to 2025? | +$0.8M (+33%) |

### Quarterly & Comparison Questions
| ID | Question | Ground Truth |
|----|----------|--------------|
| T51 | How many features shipped in Q4 2025? | 21 |
| T52 | What was Q2 2025 velocity? | 875 story points |
| T53 | How many P1 incidents in Q3 2025? | 1 |
| T54 | Compare tech debt 2024 vs 2025 | 35% → 28% (-7pts) |
| T55 | Break down features by quarter 2025 | Q1: 15, Q2: 18, Q3: 18, Q4: 21 |

---

# PART 3: AMBIGUOUS QUESTIONS (20 per persona)

## CFO Ambiguous (Already Exists - Q56-75)
*See existing test suite*

---

## CRO Ambiguous (CA1-CA20)

| ID | Question | Type | Expected Response |
|----|----------|------|-------------------|
| CA1 | bookings? | incomplete | $230.0M (2026F), with context |
| CA2 | how's pipeline looking | casual | $575.0M pipeline, $345M qualified |
| CA3 | are we hitting quota | yes_no | Yes, 95.8% attainment |
| CA4 | churn? | shorthand | Gross: 6%, Logo: 8%, NRR: 120% |
| CA5 | hows the funnel | casual | Pipeline $575M, Win rate 44%, Cycle 80 days |
| CA6 | did we close the big deal | implied | Need context - which deal? |
| CA7 | new business | vague_metric | New logos: $45M, 1,100 customers |
| CA8 | what's expansion doing | casual | $35M expansion revenue, +40% YoY |
| CA9 | reps performing? | vague | 75% at quota, $3M quota/rep |
| CA10 | NRR | shorthand | 120% (2026F) |
| CA11 | how'd Q4 go | casual | Bookings $55.7M, 55 new logos, 44% win rate |
| CA12 | are we growing | yes_no | Yes, +33% bookings YoY forecast |
| CA13 | retention ok? | judgment | Yes, NRR 120%, churn down to 6% |
| CA14 | close rate trend | incomplete | 40% → 42% → 44% (improving) |
| CA15 | pipeline coverage | vague | Pipeline $575M vs Quota $240M = 2.4x |
| CA16 | biggest deals | context | Need timeframe - which period? |
| CA17 | compare quarters | incomplete | Q1 vs Q4 2025: $34.5M → $55.7M (+62%) |
| CA18 | sales efficiency | vague_metric | Magic: 0.9, CAC payback: 14mo |
| CA19 | logo adds | shorthand | 1,100 total customers, +150 net new |
| CA20 | forecast looking good? | judgment | Yes, on track: $230M bookings, 44% win rate |

---

## COO Ambiguous (OA1-OA20)

| ID | Question | Type | Expected Response |
|----|----------|------|-------------------|
| OA1 | headcount? | incomplete | 450 (2026F), up 29% |
| OA2 | how's hiring going | casual | +115 hires planned, Q4: 32 hires |
| OA3 | are we efficient | yes_no | Yes, Rev/employee up to $444K |
| OA4 | attrition bad? | judgment | Moderate - 3.4% Q4, manageable |
| OA5 | team breakdown | vague | Eng: 150, Sales: 80, CS: 65, G&A: 70... |
| OA6 | support metrics | broad | FRT: 2.5h, Resolution: 14h, CSAT: 4.6 |
| OA7 | magic number | shorthand | 0.9 (2026F) |
| OA8 | utilization? | vague_metric | PS: 80%, Eng: 82%, Support: 80% |
| OA9 | how's customer success | casual | CS headcount 65, CSAT 4.6, NPS 55 |
| OA10 | onboarding time | shorthand | Implementation: 32 days, TTV: 42 days |
| OA11 | are we overstaffed | judgment | No, Rev/emp improving to $444K |
| OA12 | Q4 hires | incomplete | 32 hires in Q4 2025 |
| OA13 | burn rate ok? | judgment | Yes, burn multiple 0.7x (efficient) |
| OA14 | payback period | shorthand | CAC payback: 14 months (2026) |
| OA15 | LTV CAC | shorthand | 3.8x (2026F) |
| OA16 | support overwhelmed? | judgment | No, utilization at 80%, response times improving |
| OA17 | who's growing fastest | context | Engineering +35 (30%), Sales +20 (33%) |
| OA18 | ops summary | broad | 450 HC, $444K rev/emp, 0.9 magic, 14mo payback |
| OA19 | ticket volume trend | incomplete | 12K → 15K → 18K (+50% over 2 years) |
| OA20 | implementation getting better? | yes_no | Yes, 45 → 38 → 32 days (-29%) |

---

## CTO Ambiguous (TA1-TA20)

| ID | Question | Type | Expected Response |
|----|----------|------|-------------------|
| TA1 | uptime? | shorthand | 99.95% (2026 target) |
| TA2 | how's velocity | casual | 67 story points/sprint, up from 50 |
| TA3 | any incidents | vague | 3 P1s (2026F), down from 12 |
| TA4 | tech debt | shorthand | 20% (2026 target), down from 35% |
| TA5 | shipping enough features? | judgment | Yes, 96 planned (+33% YoY) |
| TA6 | platform stable? | yes_no | Yes, 99.95% uptime, MTTR 1hr |
| TA7 | cloud costs | incomplete | $4.0M (2026), 2.0% of revenue |
| TA8 | deployment frequency | shorthand | 25/week (2026 target) |
| TA9 | code quality | vague_metric | Coverage: 82%, Bug escape: 3%, Tech debt: 20% |
| TA10 | security posture | vague | 1 vulnerability (target), 82% coverage |
| TA11 | eng team growing? | yes_no | Yes, 80 → 115 → 150 (+88% over 2 years) |
| TA12 | how fast can we ship | casual | Lead time 3 days, 25 deploys/week |
| TA13 | reliability improving? | yes_no | Yes, uptime 99.5% → 99.8% → 99.95% |
| TA14 | MTTR | shorthand | P1: 1.0hr, P2: 4.0hr (2026 targets) |
| TA15 | infra efficient? | judgment | Yes, cost/transaction down to $0.007 |
| TA16 | Q4 performance | incomplete | 21 features, 1050 points, 1 P1, 250 deploys |
| TA17 | compare this year to last | comparison | Features: 72→96, Uptime: 99.8→99.95% |
| TA18 | eng productivity | vague_metric | 67 velocity, 96 features, 25 deploys/week |
| TA19 | bugs under control? | yes_no | Yes, 4 critical bugs, 3% escape rate |
| TA20 | platform overview | broad | 99.95% uptime, 96 features, $4M cloud, 150 eng |

---

# PART 4: METRIC MAPPINGS BY PERSONA

## Domain Assignment
```python
PERSONA_DOMAINS = {
    "CFO": Domain.FINANCE,
    "CRO": Domain.GROWTH,
    "COO": Domain.OPS,
    "CTO": Domain.PRODUCT,
}

METRIC_PERSONAS = {
    # CFO
    "revenue": "CFO", "net_income": "CFO", "gross_margin_pct": "CFO",
    "operating_margin_pct": "CFO", "cogs": "CFO", "sga": "CFO",
    "cash": "CFO", "ar": "CFO", "ap": "CFO",
    
    # CRO
    "bookings": "CRO", "arr": "CRO", "pipeline": "CRO",
    "win_rate": "CRO", "nrr": "CRO", "churn": "CRO",
    "new_logo_revenue": "CRO", "expansion_revenue": "CRO",
    "customer_count": "CRO", "quota_attainment": "CRO",
    
    # COO
    "headcount": "COO", "revenue_per_employee": "COO",
    "magic_number": "COO", "cac_payback": "COO", "ltv_cac": "COO",
    "nps": "COO", "csat": "COO", "utilization": "COO",
    "implementation_time": "COO", "attrition": "COO",
    
    # CTO
    "uptime": "CTO", "incidents": "CTO", "mttr": "CTO",
    "velocity": "CTO", "features_shipped": "CTO",
    "tech_debt": "CTO", "code_coverage": "CTO",
    "deploys_per_week": "CTO", "cloud_spend": "CTO",
}
```

## Related Metrics by Persona
```python
PERSONA_RELATED_METRICS = {
    "CFO": {
        "revenue": ["net_income", "gross_margin_pct", "operating_margin_pct"],
        "net_income": ["revenue", "net_margin_pct", "cash"],
        "cash": ["ar", "ap", "net_income"],
    },
    "CRO": {
        "bookings": ["pipeline", "win_rate", "arr"],
        "pipeline": ["bookings", "win_rate", "qualified_pipeline"],
        "nrr": ["churn", "expansion_revenue", "customer_count"],
    },
    "COO": {
        "headcount": ["revenue_per_employee", "attrition", "hires"],
        "magic_number": ["cac_payback", "ltv_cac", "revenue"],
        "nps": ["csat", "resolution_time", "ticket_volume"],
    },
    "CTO": {
        "uptime": ["incidents", "mttr", "deploys_per_week"],
        "velocity": ["features_shipped", "story_points", "eng_headcount"],
        "tech_debt": ["code_coverage", "bug_escape_rate", "critical_bugs"],
    },
}
```

---

# PART 5: PERSONA DETECTION

```python
def detect_persona(question: str) -> str:
    """Detect which persona's domain the question belongs to."""
    q = question.lower()
    
    # CRO signals
    cro_terms = ["booking", "pipeline", "quota", "win rate", "close rate",
                 "churn", "nrr", "retention", "arr", "new logo", "expansion",
                 "sales", "deal", "funnel", "tcv", "acv", "reps"]
    if any(term in q for term in cro_terms):
        return "CRO"
    
    # COO signals
    coo_terms = ["headcount", "hire", "attrition", "employee", "utilization",
                 "magic number", "cac", "ltv", "payback", "nps", "csat",
                 "support", "ticket", "implementation", "onboarding",
                 "efficiency", "burn"]
    if any(term in q for term in coo_terms):
        return "COO"
    
    # CTO signals
    cto_terms = ["uptime", "incident", "mttr", "deploy", "velocity",
                 "feature", "sprint", "tech debt", "code coverage", "bug",
                 "engineering", "cloud", "infrastructure", "api", "security",
                 "vulnerability", "lead time"]
    if any(term in q for term in cto_terms):
        return "CTO"
    
    # CFO signals (default)
    cfo_terms = ["revenue", "profit", "margin", "p&l", "income", "cash",
                 "balance sheet", "cogs", "opex", "sga", "ar", "ap",
                 "deferred", "ebitda"]
    if any(term in q for term in cfo_terms):
        return "CFO"
    
    # Default to CFO for financial questions
    return "CFO"
```

---

*Multi-Persona Test Suite v1.0*
*Total: 220 Direct Questions + 80 Ambiguous Questions = 300 Questions*
*January 2026*
