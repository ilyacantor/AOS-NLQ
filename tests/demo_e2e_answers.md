# Demo Experience Harness — 100 Questions & Answers

**Date:** 2026-03-06
**Endpoint:** POST http://127.0.0.1:8005/api/v1/query
**Overall:** 65/100

---
## A: CFO Point Queries (7/10)

### 1. A1: revenue this quarter — PASS
- **Persona:** CFO
- **Query:** "What's our revenue this quarter?"
- **Answer:** Revenue for 2026-Q1 is $35.6M
- **Time:** 909ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_dollar: has dollar sign | OK responsive: 909ms

### 2. A2: margins — FAIL
- **Persona:** CFO
- **Query:** "What are our margins?"
- **Answer:** Accounts Receivable for 2026-Q1 is $177.8M
- **Time:** 588ms
- **Checks:** OK has_data: has data | OK professional: professional | FAIL has_percent: missing % sign | FAIL mentions_all: missing: ['gross', 'operating', 'net']

### 3. A3: EBITDA — PASS
- **Persona:** CFO
- **Query:** "What's EBITDA?"
- **Answer:** EBITDA for 2026-Q1 is $14.2M
- **Time:** 603ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_dollar: has dollar sign | OK responsive: 603ms

### 4. A4: net income — PASS
- **Persona:** CFO
- **Query:** "What's net income?"
- **Answer:** Net Income for 2026-Q1 is $9.7M
- **Time:** 629ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_dollar: has dollar sign | OK formatted: numbers formatted

### 5. A5: cash position — PASS
- **Persona:** CFO
- **Query:** "What's our cash position?"
- **Answer:** Cash for 2026-Q1 is $148.0M
- **Time:** 577ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_dollar: has dollar sign

### 6. A6: ARR — PASS
- **Persona:** CFO
- **Query:** "What's ARR?"
- **Answer:** Arr for 2026-Q1 is $145.5M
- **Time:** 583ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_dollar: has dollar sign

### 7. A7: are we profitable — FAIL
- **Persona:** CFO
- **Query:** "Are we profitable?"
- **Answer:** Yes, N/A net margin in 2026 forecast
- **Time:** 1156ms
- **Checks:** FAIL has_data: contains 'n/a' | OK professional: professional | OK mentions_any: found: ['yes', 'margin'] | OK not_about: on topic

### 8. A8: burn rate — PASS
- **Persona:** CFO
- **Query:** "What's our burn rate?"
- **Answer:** Our COGS of $0M and SG&A of $0M total $0M annually. We are quite profitable, however, and have been for a long time, therefore we do not report burn_rate discretely.
- **Time:** 868ms
- **Checks:** OK has_data: has data | OK professional: professional | OK not_about: on topic

### 9. A9: cost structure — FAIL
- **Persona:** CFO
- **Query:** "What's our cost structure look like?"
- **Answer:** Gross Margin for 2026-Q1 is 66.4%
- **Time:** 573ms
- **Checks:** OK has_data: has data | OK professional: professional | FAIL mentions_any: none of ['cogs', 'cost', 'opex', 'expense', 'sg&a'] found

### 10. A10: runway — PASS
- **Persona:** CFO
- **Query:** "How much runway do we have?"
- **Answer:** Our COGS of $0M and SG&A of $0M total $0M annually. We are quite profitable, however, and have been for a long time, therefore we do not report burn_rate discretely.
- **Time:** 731ms
- **Checks:** OK has_data: has data | OK professional: professional | OK mentions_any: found: ['burn']

---
## B: CRO Point Queries (8/10)

### 11. B1: pipeline — PASS
- **Persona:** CRO
- **Query:** "How's pipeline looking?"
- **Answer:** Pipeline for 2026-Q1 is $177.9M
- **Time:** 564ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_dollar_or_number: has dollar sign

### 12. B2: win rate — PASS
- **Persona:** CRO
- **Query:** "What's our win rate?"
- **Answer:** Win Rate Pct for 2026-Q1 is 40.0%
- **Time:** 812ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_percent: has percentage

### 13. B3: churn — PASS
- **Persona:** CRO
- **Query:** "What's churn?"
- **Answer:** Churn Rate Pct for 2026-Q1 is 7.2%
- **Time:** 639ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_percent: has percentage | OK not_about: on topic

