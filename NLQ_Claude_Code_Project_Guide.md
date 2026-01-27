# NLQ Engine - Standalone Project

## Project Overview

**Purpose**: Natural Language Query engine for enterprise financial data  
**Architecture**: Standalone Python service, decoupled from DCL  
**AI Backend**: Claude API (Anthropic) for reasoning  
**Owner**: Ilya  
**IDE**: Replit  
**Developer**: Claude Code for Web (CC)

---

## CRITICAL CONTEXT FOR CLAUDE CODE

### Who is building this
Ilya is the product owner. He does NOT write code directly. He uses AI assistants (you, Claude Code) to build. He understands systems architecture and can review code, but prefers not to debug or set up environments manually.

### What this project is
A standalone NLQ (Natural Language Query) engine that:
1. Accepts natural language questions about financial data
2. Parses intent, entities, and time references
3. Resolves relative dates ("last quarter") to absolute dates
4. Generates structured queries against a financial fact base
5. Returns answers with confidence scores (MUST be 0.0-1.0, never exceed 1.0)

### What this project is NOT
- Not a DCL component (decoupled)
- Not a UI (API only)
- Not a database (consumes data from external sources)
- Not training an ML model (uses Claude API for reasoning)

---

## PROJECT STRUCTURE

```
aos-nlq/
├── README.md
├── pyproject.toml
├── .env.example
├── src/
│   └── nlq/
│       ├── __init__.py
│       ├── main.py              # FastAPI app entry point
│       ├── config.py            # Settings, env vars
│       ├── models/
│       │   ├── __init__.py
│       │   ├── query.py         # Pydantic models for requests
│       │   └── response.py      # Pydantic models for responses
│       ├── core/
│       │   ├── __init__.py
│       │   ├── parser.py        # Query parsing & intent extraction
│       │   ├── resolver.py      # Date/period resolution
│       │   ├── executor.py      # Query execution against data
│       │   └── confidence.py    # Confidence scoring (bounded 0-1)
│       ├── knowledge/
│       │   ├── __init__.py
│       │   ├── synonyms.py      # Metric & period synonym maps
│       │   ├── schema.py        # Financial data schema definition
│       │   └── fact_base.py     # Fact base loader
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── client.py        # Claude API client wrapper
│       │   └── prompts.py       # System prompts for Claude
│       └── api/
│           ├── __init__.py
│           └── routes.py        # API endpoints
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures
│   ├── test_parser.py
│   ├── test_resolver.py
│   ├── test_executor.py
│   ├── test_confidence.py
│   └── test_e2e.py              # End-to-end with ground truth
├── data/
│   ├── fact_base.json           # Financial fact base
│   └── test_questions.json      # Test suite with ground truth
└── scripts/
    ├── validate.py              # Run all tests against ground truth
    └── benchmark.py             # Performance benchmarking
```

---

## IMPLEMENTATION REQUIREMENTS

### 1. Confidence Scores - CRITICAL

**Problem to solve**: Previous implementation had confidence scores exceeding 1.0

**Requirement**: ALL confidence scores MUST be bounded [0.0, 1.0]

```python
# REQUIRED PATTERN - Use everywhere confidence is calculated
def bounded_confidence(score: float) -> float:
    """Ensure confidence is always in [0, 1] range."""
    return max(0.0, min(1.0, score))
```

**Confidence calculation factors**:
- Intent clarity (0-1): How clear is what they're asking?
- Entity match (0-1): Did we find the metric/period they referenced?
- Data availability (0-1): Do we have data for that period?
- Final score = weighted average, ALWAYS clamped to [0, 1]

### 2. Relative Date Resolution - CRITICAL

**Problem to solve**: Queries like "last quarter" must resolve based on current date

**Requirement**: Query processor receives current_date context at runtime

```python
from datetime import date

class PeriodResolver:
    def __init__(self, reference_date: date = None):
        self.reference_date = reference_date or date.today()
        self.current_year = self.reference_date.year
        self.current_quarter = (self.reference_date.month - 1) // 3 + 1
    
    def resolve(self, period_reference: str) -> dict:
        """Convert relative period to absolute."""
        mappings = {
            "last_year": {"type": "annual", "year": self.current_year - 1},
            "this_year": {"type": "annual", "year": self.current_year},
            "last_quarter": self._previous_quarter(),
            "this_quarter": {"type": "quarterly", "year": self.current_year, "quarter": self.current_quarter},
        }
        return mappings.get(period_reference.lower().replace(" ", "_"))
```

