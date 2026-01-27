# NLQ Engine - Advanced Intents Implementation

## Current State
- **POINT_QUERY** works: 46/55 questions (84%)
- **Missing**: 9 questions requiring multi-period or multi-metric logic

## Features to Add

| Intent | Questions | Core Logic |
|--------|-----------|------------|
| COMPARISON | Q33, Q34, Q35, Q36, Q37 | Fetch 2 periods, compute delta/growth |
| AGGREGATION | Q46, Q48 | Sum or average across periods |
| BREAKDOWN | Q52 | Return multiple related metrics |

---

## 1. COMPARISON Intent

### Pattern Detection
```python
COMPARISON_PATTERNS = [
    r"grow|growth|grew",
    r"change|changed",
    r"compare|comparison|vs|versus",
    r"improve|improved|decline|declined",
    r"yoy|year.over.year|y/y",
    r"from .* to .*",
    r"between .* and .*",
]
```

### Data Structure
```python
class ComparisonQuery(BaseModel):
    metric: str
    period_from: ResolvedPeriod  # e.g., 2024 or Q4 2024
    period_to: ResolvedPeriod    # e.g., 2025 or Q4 2025
    comparison_type: Literal["absolute", "percentage", "direction"]
```

### Execution Logic
```python
def execute_comparison(query: ComparisonQuery, fact_base: FactBase) -> ComparisonResult:
    # Fetch both values
    value_from = fact_base.query(query.metric, query.period_from)
    value_to = fact_base.query(query.metric, query.period_to)
    
    # Compute deltas
    absolute_change = value_to - value_from
    if value_from != 0:
        percentage_change = ((value_to - value_from) / value_from) * 100
    else:
        percentage_change = None
    
    # Determine direction
    if absolute_change > 0:
        direction = "increased"
    elif absolute_change < 0:
        direction = "decreased"
    else:
        direction = "unchanged"
    
    return ComparisonResult(
        metric=query.metric,
        period_from=query.period_from,
        period_to=query.period_to,
        value_from=value_from,
        value_to=value_to,
        absolute_change=absolute_change,
        percentage_change=percentage_change,
        direction=direction
    )
```

### Response Formatting
```python
def format_comparison_response(result: ComparisonResult, question_type: str) -> str:
    if question_type == "growth_amount":
        # Q33: "How much did revenue grow from 2024 to 2025?"
        return f"${abs(result.absolute_change)}M ({abs(result.percentage_change):.0f}%)"
    
    elif question_type == "growth_percentage":
        # Q34: "What was YoY revenue growth in 2025?"
        return f"{result.percentage_change:.0f}%"
    
    elif question_type == "change_description":
        # Q35: "How did net income change from 2024 to 2025?"
        return f"{result.direction.capitalize()} from ${result.value_from}M to ${result.value_to}M"
    
    elif question_type == "side_by_side":
        # Q36: "Compare Q4 2024 to Q4 2025 revenue"
        pct = f" ({abs(result.percentage_change):.0f}% {'increase' if result.percentage_change > 0 else 'decrease'})"
        return f"{result.period_from}: ${result.value_from}M, {result.period_to}: ${result.value_to}M{pct}"
    
    elif question_type == "boolean_trend":
        # Q37: "Did operating margin improve from 2024 to 2025?"
        improved = result.absolute_change > 0
        answer = "Yes" if improved else "No"
        return f"{answer}, {'improved' if improved else 'declined'} from {result.value_from}% to {result.value_to}%"
```

### Question → Type Mapping
```python
def classify_comparison_type(question: str) -> str:
    q = question.lower()
    
    if "how much" in q and ("grow" in q or "change" in q):
        return "growth_amount"
    
    if "yoy" in q or "year over year" in q or "growth" in q and "%" not in q:
        if "what was" in q:
            return "growth_percentage"
    
    if "how did" in q and "change" in q:
        return "change_description"
    
    if "compare" in q:
        return "side_by_side"
    
    if q.startswith("did") or q.startswith("has") or "improve" in q or "decline" in q:
        return "boolean_trend"
    
    return "side_by_side"  # Default
```

---

## 2. AGGREGATION Intent

### Pattern Detection
```python
AGGREGATION_PATTERNS = [
    r"total .* for (h1|h2|first half|second half)",
    r"average|avg|mean",
    r"sum of",
    r"combined",
    r"h1|h2|first half|second half",
]
```

### Data Structure
```python
class AggregationQuery(BaseModel):
    metric: str
    aggregation_type: Literal["sum", "average"]
    periods: List[ResolvedPeriod]  # e.g., [Q1 2025, Q2 2025] for H1
```