### 14. B4: NRR — PASS
- **Persona:** CRO
- **Query:** "What's NRR?"
- **Answer:** Nrr for 2026-Q1 is 114.0%
- **Time:** 621ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_percent: has percentage

### 15. B5: quota attainment — PASS
- **Persona:** CRO
- **Query:** "Are we hitting quota?"
- **Answer:** Yes, 0% attainment
- **Time:** 678ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_percent: has percentage | OK mentions_any: found: ['attainment']

### 16. B6: sales cycle — FAIL
- **Persona:** CRO
- **Query:** "How long is our sales cycle?"
- **Answer:** Revenue for 2026-Q1 is $35.6M
- **Time:** 598ms
- **Checks:** OK has_data: has data | OK professional: professional | FAIL mentions_any: none of ['days', 'cycle'] found

### 17. B7: bookings last quarter — FAIL
- **Persona:** CRO
- **Query:** "What did we book last quarter?"
- **Answer:** I'm stumped! But I can definitely help with:
• Financial metrics (revenue, margin, profit)
• Sales metrics (pipeline, bookings, win rate)
• Or try 'show me KPIs'

⚠️ Possible insufficient data condition (50% confidence)
- **Time:** 5424ms
- **Checks:** FAIL has_data: contains 'i'm stumped' | OK professional: professional | OK mentions_any: found: ['booking']

### 18. B8: customer count — PASS
- **Persona:** CRO
- **Query:** "How many customers do we have?"
- **Answer:** Customer Count for 2026-Q1 is 3336.0
- **Time:** 958ms
- **Checks:** OK has_data: has data | OK professional: professional

### 19. B9: expansion revenue — PASS
- **Persona:** CRO
- **Query:** "What's our expansion revenue?"
- **Answer:** I'm stumped! But I can definitely help with:
• Financial metrics (revenue, margin, profit)
• Sales metrics (pipeline, bookings, win rate)
• Or try 'show me KPIs'

⚠️ Possible insufficient data condition (50% confidence)
- **Time:** 4771ms
- **Checks:** OK professional: professional | OK responsive: 4771ms

### 20. B10: sales scorecard — PASS
- **Persona:** CRO
- **Query:** "Show me the sales scorecard"
- **Answer:** Here's a dashboard showing Accounts Receivable & Pipeline Dashboard
- **Time:** 1237ms
- **Checks:** OK professional: professional | OK responsive: 1237ms | OK has_data_or_dashboard: is dashboard

---
## C: COO/CTO/CHRO Queries (7/10)

### 21. C1: headcount — PASS
- **Persona:** COO
- **Query:** "What's our headcount?"
- **Answer:** Headcount for 2026-Q1 is 373.0
- **Time:** 745ms
- **Checks:** OK has_data: has data | OK professional: professional

### 22. C2: revenue per employee — PASS
- **Persona:** COO
- **Query:** "Revenue per employee?"
- **Answer:** Revenue Per Employee for 2026-Q1 is $106.8M
- **Time:** 593ms
- **Checks:** OK has_data: has data | OK professional: professional | OK mentions_any: found: ['per employee', '$']

### 23. C3: platform uptime — PASS
- **Persona:** CTO
- **Query:** "What's platform uptime?"
- **Answer:** Uptime Pct for 2026-Q1 is 99.6%
- **Time:** 615ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_percent: has percentage

### 24. C4: P1 incidents — PASS
- **Persona:** CTO
- **Query:** "How many P1 incidents this quarter?"
- **Answer:** P1 Incidents for 2026-Q1 is 3.0
- **Time:** 720ms
- **Checks:** OK has_data: has data | OK professional: professional | OK not_about: on topic

### 25. C5: MTTR — FAIL
- **Persona:** CTO
- **Query:** "What's our MTTR?"
- **Answer:** I recognize **Mttr P1 Hours** (Mean time to recover from P1), but I don't have data for it right now. This may indicate missing data in the current dataset for metric `mttr_p1_hours`.
- **Time:** 695ms
- **Checks:** FAIL has_data: contains 'don't have data' | OK professional: professional | OK mentions_any: found: ['hours', 'time']

### 26. C6: attrition — PASS
- **Persona:** CHRO
- **Query:** "What's attrition looking like?"
- **Answer:** Attrition Rate Pct for 2026-Q1 is 11.0%
- **Time:** 643ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_percent: has percentage

