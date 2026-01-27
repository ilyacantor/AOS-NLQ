# NLQ Ambiguous Questions - Ground Truth Reference

**Context**: Reference date is January 27, 2026 (Q1 2026)

These questions reflect how humans actually ask things: incomplete sentences, casual language, vague references, implied context, and shorthand.

| # | Question | Ground Truth Answer | Ambiguity Type |
|---|----------|---------------------|----------------|
| 56 | rev? | $200.0M | Incomplete - assumes current year |
| 57 | how'd we do last year | $150.0M revenue, $28.13M net income | Vague metric - provide key financials |
| 58 | whats the margin | Gross: 65.0%, Operating: 35.0%, Net: 22.5% | Vague metric - which margin? |
| 59 | q4 numbers | Q4 2025: Revenue $42.0M, Net Income $11.03M | Incomplete - assume most recent Q4 |
| 60 | are we profitable | Yes, 22.5% net margin in 2026 forecast | Yes/no with context |
| 61 | hows the top line looking | $200.0M forecast for 2026, up 33% from 2025 | Casual language - wants trend |
| 62 | give me the P&L | 2026: Revenue $200M, COGS $70M, Gross Profit $130M, SG&A $60M, Op Profit $70M, Net Income $45M | Broad request - full statement |
| 63 | did we hit 150 | Yes, 2025 revenue was exactly $150.0M | Implied context - 150 = revenue target |
| 64 | costs too high? | COGS 35% of revenue, SG&A 30% - consistent with targets | Judgment call |
| 65 | cash position | $41.42M as of Q4 2025 | Shorthand - two words, no verb |
| 66 | year over year | Revenue +50% (2024→2025), +33% (2025→2026F) | Incomplete - assume revenue |
| 67 | what about Q2 | Q2 2026 forecast: Revenue $48.0M, Net Income $12.6M | Context dependent - which Q2? |
| 68 | bookings vs revenue | Bookings 115% of revenue (2025: $172.5M vs $150M) | Comparison - wants ratio |
| 69 | where are we on AR | $20.71M as of Q4 2025, ~45 days sales outstanding | Casual language |
| 70 | quick ratio stuff | Current Assets $75.57M, Current Liabs $26.47M, Ratio ~2.9x | Vague request |
| 71 | 2025 in a nutshell | Revenue $150M (+50% YoY), Net Income $28.13M (18.8% margin), Op Margin 35% | Summary request |
| 72 | burn rate? | Not applicable - company is profitable with positive cash flow | Not applicable to dataset |
| 73 | opex breakdown pls | 2026: Selling $36M, G&A $24M, Total SG&A $60M | Casual with abbreviation |
| 74 | we growing? | Yes, 50% growth 2024→2025, 33% forecast 2025→2026 | Yes/no needing evidence |
| 75 | compare this year to last | 2026 vs 2025: Revenue $200M vs $150M (+33%), Net Income $45M vs $28.13M (+60%) | Comparison - comprehensive |

---

## Ambiguity Types Explained

| Type | Description | Example |
|------|-------------|---------|
| **Incomplete** | Missing metric, period, or both | "rev?" "q4 numbers" |
| **Vague metric** | Unclear which specific metric | "whats the margin" |
| **Casual language** | Informal, slang, abbreviations | "hows the top line looking" |
| **Yes/no** | Boolean question needing context | "are we profitable" |
| **Broad request** | Asking for multiple data points | "give me the P&L" |
| **Implied context** | References unstated assumptions | "did we hit 150" |
| **Judgment call** | Requires interpretation | "costs too high?" |
| **Shorthand** | Telegraphic, minimal words | "cash position" |
| **Context dependent** | Answer varies by current date | "what about Q2" |
| **Comparison** | Wants relationship, not raw numbers | "bookings vs revenue" |
| **Summary request** | Wants condensed overview | "2025 in a nutshell" |
| **Not applicable** | Question doesn't fit dataset | "burn rate?" |

---

## Handling Guidance for NLQ Engine

For ambiguous questions, the engine should:

1. **Make reasonable assumptions** based on context (current date, most recent data)
2. **Provide comprehensive answers** when metric is vague (give all margins, not just one)
3. **Answer yes/no questions with supporting data** (don't just say "yes")
4. **Handle "not applicable" gracefully** (explain why rather than error)
5. **Interpret casual language** ("how'd we do" = key performance metrics)