### 3. Synonym Normalization - CRITICAL

**Problem to solve**: Users say "top line", "turnover", "sales" meaning "revenue"

**Requirement**: Normalize all metric references before processing

```python
METRIC_SYNONYMS = {
    "revenue": ["sales", "top line", "turnover", "top-line", "topline"],
    "net_income": ["profit", "bottom line", "earnings", "net profit", "bottom-line"],
    "operating_profit": ["ebit", "operating income", "op profit"],
    "gross_profit": ["gross income", "gross margin dollars"],
    "cogs": ["cost of goods sold", "cost of sales", "cost of revenue", "cos"],
    "sga": ["sg&a", "selling general and administrative", "opex", "operating expenses"],
}

def normalize_metric(raw_metric: str) -> str:
    """Convert synonym to canonical metric name."""
    raw_lower = raw_metric.lower().strip()
    for canonical, synonyms in METRIC_SYNONYMS.items():
        if raw_lower == canonical or raw_lower in synonyms:
            return canonical
    return raw_lower  # Return as-is if no match
```

### 4. Zero-Row Handling - CRITICAL

**Problem to solve**: Aggregations returning zero rows when data doesn't exist

**Requirement**: Explicit checks before returning results

```python
def execute_query(parsed_query: ParsedQuery, fact_base: FactBase) -> QueryResult:
    # Check 1: Does the metric exist?
    if parsed_query.metric not in fact_base.available_metrics:
        return QueryResult(
            success=False,
            error="UNKNOWN_METRIC",
            message=f"Metric '{parsed_query.metric}' not found. Available: {fact_base.available_metrics}",
            confidence=0.0
        )
    
    # Check 2: Does the period exist in data?
    if not fact_base.has_period(parsed_query.resolved_period):
        return QueryResult(
            success=False,
            error="NO_DATA_FOR_PERIOD",
            message=f"No data available for {parsed_query.resolved_period}",
            confidence=0.0
        )
    
    # Check 3: Execute and verify non-empty result
    result = fact_base.query(parsed_query.metric, parsed_query.resolved_period)
    if result is None or (isinstance(result, list) and len(result) == 0):
        return QueryResult(
            success=False,
            error="EMPTY_RESULT",
            message="Query returned no data",
            confidence=0.0
        )
    
    return QueryResult(success=True, value=result, confidence=bounded_confidence(0.95))
```

---

## API DESIGN

### Endpoints

```
POST /v1/query
GET /v1/health
GET /v1/schema  (returns available metrics/periods)
```

### Request Model

```python
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional

class NLQRequest(BaseModel):
    question: str = Field(..., description="Natural language question")
    reference_date: Optional[date] = Field(default=None, description="Date context for relative references. Defaults to today.")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What was revenue last year?",
                "reference_date": "2026-01-27"
            }
        }
```

### Response Model

```python
from pydantic import BaseModel, Field
from typing import Optional, Any

class NLQResponse(BaseModel):
    success: bool
    answer: Optional[str] = Field(None, description="Human-readable answer")
    value: Optional[Any] = Field(None, description="Raw numeric value")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score, always 0-1")
    
    # Debugging/transparency
    parsed_intent: Optional[str] = None
    resolved_metric: Optional[str] = None
    resolved_period: Optional[str] = None
    
    # Error handling
    error_code: Optional[str] = None
    error_message: Optional[str] = None
```

---

## CLAUDE API INTEGRATION

### System Prompt for Query Parsing

```python
QUERY_PARSER_PROMPT = """You are a financial query parser for an enterprise NLQ system.

Given a natural language question about financial data, extract:
1. intent: One of [POINT_QUERY, COMPARISON_QUERY, TREND_QUERY, AGGREGATION_QUERY, BREAKDOWN_QUERY]
2. metric: The financial metric being asked about (use canonical names)
3. period_type: One of [annual, quarterly, half_year, ytd]
4. period_reference: Either absolute (e.g., "2024", "Q4 2025") or relative (e.g., "last_year", "last_quarter")
5. is_relative: Boolean - does this use relative time references?

Canonical metric names: revenue, bookings, cogs, gross_profit, gross_margin_pct, selling_expenses, g_and_a_expenses, sga, operating_profit, operating_margin_pct, net_income, net_income_pct, cash, ar, ap, ppe, deferred_revenue, unbilled_revenue, total_current_assets, current_liabilities, retained_earnings, stockholders_equity

Relative period keywords: last year, prior year, previous year, this year, current year, last quarter, prior quarter, previous quarter, this quarter, current quarter

Respond ONLY with valid JSON, no markdown, no explanation:
{
  "intent": "...",
  "metric": "...",
  "period_type": "...",
  "period_reference": "...",
  "is_relative": true/false
}
"""
```