### 27. C7: employee engagement — PASS
- **Persona:** CHRO
- **Query:** "How's employee engagement?"
- **Answer:** Employee Engagement for 2026-Q1 is 84.6
- **Time:** 593ms
- **Checks:** OK has_data: has data | OK professional: professional

### 28. C8: open roles — FAIL
- **Persona:** CHRO
- **Query:** "How many open roles do we have?"
- **Answer:** 
- **Time:** 1198ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional

### 29. C9: time to hire — FAIL
- **Persona:** CHRO
- **Query:** "What's our time to hire?"
- **Answer:** Throughput for 2026-Q1 is 8,533
- **Time:** 933ms
- **Checks:** OK has_data: has data | OK professional: professional | FAIL mentions_any: none of ['days', 'time', 'hire'] found

### 30. C10: deployment frequency — PASS
- **Persona:** CTO
- **Query:** "Deployment frequency this quarter?"
- **Answer:** 0/week (2026 target)
- **Time:** 1090ms
- **Checks:** OK has_data: has data | OK professional: professional

---
## D: Dashboards That Work (2/10)

### 31. D1: CFO dashboard — FAIL
- **Persona:** CFO
- **Query:** "Build me a CFO dashboard"
- **Answer:** Here's a dashboard showing CFO Dashboard
- **Time:** 1187ms
- **Checks:** OK is_dashboard: is dashboard | FAIL no_empty_widgets: dashboard has 'No data' widgets | OK responsive: 1187ms

### 32. D2: CRO dashboard — FAIL
- **Persona:** CRO
- **Query:** "Build me a CRO dashboard"
- **Answer:** Here's a dashboard showing CRO Dashboard
- **Time:** 1003ms
- **Checks:** OK is_dashboard: is dashboard | FAIL no_empty_widgets: dashboard has 'No data' widgets | OK responsive: 1003ms

### 33. D3: COO dashboard — FAIL
- **Persona:** COO
- **Query:** "Build me a COO dashboard"
- **Answer:** Here's a dashboard showing Operations Dashboard
- **Time:** 625ms
- **Checks:** OK is_dashboard: is dashboard | FAIL no_empty_widgets: dashboard has 'No data' widgets | OK responsive: 625ms

### 34. D4: CTO dashboard — FAIL
- **Persona:** CTO
- **Query:** "Build me a CTO dashboard"
- **Answer:** Here's a dashboard showing CTO Dashboard
- **Time:** 745ms
- **Checks:** OK is_dashboard: is dashboard | FAIL no_empty_widgets: dashboard has 'No data' widgets | OK responsive: 745ms

### 35. D5: CHRO dashboard — FAIL
- **Persona:** CHRO
- **Query:** "Build me a CHRO dashboard"
- **Answer:** Here's a dashboard showing Executive Dashboard
- **Time:** 747ms
- **Checks:** OK is_dashboard: is dashboard | FAIL no_empty_widgets: dashboard has 'No data' widgets | OK responsive: 747ms

### 36. D6: how are we doing (CFO) — FAIL
- **Persona:** CFO
- **Query:** "How are we doing?"
- **Answer:** Here's a dashboard showing Revenue & Gross Margin Dashboard
- **Time:** 1500ms
- **Checks:** OK is_dashboard: is dashboard | FAIL no_empty_widgets: dashboard has 'No data' widgets | OK responsive: 1500ms

### 37. D7: how are we doing (CRO) — FAIL
- **Persona:** CRO
- **Query:** "How are we doing?"
- **Answer:** Here's a dashboard showing Pipeline & Win Rate Pct Dashboard
- **Time:** 774ms
- **Checks:** OK is_dashboard: is dashboard | FAIL no_empty_widgets: dashboard has 'No data' widgets | OK responsive: 774ms

### 38. D8: how are we doing (COO) — FAIL
- **Persona:** COO
- **Query:** "How are we doing?"
- **Answer:** Here's a dashboard showing Headcount & Revenue Per Employee Dashboard
- **Time:** 752ms
- **Checks:** OK is_dashboard: is dashboard | FAIL no_empty_widgets: dashboard has 'No data' widgets | OK responsive: 752ms

