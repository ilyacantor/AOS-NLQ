# NLQ Project - Claude Code Quick Start Prompts

Copy-paste these prompts into Claude Code sessions. Use in sequence for new project, or individually for specific tasks.

---

## SESSION OPENER (Use at start of every CC session)

```
I'm building aos-nlq, a standalone Natural Language Query engine for financial data. 

Key context:
- Python/FastAPI service, NOT part of DCL
- Uses Claude API (Anthropic) for query parsing
- I don't write code - you implement, I review
- Replit is my IDE

Critical requirements:
1. Confidence scores MUST be bounded [0.0, 1.0] - NEVER exceed 1.0
2. Relative dates ("last quarter") resolve from injected reference_date, not system time
3. Metric synonyms normalized (revenue = sales = top line)
4. Zero-row queries return explicit errors, not empty results

The project spec is in NLQ_Claude_Code_Project_Guide.md - reference it for structure and patterns.
```

---

## ACCURACY REQUIREMENT

**100% of ground truth questions must pass. No exceptions.**

If a test fails:
1. Fix the bug in the engine
2. If the question is genuinely ambiguous, fix the question  
3. Never lower the threshold

Financial queries have exact answers. A wrong answer is a bug, not an edge case.

---

## PHASE 1: PROJECT SETUP

### 1A. Create Structure
```
Create the aos-nlq project with this structure:
- src/nlq/ with subfolders: models/, core/, knowledge/, llm/, api/
- tests/
- data/
- scripts/

Create pyproject.toml with deps: fastapi, uvicorn, anthropic, pydantic, python-dotenv, pytest

Create .env.example with ANTHROPIC_API_KEY placeholder

Add __init__.py files. Create placeholder modules with docstrings explaining purpose.
```

### 1B. Create Models
```
Create src/nlq/models/query.py and response.py with Pydantic models:

NLQRequest:
- question: str (required)
- reference_date: Optional[date] (for relative period resolution)

NLQResponse:
- success: bool
- answer: Optional[str]
- value: Optional[Any]  
- unit: Optional[str]
- confidence: float = Field(ge=0.0, le=1.0)  # CRITICAL: bounded
- parsed_intent, resolved_metric, resolved_period: Optional[str]
- error_code, error_message: Optional[str]

Add JSON schema examples in Config.
```

---

## PHASE 2: CORE LOGIC

### 2A. Synonym Normalization
```
Create src/nlq/knowledge/synonyms.py

Define METRIC_SYNONYMS dict mapping canonical names to lists of synonyms:
- revenue: [sales, top line, turnover, topline, top-line]
- net_income: [profit, bottom line, earnings, net profit]
- operating_profit: [ebit, operating income, op profit]
- gross_profit: [gross income, gross margin dollars]  
- cogs: [cost of goods sold, cost of sales, cost of revenue, cos]
- sga: [sg&a, opex, operating expenses, selling general and administrative]

Define PERIOD_SYNONYMS:
- last_year: [prior year, previous year, year ago, ly]
- last_quarter: [prior quarter, previous quarter, quarter ago, lq]
- this_year: [current year, cy]
- this_quarter: [current quarter, cq]

Create normalize_metric(raw: str) -> str and normalize_period(raw: str) -> str functions.

Add tests in tests/test_synonyms.py covering all variations.
```

### 2B. Period Resolver
```
Create src/nlq/core/resolver.py

Class PeriodResolver:
- __init__(reference_date: date = None) - defaults to date.today()
- Properties: current_year, current_quarter (1-4)
- Method resolve(period_ref: str) -> dict with keys: type, year, quarter (if applicable)

Handle relative periods:
- last_year -> {type: "annual", year: current_year - 1}
- this_year -> {type: "annual", year: current_year}
- last_quarter -> previous quarter (Q1 wraps to Q4 of prior year)
- this_quarter -> {type: "quarterly", year: current_year, quarter: current_quarter}

Handle absolute periods:
- "2024" -> {type: "annual", year: 2024}
- "Q4 2025" or "2025-Q4" -> {type: "quarterly", year: 2025, quarter: 4}

Add tests with reference_date=2026-01-27 verifying last_year=2025, last_quarter=Q4 2025.
```

### 2C. Confidence Scoring
```
Create src/nlq/core/confidence.py

Function bounded_confidence(score: float) -> float:
- Return max(0.0, min(1.0, score))
- Handle edge cases: None->0, NaN->0, negative->0, >1->1

Class ConfidenceCalculator:
- Method calculate(intent_score: float, entity_score: float, data_score: float) -> float
- Weights: intent=0.4, entity=0.4, data=0.2
- ALWAYS return bounded result

Add tests proving confidence NEVER exceeds 1.0 even with inputs like (1.5, 2.0, 1.8).
```

---

## PHASE 3: CLAUDE INTEGRATION

### 3A. Prompts
```
Create src/nlq/llm/prompts.py

QUERY_PARSER_PROMPT = system prompt that instructs Claude to:
1. Extract intent: POINT_QUERY, COMPARISON_QUERY, TREND_QUERY, AGGREGATION_QUERY, BREAKDOWN_QUERY
2. Extract metric using canonical names (list them)
3. Extract period_type: annual, quarterly, half_year
4. Extract period_reference: the actual period mentioned
5. Determine is_relative: boolean

Response must be JSON only, no markdown, no explanation.

Include the full list of canonical metrics in the prompt.
```