### Client Wrapper

```python
import anthropic
from typing import Optional
import json

class ClaudeClient:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"  # Use Sonnet for speed/cost
    
    def parse_query(self, question: str) -> dict:
        """Use Claude to parse natural language query."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            system=QUERY_PARSER_PROMPT,
            messages=[{"role": "user", "content": question}]
        )
        
        # Extract JSON from response
        content = response.content[0].text.strip()
        
        # Handle potential markdown wrapping
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        
        return json.loads(content)
```

---

## TESTING STRATEGY

### Accuracy Requirement: 100%

**All 55 ground truth questions must pass. No exceptions.**

Rationale:
- You control the test set — these aren't wild user queries
- Financial data is precise — "What was revenue in 2024?" has exactly one answer
- Failures indicate bugs, not edge cases
- Format mismatches are bugs in comparison logic, not reasons to lower the bar

If a test fails:
1. Fix the bug in the engine
2. If the question is genuinely ambiguous, fix the question
3. Never lower the threshold

### Test Categories

1. **Unit tests**: Each component in isolation
2. **Integration tests**: Components working together
3. **Ground truth tests**: 55 questions with known answers
4. **Edge case tests**: Invalid inputs, missing data, ambiguous queries

### Ground Truth Validation

```python
import pytest
import json

@pytest.fixture
def test_questions():
    with open("data/test_questions.json") as f:
        return json.load(f)

@pytest.fixture
def nlq_engine():
    return NLQEngine()  # Your engine instance

def test_ground_truth_accuracy(nlq_engine, test_questions):
    """All 55 questions must return correct answers."""
    results = []
    
    for q in test_questions["test_questions"]:
        response = nlq_engine.query(
            question=q["question"],
            reference_date=date(2026, 1, 27)  # Fixed reference for testing
        )
        
        # Check answer matches ground truth
        expected = q["ground_truth"]
        actual = response.answer
        
        results.append({
            "id": q["id"],
            "question": q["question"],
            "expected": expected,
            "actual": actual,
            "passed": expected in actual or actual in expected  # Flexible matching
        })
    
    # Report
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    
    print(f"\nGround Truth Accuracy: {passed}/{total} ({100*passed/total:.1f}%)")
    
    # Fail if ANY question wrong - 100% accuracy required
    assert passed == total, f"Failed {total - passed} questions. All 55 must pass."
```

---

## REPLIT SETUP INSTRUCTIONS

When creating the project in Replit:

1. **Create new Repl**: Python template
2. **Rename to**: `aos-nlq`
3. **In Shell, run**:
   ```bash
   pip install fastapi uvicorn anthropic pydantic python-dotenv pytest
   ```
4. **Create `.env`**:
   ```
   ANTHROPIC_API_KEY=your-key-here
   ```
5. **Set Replit Secrets**: Add `ANTHROPIC_API_KEY` in Secrets tab (more secure than .env)

### Replit Run Command