### 39. D9: 2025 KPIs dashboard — PASS
- **Persona:** CFO
- **Query:** "2025 KPIs in a dashboard"
- **Answer:** Here's a dashboard showing 2025 CFO Dashboard
- **Time:** 854ms
- **Checks:** OK is_dashboard: is dashboard | OK responsive: 854ms

### 40. D10: executive summary — PASS
- **Persona:** CFO
- **Query:** "Show me the executive summary"
- **Answer:** Here's a dashboard showing Revenue & Gross Margin Dashboard
- **Time:** 750ms
- **Checks:** OK has_data_or_dashboard: is dashboard | OK professional: professional | OK responsive: 750ms

---
## E: Comparisons and Trends (5/15)

### 41. E1: Q1 vs Q2 revenue — FAIL
- **Persona:** CFO
- **Query:** "Compare Q1 vs Q2 2025 revenue"
- **Answer:** Here's a dashboard showing Revenue & Gross Margin Dashboard
- **Time:** 1003ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | FAIL multi_value: only 0 distinct number(s)

### 42. E2: revenue trend this year — PASS
- **Persona:** CFO
- **Query:** "How has revenue trended this year?"
- **Answer:** Here's a dashboard showing Revenue & Accounts Receivable Over Time
- **Time:** 747ms
- **Checks:** OK has_data_or_dashboard: is dashboard | OK professional: professional | OK responsive: 747ms

### 43. E3: revenue growth YoY — FAIL
- **Persona:** CFO
- **Query:** "Revenue growth year over year"
- **Answer:** I'm not sure what you mean, but here are some things I'm great at:
• 'What's revenue?'
• 'How's pipeline looking?'
• 'Show me the CFO dashboard'

⚠️ Possible insufficient data condition (50% confidence)
- **Time:** 4251ms
- **Checks:** FAIL has_data: contains 'i'm not sure' | OK professional: professional | OK mentions_any: found: ['%']

### 44. E4: gross vs net margin — FAIL
- **Persona:** CFO
- **Query:** "Compare gross vs net margin"
- **Answer:** Here's a dashboard showing Gross Margin & Net Margin Pct Dashboard
- **Time:** 869ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | FAIL multi_value: only 0 distinct number(s) | FAIL has_percent: missing % sign

### 45. E5: margin this vs last quarter — FAIL
- **Persona:** CFO
- **Query:** "Margin this quarter vs last"
- **Answer:** Query interpreted with multiple possibilities.
- **Time:** 1296ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | FAIL multi_value: only 0 distinct number(s) | FAIL has_percent: missing % sign

### 46. E6: pipeline change this year — FAIL
- **Persona:** CRO
- **Query:** "How has pipeline changed this year?"
- **Answer:** Hmm, that's a head-scratcher. Try asking me about:
• Revenue, bookings, or ARR
• Pipeline or churn
• Any of the dashboards (CFO, CRO, COO, CTO)

⚠️ Possible insufficient data condition (50% confidence)
- **Time:** 1588ms
- **Checks:** FAIL has_data_or_dashboard: neither dashboard nor data: contains 'head-scratcher' | OK professional: professional | OK responsive: 1588ms

### 47. E7: revenue direction — FAIL
- **Persona:** CFO
- **Query:** "Is revenue going up or down?"
- **Answer:** Query interpreted with multiple possibilities.
- **Time:** 928ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | FAIL indicates_direction: no directional language

### 48. E8: churn rate last 3 quarters — PASS
- **Persona:** CRO
- **Query:** "Churn rate last 3 quarters"
- **Answer:** Churn Rate Pct has been decreasing (-6.1% change over 8 periods)
- **Time:** 1976ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_percent: has percentage

### 49. E9: ARR trend since Q1 2025 — PASS
- **Persona:** CFO
- **Query:** "ARR trend since Q1 2025"
- **Answer:** Here's a dashboard showing Arr & Retained Earnings Over Time
- **Time:** 747ms
- **Checks:** OK has_data_or_dashboard: is dashboard | OK professional: professional | OK responsive: 747ms

### 50. E10: bookings this vs last year — FAIL
- **Persona:** CRO
- **Query:** "Bookings this year vs last year"
- **Answer:** Query interpreted with multiple possibilities.
- **Time:** 1365ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | OK responsive: 1365ms