### 3B. Client
```
Create src/nlq/llm/client.py

Class ClaudeClient:
- __init__(api_key: str) - create anthropic.Anthropic client
- model = "claude-sonnet-4-20250514"
- Method parse_query(question: str) -> dict
  - Call Claude with QUERY_PARSER_PROMPT as system, question as user message
  - Extract JSON from response, handling markdown code fences
  - Return parsed dict

Load API key from environment variable ANTHROPIC_API_KEY.
```

---

## PHASE 4: DATA & EXECUTION

### 4A. Fact Base
```
Create src/nlq/knowledge/fact_base.py

Class FactBase:
- load(filepath: str) - load JSON fact base
- available_metrics -> List[str]
- available_periods -> List[str]  
- has_period(period: str) -> bool
- query(metric: str, period: dict) -> Optional[float]
  - period dict has type, year, quarter
  - For annual: sum quarterly values or return annual value
  - For quarterly: return specific quarter value

Handle both formats in data: "2024" and "2024-Q1"
```

### 4B. Executor
```
Create src/nlq/core/executor.py

Class QueryExecutor:
- __init__(fact_base: FactBase)
- Method execute(parsed: dict, resolved_period: dict) -> NLQResponse

Execution flow:
1. Check metric exists -> if not, return error UNKNOWN_METRIC, confidence=0
2. Check period exists -> if not, return error NO_DATA_FOR_PERIOD, confidence=0
3. Query data -> if empty/None, return error EMPTY_RESULT, confidence=0
4. Success -> return value with bounded confidence

CRITICAL: Never return empty result silently. Always explicit error or valid data.
```

---

## PHASE 5: API & INTEGRATION

### 5A. API Routes
```
Create src/nlq/api/routes.py

FastAPI router with:
- POST /v1/query - accepts NLQRequest, returns NLQResponse
- GET /v1/health - returns {"status": "healthy", "version": "1.0.0"}
- GET /v1/schema - returns {"metrics": [...], "periods": [...]}

Query endpoint flow:
1. Parse question with ClaudeClient
2. Normalize metric with synonyms
3. Resolve period (use request.reference_date or today)
4. Execute query
5. Format and return response
```

### 5B. Main App
```
Create src/nlq/main.py

FastAPI app with:
- Include router from api/routes.py
- CORS middleware (allow all for dev)
- Startup event to load fact base
- Config from environment

Add run command for Replit: uvicorn src.nlq.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## PHASE 6: TESTING

### 6A. Unit Tests
```
Create tests for each module:
- tests/test_synonyms.py - all synonym variations
- tests/test_resolver.py - relative and absolute periods
- tests/test_confidence.py - bounded scoring
- tests/test_executor.py - error cases and success cases

Use pytest. Each test file should be runnable independently.
```

### 6B. End-to-End Tests
```
Create tests/test_e2e.py

Load data/test_questions.json (55 questions with ground truth)
For each question:
1. Call NLQ engine with reference_date=2026-01-27
2. Compare answer to ground truth
3. Track pass/fail by category

Report:
- Overall accuracy percentage
- Failures grouped by category
- Fail test if ANY question fails - 100% accuracy required

Every question must pass. If any fail, fix the bug or fix the question - never lower the bar.
```

---

## DEBUGGING PROMPTS

### If confidence exceeds 1.0:
```
The confidence score is exceeding 1.0. Find all places where confidence is calculated or assigned and ensure they use bounded_confidence(). Add an assertion in NLQResponse validator that raises error if confidence > 1.0. Show me all confidence-related code.
```

### If relative dates wrong:
```
Relative date resolution is incorrect. The reference_date is 2026-01-27, so:
- last_year should resolve to 2025
- last_quarter should resolve to 2025-Q4
- this_year should resolve to 2026

Check PeriodResolver. Make sure it's receiving the reference_date from the request, not using system time.
```

### If synonyms not matching:
```
Synonym normalization isn't working. "top line" should normalize to "revenue". Check:
1. Is normalize_metric() being called before query execution?
2. Is the comparison case-insensitive?
3. Are multi-word synonyms handled (strip, lower, replace spaces)?
Show me the normalization code path.
```

### If zero-row results:
```
Query is returning empty/zero results when data exists. Check:
1. Is the period format matching what's in fact_base.json?
2. For annual queries, are we summing quarters correctly?
3. Is the metric name normalized before lookup?
Add debug logging to trace: raw metric -> normalized metric -> period -> query result
```

---

## VALIDATION CHECKLIST

Before declaring done, verify:

```
Run the full test suite and confirm:

1. [ ] tests/test_confidence.py passes - no score > 1.0
2. [ ] tests/test_resolver.py passes - relative dates correct  
3. [ ] tests/test_synonyms.py passes - all variations work
4. [ ] tests/test_e2e.py passes - 100% of 55 questions correct (all must pass)

5. [ ] POST /v1/query returns valid NLQResponse
6. [ ] GET /v1/health returns 200
7. [ ] GET /v1/schema lists all metrics and periods

8. [ ] "What was revenue last year?" returns $150M (not current year)
9. [ ] "What was top line in 2024?" returns same as "What was revenue in 2024?"
10. [ ] Query for "Q5 2024" returns error, not crash
```

---

*Use these prompts sequentially for new build, or jump to specific phase for fixes.*