In `.replit` file or Run configuration:
```
uvicorn src.nlq.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## PROMPTS FOR CLAUDE CODE

Use these prompts to guide Claude Code through implementation:

### Prompt 1: Project Setup
```
Create a new Python project called aos-nlq with the folder structure defined in the project spec. Use FastAPI for the API layer, Pydantic for models, and set up for Anthropic Claude API integration. Create placeholder files with docstrings explaining what each module does. Include pyproject.toml with dependencies: fastapi, uvicorn, anthropic, pydantic, python-dotenv, pytest.
```

### Prompt 2: Core Models
```
Implement the Pydantic models in src/nlq/models/. Create NLQRequest with question (str) and optional reference_date (date). Create NLQResponse with success, answer, value, unit, confidence (bounded 0-1 using Field(ge=0, le=1)), parsed_intent, resolved_metric, resolved_period, error_code, error_message. Include Config with example JSON schemas.
```

### Prompt 3: Synonym System
```
Implement src/nlq/knowledge/synonyms.py with METRIC_SYNONYMS and PERIOD_SYNONYMS dictionaries. Create normalize_metric() and normalize_period() functions that convert user terms to canonical names. Include comprehensive synonyms for: revenue (sales, top line, turnover), net_income (profit, bottom line, earnings), operating_profit (EBIT), cogs (cost of goods sold, cost of sales), sga (SG&A, opex). Add unit tests.
```

### Prompt 4: Period Resolver
```
Implement src/nlq/core/resolver.py with PeriodResolver class. Constructor takes optional reference_date (defaults to today). Method resolve(period_reference: str) converts relative terms (last_year, last_quarter, this_year, prior_year, previous_quarter) to absolute periods. Return dict with type (annual/quarterly), year, and quarter if applicable. Handle edge cases: Q1 "last quarter" should return Q4 of previous year. Add unit tests.
```

### Prompt 5: Confidence Scoring
```
Implement src/nlq/core/confidence.py with bounded_confidence(score: float) -> float that clamps any input to [0.0, 1.0] range. Create ConfidenceCalculator class with method calculate(intent_score, entity_score, data_availability_score) -> float that returns weighted average, ALWAYS bounded. Weights: intent=0.4, entity=0.4, data=0.2. Add unit tests including edge cases: negative inputs, inputs > 1, NaN handling.
```

### Prompt 6: Claude API Client
```
Implement src/nlq/llm/client.py and prompts.py. Create QUERY_PARSER_PROMPT as a system prompt instructing Claude to extract intent, metric, period_type, period_reference, is_relative from natural language questions. Response must be JSON only. Create ClaudeClient class wrapping anthropic.Anthropic with parse_query(question: str) method. Handle JSON extraction including stripping markdown code fences. Use claude-sonnet-4-20250514 model.
```

### Prompt 7: Query Executor
```
Implement src/nlq/core/executor.py. Create QueryExecutor class that takes a FactBase instance. Method execute(parsed_query) checks: 1) metric exists in schema, 2) period exists in data, 3) result is non-empty. Return QueryResult with appropriate error codes (UNKNOWN_METRIC, NO_DATA_FOR_PERIOD, EMPTY_RESULT) and confidence=0 for failures. For success, return value with bounded confidence.
```

### Prompt 8: Fact Base Loader
```
Implement src/nlq/knowledge/fact_base.py. Create FactBase class that loads financial data from JSON. Methods: load(filepath), available_metrics -> list, available_periods -> list, has_period(period) -> bool, query(metric, period) -> value. Handle both quarterly and annual queries. Support period formats: "2024" for annual, "2024-Q1" for quarterly. Load the test fact base from data/fact_base.json.
```

### Prompt 9: API Routes
```
Implement src/nlq/api/routes.py and wire up in main.py. Create POST /v1/query endpoint accepting NLQRequest, returning NLQResponse. Create GET /v1/health returning {"status": "healthy"}. Create GET /v1/schema returning available metrics and periods. Wire everything together: parse query with Claude, resolve periods, normalize metrics, execute against fact base, return response with bounded confidence.
```

### Prompt 10: End-to-End Tests
```
Implement tests/test_e2e.py. Load test_questions.json with 55 ground truth questions. For each question, call the NLQ engine with reference_date=2026-01-27 and verify the answer matches ground truth. Use flexible matching (ground truth contained in answer or vice versa). Report accuracy percentage. Fail test if accuracy below 90%. Group failures by category (absolute, relative, margin, balance_sheet, comparison, synonym) to identify weak areas.
```

---

## SUCCESS CRITERIA

Before considering the NLQ engine complete:

- [ ] All 55 ground truth questions return correct answers (100% accuracy required)
- [ ] Confidence scores NEVER exceed 1.0 (add assertion tests)
- [ ] Relative dates resolve correctly based on reference_date
- [ ] Synonym variations return same results ("revenue" = "sales" = "top line")
- [ ] Zero-row scenarios return appropriate error messages, not empty results
- [ ] API responds in <2 seconds for single queries
- [ ] Health check endpoint works
- [ ] Schema endpoint returns accurate metadata

---

## KNOWN ISSUES TO AVOID

From the DCL implementation:

1. **Confidence > 1.0**: Always use bounded_confidence() wrapper
2. **Zero-row aggregations**: Check data exists BEFORE aggregating
3. **Hardcoded date logic**: Use injected reference_date, never datetime.now() in business logic
4. **Tight coupling**: Keep NLQ independent of DCL, communicate via API only
5. **Missing synonym coverage**: Test all variations in test suite

---

*Document version: 1.0*
*Created: January 27, 2026*
*For use with Claude Code for Web*