### 51. E11: best revenue quarter — FAIL
- **Persona:** CFO
- **Query:** "Which quarter had the best revenue?"
- **Answer:** Revenue data ranked by rep is not available in the current data connection. This ranking requires dimensional data that has not been materialized in DCL.
- **Time:** 288ms
- **Checks:** FAIL has_data: contains 'not available' | OK professional: professional | FAIL mentions_any: none of ['q1', 'q2', 'q3', 'q4'] found

### 52. E12: headcount growth YoY — FAIL
- **Persona:** COO
- **Query:** "Year over year headcount growth"
- **Answer:** Hmm, that's a head-scratcher. Try asking me about:
• Revenue, bookings, or ARR
• Pipeline or churn
• Any of the dashboards (CFO, CRO, COO, CTO)

⚠️ Possible insufficient data condition (50% confidence)
- **Time:** 4142ms
- **Checks:** FAIL has_data: contains 'head-scratcher' | OK professional: professional | OK responsive: 4142ms

### 53. E13: pipeline trend 4 quarters — PASS
- **Persona:** CRO
- **Query:** "Pipeline trend last 4 quarters"
- **Answer:** Here's a dashboard showing Pipeline & Rule Of 40 Over Time
- **Time:** 900ms
- **Checks:** OK has_data_or_dashboard: is dashboard | OK professional: professional | OK responsive: 900ms

### 54. E14: margins 2024 to 2025 — FAIL
- **Persona:** CFO
- **Query:** "How did margins change from 2024 to 2025?"
- **Answer:** Margin data not available
- **Time:** 836ms
- **Checks:** FAIL has_data: contains 'not available' | OK professional: professional | FAIL has_percent: missing % sign

### 55. E15: NRR trend — PASS
- **Persona:** CRO
- **Query:** "NRR trend"
- **Answer:** Here's a dashboard showing Nrr & Pipeline Over Time
- **Time:** 710ms
- **Checks:** OK has_data_or_dashboard: is dashboard | OK professional: professional | OK responsive: 710ms

---
## F: Causal and Analytical (8/10)

### 56. F1: why did revenue increase — PASS
- **Persona:** CFO
- **Query:** "Why did revenue increase?"
- **Answer:** Breakdown for 2026-Q1: Revenue: $35.6M
- **Time:** 2270ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 2270ms | OK not_about: on topic

### 57. F2: margin improvement driver — PASS
- **Persona:** CFO
- **Query:** "What's driving margin improvement?"
- **Answer:** Breakdown for 2026-Q1: Revenue: 35.6%, Cogs: 11.9%, Cloud Spend: 4.1%
- **Time:** 4324ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 4324ms

### 58. F3: biggest cost driver — FAIL
- **Persona:** CFO
- **Query:** "What's our biggest cost driver?"
- **Answer:** Quota Attainment data ranked by rep is not available in the current data connection. This ranking requires dimensional data that has not been materialized in DCL.
- **Time:** 794ms
- **Checks:** FAIL has_data: contains 'not available' | OK professional: professional | FAIL mentions_any: none of ['cost', 'cogs', 'opex', 'expense'] found

### 59. F4: why is churn going up — PASS
- **Persona:** CRO
- **Query:** "Why is churn going up?"
- **Answer:** Breakdown for 2026-Q1: Ar: 177.8%
- **Time:** 4484ms
- **Checks:** OK professional: professional | OK responsive: 4484ms

### 60. F5: win rate impact — PASS
- **Persona:** CRO
- **Query:** "What's impacting win rate?"
- **Answer:** Win Rate Pct for 2026-Q1 is 40.0%
- **Time:** 815ms
- **Checks:** OK professional: professional | OK responsive: 815ms

### 61. F6: revenue by segment — FAIL
- **Persona:** CRO
- **Query:** "Break down revenue by segment"
- **Answer:** 
- **Time:** 688ms
- **Checks:** FAIL has_data_or_professional: no data and not a professional explanation | OK responsive: 688ms

### 62. F7: top performing region — PASS
- **Persona:** CRO
- **Query:** "Top performing region"
- **Answer:** Revenue data ranked by region is not available in the current data connection. This ranking requires dimensional data that has not been materialized in DCL.
- **Time:** 702ms
- **Checks:** OK has_data_or_professional: professional explanation (no raw data) | OK responsive: 702ms