### Period Expansion
```python
def expand_period(period_ref: str, year: int) -> List[ResolvedPeriod]:
    """Expand shorthand periods to list of quarters."""
    
    if period_ref.lower() in ["h1", "first half"]:
        return [
            ResolvedPeriod(type="quarterly", year=year, quarter=1),
            ResolvedPeriod(type="quarterly", year=year, quarter=2),
        ]
    
    elif period_ref.lower() in ["h2", "second half"]:
        return [
            ResolvedPeriod(type="quarterly", year=year, quarter=3),
            ResolvedPeriod(type="quarterly", year=year, quarter=4),
        ]
    
    elif period_ref.lower() in ["full year", "annual", "all quarters"]:
        return [
            ResolvedPeriod(type="quarterly", year=year, quarter=q)
            for q in [1, 2, 3, 4]
        ]
    
    return []
```

### Execution Logic
```python
def execute_aggregation(query: AggregationQuery, fact_base: FactBase) -> AggregationResult:
    # Fetch all period values
    values = []
    for period in query.periods:
        value = fact_base.query(query.metric, period)
        if value is not None:
            values.append(value)
    
    if not values:
        return AggregationResult(success=False, error="NO_DATA")
    
    # Compute aggregate
    if query.aggregation_type == "sum":
        result_value = sum(values)
    elif query.aggregation_type == "average":
        result_value = sum(values) / len(values)
    
    return AggregationResult(
        metric=query.metric,
        aggregation_type=query.aggregation_type,
        periods=query.periods,
        individual_values=values,
        result=result_value
    )
```

### Response Formatting
```python
def format_aggregation_response(result: AggregationResult) -> str:
    if result.aggregation_type == "sum":
        # Q46: "What was total revenue for H1 2025?"
        return f"${result.result}M"
    
    elif result.aggregation_type == "average":
        # Q48: "What was average quarterly revenue in 2025?"
        return f"${result.result}M"
```

---

## 3. BREAKDOWN Intent

### Pattern Detection
```python
BREAKDOWN_PATTERNS = [
    r"break.?down",
    r"breakdown",
    r"split|decompose",
    r"what (are|were) the components",
    r"show .* by",
]
```

### Metric Groups
```python
METRIC_BREAKDOWNS = {
    "operating_expenses": ["selling_expenses", "g_and_a_expenses", "sga"],
    "opex": ["selling_expenses", "g_and_a_expenses", "sga"],
    "sga": ["selling_expenses", "g_and_a_expenses", "sga"],
    "revenue_components": ["revenue", "bookings", "deferred_revenue"],
    "profitability": ["gross_profit", "operating_profit", "net_income"],
    "margins": ["gross_margin_pct", "operating_margin_pct", "net_income_pct"],
}

# Display names for breakdown items
BREAKDOWN_LABELS = {
    "selling_expenses": "Selling",
    "g_and_a_expenses": "G&A",
    "sga": "Total SG&A",
}
```

### Execution Logic
```python
def execute_breakdown(metric_group: str, period: ResolvedPeriod, fact_base: FactBase) -> BreakdownResult:
    components = METRIC_BREAKDOWNS.get(metric_group, [])
    
    if not components:
        return BreakdownResult(success=False, error="UNKNOWN_BREAKDOWN")
    
    results = {}
    for metric in components:
        value = fact_base.query(metric, period)
        if value is not None:
            label = BREAKDOWN_LABELS.get(metric, metric.replace("_", " ").title())
            results[label] = value
    
    return BreakdownResult(
        metric_group=metric_group,
        period=period,
        components=results
    )
```

### Response Formatting
```python
def format_breakdown_response(result: BreakdownResult) -> str:
    # Q52: "Break down operating expenses for 2025"
    # Output: "Selling: $27.0M, G&A: $18.0M, Total SG&A: $45.0M"
    
    parts = []
    for label, value in result.components.items():
        parts.append(f"{label}: ${value}M")
    
    return ", ".join(parts)
```

---

## Updated Intent Classification

```python
def classify_intent(question: str) -> str:
    q = question.lower()
    
    # Check COMPARISON first (most specific)
    for pattern in COMPARISON_PATTERNS:
        if re.search(pattern, q):
            return "COMPARISON"
    
    # Check AGGREGATION
    for pattern in AGGREGATION_PATTERNS:
        if re.search(pattern, q):
            return "AGGREGATION"
    
    # Check BREAKDOWN
    for pattern in BREAKDOWN_PATTERNS:
        if re.search(pattern, q):
            return "BREAKDOWN"
    
    # Default to POINT_QUERY
    return "POINT_QUERY"
```

---

## Updated Query Execution Router