### 63. F8: highest attrition dept — PASS
- **Persona:** CHRO
- **Query:** "Which department has the highest attrition?"
- **Answer:** Attrition Rate data ranked by department is not available in the current data connection. This ranking requires dimensional data that has not been materialized in DCL.
- **Time:** 892ms
- **Checks:** OK has_data_or_professional: professional explanation (no raw data) | OK responsive: 892ms

### 64. F9: biggest risk — PASS
- **Persona:** CFO
- **Query:** "What's the biggest risk to the business?"
- **Answer:** Quota Attainment data ranked by rep is not available in the current data connection. This ranking requires dimensional data that has not been materialized in DCL.
- **Time:** 576ms
- **Checks:** OK professional: professional | OK responsive: 576ms | OK has_data_or_guidance: thoughtful guidance

### 65. F10: what to focus on — PASS
- **Persona:** CFO
- **Query:** "What should I focus on this quarter?"
- **Answer:** Breakdown for 2026-Q1: Revenue: 35.57, Pipeline: 177.85, Cash: 148.0, Customer Count: 3336.0
- **Time:** 5218ms
- **Checks:** OK professional: professional | OK responsive: 5218ms | OK has_data_or_guidance: has data

---
## G: P&L and Financials (7/10)

### 66. G1: show P&L — PASS
- **Persona:** CFO
- **Query:** "Show me the P&L"
- **Answer:** **P&L Statement — 2026-Q1**

  Revenue: $35.6M
  COGS: $11.9M
  Gross Profit: $23.6M
  Gross Margin: 66.4%
  Opex: $10.7M
  EBITDA: $14.2M
  EBITDA Margin: 39.9%
  Operating Profit: $13.0M
  Net Income: $9.7M
  Net Margin Pct: 27.3%
- **Time:** 1199ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 1199ms | OK mentions_all: contains all: ['revenue', 'gross'] | OK multi_value: 12 distinct values

### 67. G2: full P&L 2025 — PASS
- **Persona:** CFO
- **Query:** "Full P&L for 2025"
- **Answer:** 2026: Revenue $0M, COGS $0M, Gross Profit $0M, SG&A $0M, Operating Profit $0M, Net Income $0M
- **Time:** 1755ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 1755ms | OK mentions_any: found: ['revenue', 'cogs', 'gross'] | OK multi_value: 2 distinct values

### 68. G3: P&L Q1 2026 — PASS
- **Persona:** CFO
- **Query:** "P&L for Q1 2026"
- **Answer:** **P&L Statement — 2026-Q1**

  Revenue: $35.6M
  COGS: $11.9M
  Gross Profit: $23.6M
  Gross Margin: 66.4%
  Opex: $10.7M
  EBITDA: $14.2M
  EBITDA Margin: 39.9%
  Operating Profit: $13.0M
  Net Income: $9.7M
  Net Margin Pct: 27.3%
- **Time:** 1267ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 1267ms | OK multi_value: 12 distinct values

### 69. G4: all margins — FAIL
- **Persona:** CFO
- **Query:** "Show me all the margins"
- **Answer:** Margin data not available
- **Time:** 819ms
- **Checks:** FAIL has_data: contains 'not available' | OK professional: professional | FAIL has_percent: missing % sign | FAIL mentions_all: missing: ['gross', 'operating', 'net']

### 70. G5: gross margin trend — PASS
- **Persona:** CFO
- **Query:** "What's the gross margin trend?"
- **Answer:** Here's a dashboard showing Gross Margin & Revenue Over Time
- **Time:** 865ms
- **Checks:** OK has_data_or_dashboard: is dashboard | OK professional: professional | OK responsive: 865ms

### 71. G6: revenue COGS gross profit — PASS
- **Persona:** CFO
- **Query:** "Revenue, COGS, and gross profit"
- **Answer:** COGS for 2026-Q1 is $11.9M
- **Time:** 725ms
- **Checks:** OK has_data: has data | OK professional: professional | OK multi_value: 3 distinct values | OK has_dollar: has dollar sign

### 72. G7: opex breakdown — FAIL
- **Persona:** CFO
- **Query:** "Operating expenses breakdown"
- **Answer:** Here's a dashboard showing Opex & Revenue Dashboard
- **Time:** 753ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | OK responsive: 753ms