```python
def execute_query(parsed: ParsedQuery, fact_base: FactBase) -> NLQResponse:
    intent = parsed.intent
    
    if intent == "POINT_QUERY":
        return execute_point_query(parsed, fact_base)
    
    elif intent == "COMPARISON":
        result = execute_comparison(parsed.comparison_query, fact_base)
        answer = format_comparison_response(result, parsed.comparison_type)
        return NLQResponse(
            success=True,
            answer=answer,
            confidence=bounded_confidence(0.95)
        )
    
    elif intent == "AGGREGATION":
        result = execute_aggregation(parsed.aggregation_query, fact_base)
        answer = format_aggregation_response(result)
        return NLQResponse(
            success=True,
            answer=answer,
            value=result.result,
            confidence=bounded_confidence(0.95)
        )
    
    elif intent == "BREAKDOWN":
        result = execute_breakdown(parsed.metric_group, parsed.period, fact_base)
        answer = format_breakdown_response(result)
        return NLQResponse(
            success=True,
            answer=answer,
            confidence=bounded_confidence(0.95)
        )
    
    return NLQResponse(success=False, error="UNKNOWN_INTENT")
```

---

## Claude Code Prompts

### Prompt: Add Comparison Intent
```
Add COMPARISON intent support to the NLQ engine.

1. Create src/nlq/core/comparison.py with:
   - ComparisonQuery model (metric, period_from, period_to, comparison_type)
   - ComparisonResult model (values, absolute_change, percentage_change, direction)
   - execute_comparison() function that fetches 2 periods and computes deltas
   - classify_comparison_type() to detect: growth_amount, growth_percentage, change_description, side_by_side, boolean_trend
   - format_comparison_response() to generate human-readable answers

2. Update intent classification to detect comparison patterns:
   - "grow/growth/grew", "change/changed", "compare/vs", "improve/decline", "yoy", "from X to Y"

3. Update query router to handle COMPARISON intent

4. Add tests for Q33, Q34, Q35, Q36, Q37 - all must pass with 100% accuracy
```

### Prompt: Add Aggregation Intent
```
Add AGGREGATION intent support to the NLQ engine.

1. Create src/nlq/core/aggregation.py with:
   - AggregationQuery model (metric, aggregation_type: sum|average, periods: list)
   - expand_period() to convert H1/H2 to list of quarters
   - execute_aggregation() that fetches multiple periods and computes sum/average
   - format_aggregation_response()

2. Update intent classification to detect aggregation patterns:
   - "total for H1/H2", "average/avg", "sum of", "combined"

3. Update query router to handle AGGREGATION intent

4. Add tests for Q46, Q48 - both must pass with 100% accuracy

Note: Q47 should already work since annual SG&A data exists - verify this.
```

### Prompt: Add Breakdown Intent
```
Add BREAKDOWN intent support to the NLQ engine.

1. Create src/nlq/core/breakdown.py with:
   - METRIC_BREAKDOWNS dict mapping group names to component metrics
   - BREAKDOWN_LABELS for display names
   - execute_breakdown() that fetches all components for a period
   - format_breakdown_response() that returns "Label1: $XM, Label2: $YM, ..."

2. Update intent classification to detect breakdown patterns:
   - "break down", "breakdown", "split", "components of"

3. Update query router to handle BREAKDOWN intent

4. Add test for Q52 - must pass with 100% accuracy

Breakdown mappings needed:
- operating_expenses/opex/sga → [selling_expenses, g_and_a_expenses, sga]
```

---

## Test Verification

After implementing all three intents, run:

```bash
pytest tests/test_e2e.py -v
```

Expected: 55/55 passing (100%)

If any fail, check:
1. Period parsing (especially "from 2024 to 2025" extraction)
2. Metric normalization (operating expenses → sga breakdown)
3. Response format matching ground truth exactly

---

## Ground Truth Reference (9 Questions)

| ID | Question | Expected Answer |
|----|----------|-----------------|
| Q33 | How much did revenue grow from 2024 to 2025? | $50.0M (50%) |
| Q34 | What was YoY revenue growth in 2025? | 50% |
| Q35 | How did net income change from 2024 to 2025? | Increased from $26.25M to $39.38M |
| Q36 | Compare Q4 2024 to Q4 2025 revenue | Q4 2024: $28.0M, Q4 2025: $42.0M (50% increase) |
| Q37 | Did operating margin improve from 2024 to 2025? | Yes, improved from 35.0% to 35.0% |
| Q46 | What was total revenue for H1 2025? | $69.0M |
| Q47 | What was total SG&A for all of 2025? | $45.0M |
| Q48 | What was average quarterly revenue in 2025? | $37.5M |
| Q52 | Break down operating expenses for 2025 | Selling: $27.0M, G&A: $18.0M, Total SG&A: $45.0M |

---

*Implementation Spec v1.0 - January 2026*