### 73. G8: EBITDA and net income — PASS
- **Persona:** CFO
- **Query:** "EBITDA and net income"
- **Answer:** Revenue for 2026-Q1 is $35.6M
- **Time:** 659ms
- **Checks:** OK has_data: has data | OK professional: professional | OK multi_value: 3 distinct values | OK has_dollar: has dollar sign

### 74. G9: financial health — FAIL
- **Persona:** CFO
- **Query:** "What's our financial health?"
- **Answer:** Financial health data not available
- **Time:** 835ms
- **Checks:** FAIL has_data: contains 'not available' | OK professional: professional | OK responsive: 835ms | FAIL mentions_any: none of ['revenue', 'margin', 'profit', 'cash'] found

### 75. G10: board deck metrics — PASS
- **Persona:** CFO
- **Query:** "Board deck metrics"
- **Answer:** **CFO Dashboard (2026-Q1)**
Revenue: $NoneM | Gross Margin: None%
Operating Margin: None% | Net Income: $NoneM
Cash: $NoneM | ARR: $NoneM | Burn: Nonex
- **Time:** 1748ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 1748ms | OK multi_value: 2 distinct values

---
## H: Demo Showstoppers (11/15)

### 76. H1: quick overview — FAIL
- **Persona:** CFO
- **Query:** "Give me a quick overview"
- **Answer:** Here's a dashboard showing Revenue & Gross Margin Dashboard
- **Time:** 1003ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | OK responsive: 1003ms | FAIL multi_value: only 0 distinct number(s)

### 77. H2: how's the business — PASS
- **Persona:** CFO
- **Query:** "How's the business doing?"
- **Answer:** Here's a dashboard showing New Logo Arr & Revenue Dashboard
- **Time:** 1002ms
- **Checks:** OK has_data_or_dashboard: is dashboard | OK professional: professional | OK responsive: 1002ms

### 78. H3: what should I worry about — PASS
- **Persona:** CFO
- **Query:** "What should I worry about?"
- **Answer:** Breakdown for 2026-Q1: Churn Risk: 12.96
- **Time:** 3631ms
- **Checks:** OK professional: professional | OK responsive: 3631ms | OK has_data_or_guidance: has data

### 79. H4: TL;DR — PASS
- **Persona:** CFO
- **Query:** "Give me the TL;DR"
- **Answer:** Revenue for 2026-Q1 was $35.6M
- **Time:** 4206ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 4206ms

### 80. H5: KPIs — FAIL
- **Persona:** CFO
- **Query:** "What are our KPIs?"
- **Answer:** Here's a dashboard showing Revenue & Gross Margin Dashboard
- **Time:** 1189ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | OK responsive: 1189ms

### 81. H6: show me something interesting — PASS
- **Persona:** CFO
- **Query:** "Show me something interesting"
- **Answer:** Here's a dashboard showing Revenue & Gross Margin Dashboard
- **Time:** 1053ms
- **Checks:** OK professional: professional | OK responsive: 1053ms

### 82. H7: last quarter — PASS
- **Persona:** CFO
- **Query:** "How did last quarter go?"
- **Answer:** Accounts Receivable for 2025-Q4 is $168.9M
- **Time:** 962ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 962ms | OK multi_value: 3 distinct values

### 83. H8: what changed since last quarter — FAIL
- **Persona:** CFO
- **Query:** "What's changed since last quarter?"
- **Answer:** 
- **Time:** 2544ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | OK responsive: 2544ms | FAIL indicates_direction: no directional language

### 84. H9: are we on track — FAIL
- **Persona:** CFO
- **Query:** "Are we on track?"
- **Answer:** Compared to what benchmark?
- **Time:** 972ms
- **Checks:** FAIL has_data: no numeric data in answer | OK professional: professional | OK responsive: 972ms

### 85. H10: what does the data tell us — PASS
- **Persona:** CFO
- **Query:** "What does the data tell us?"
- **Answer:** Employee Engagement for 2026-Q1 is 84.6
- **Time:** 589ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 589ms

### 86. H11: run through the numbers — PASS
- **Persona:** CFO
- **Query:** "Run me through the numbers"
- **Answer:** Revenue has been increasing (+56.0% change over 8 periods)
- **Time:** 3899ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 3899ms | OK multi_value: 2 distinct values

### 87. H12: new CRO catch me up — PASS
- **Persona:** CRO
- **Query:** "I'm the new CRO, catch me up"
- **Answer:** Breakdown for 2026-Q1: Pipeline: $177.9M, Win Rate Pct: $40.0M, Sales Cycle Days: $86.0M, Quota Attainment Pct: $89.3M, Nrr: $114.0M, Churn Rate Pct: $7.2M
- **Time:** 5425ms
- **Checks:** OK has_data_or_dashboard: has data | OK professional: professional | OK responsive: 5425ms

### 88. H13: quick health check — PASS
- **Persona:** CFO
- **Query:** "Quick health check"
- **Answer:** Revenue for 2026-Q1 was $35.6M
- **Time:** 5242ms
- **Checks:** OK has_data: has data | OK professional: professional | OK responsive: 5242ms

### 89. H14: anything unusual — PASS
- **Persona:** CFO
- **Query:** "Anything unusual in the data?"
- **Answer:** Revenue has been increasing (+56.0% change over 8 periods)
- **Time:** 4264ms
- **Checks:** OK professional: professional | OK responsive: 4264ms

### 90. H15: let's start with revenue — PASS
- **Persona:** CFO
- **Query:** "Let's start with revenue"
- **Answer:** Accounts Receivable for 2026-Q1 is $177.8M
- **Time:** 601ms
- **Checks:** OK has_data: has data | OK professional: professional | OK has_dollar: has dollar sign | OK responsive: 601ms

---
## I: Edge Cases (10/10)

### 91. I1: hi — PASS
- **Persona:** ---
- **Query:** "hi"
- **Answer:** I was built for this. Don't let my GPU cycles go to waste.
- **Time:** 117ms
- **Checks:** OK professional: professional | OK responsive: 117ms | OK no_crash: no crash

### 92. I2: thanks — PASS
- **Persona:** ---
- **Query:** "thanks"
- **Answer:** Thanks! Now, what metric do you need?
- **Time:** 121ms
- **Checks:** OK professional: professional | OK responsive: 121ms | OK no_crash: no crash

### 93. I3: go back — PASS
- **Persona:** ---
- **Query:** "go back"
- **Answer:** 
- **Time:** 4437ms
- **Checks:** OK professional: professional | OK responsive: 4437ms | OK no_crash: no crash

### 94. I4: more detail — PASS
- **Persona:** CFO
- **Query:** "more detail"
- **Answer:** 
- **Time:** 8304ms
- **Checks:** OK professional: professional | OK responsive: 8304ms | OK no_crash: no crash

### 95. I5: can you explain that — PASS
- **Persona:** CFO
- **Query:** "can you explain that?"
- **Answer:** 
- **Time:** 2715ms
- **Checks:** OK professional: professional | OK responsive: 2715ms | OK no_crash: no crash

### 96. I6: what about last year — PASS
- **Persona:** CFO
- **Query:** "what about last year?"
- **Answer:** 
- **Time:** 2527ms
- **Checks:** OK professional: professional | OK responsive: 2527ms

### 97. I7: break that down — PASS
- **Persona:** CFO
- **Query:** "break that down"
- **Answer:** Ar Aging for 2026-Q1 is 177.8
- **Time:** 693ms
- **Checks:** OK professional: professional | OK responsive: 693ms

### 98. I8: that doesn't look right — PASS
- **Persona:** CFO
- **Query:** "hmm that doesn't look right"
- **Answer:** 
- **Time:** 4229ms
- **Checks:** OK professional: professional | OK responsive: 4229ms

### 99. I9: show me more — PASS
- **Persona:** CFO
- **Query:** "show me more"
- **Answer:** Here's a dashboard showing Revenue & Gross Margin Dashboard
- **Time:** 842ms
- **Checks:** OK professional: professional | OK responsive: 842ms

### 100. I10: actually show CRO metrics — PASS
- **Persona:** CRO
- **Query:** "actually show me CRO metrics"
- **Answer:** Here's a dashboard showing Pipeline & Win Rate Pct Dashboard
- **Time:** 1083ms
- **Checks:** OK professional: professional | OK responsive: 1083ms | OK mentions_any: found: ['pipeline', 'win']
