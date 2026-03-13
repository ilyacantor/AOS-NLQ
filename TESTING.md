# Testing Guide

## Prerequisites

- **Python** >= 3.11
- **pip** (or **uv** / **pipx**)
- **Environment variables** (copy `.env.example` to `.env`):
  - `ANTHROPIC_API_KEY` -- required for any tests that hit Claude (LLM integration, eval suites)
  - `DCL_API_URL` -- required for eval tests that hit real DCL
  - `NLQ_API_PORT` -- defaults to `8000`; the live/e2e harnesses default to `http://localhost:8005`
  - `NLQ_FACT_BASE_PATH` -- defaults to `data/fact_base.json`; many tests load this fixture

## Install Dependencies

```bash
# Core + test dependencies
pip install -e ".[dev]"

# Or from requirements.txt (does not include test extras)
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov
```

## Running Tests

### All unit tests (no running server needed)

```bash
pytest
```

This runs everything under `tests/` that pytest discovers via `pyproject.toml` config (`testpaths = ["tests"]`, `asyncio_mode = "auto"`).

### With coverage

```bash
pytest --cov=src/nlq --cov-report=term-missing
```

### Single test file

```bash
pytest tests/test_parser.py
pytest tests/test_resolver.py -v
```

### Single test class or method

```bash
pytest tests/test_parser.py::TestQueryParser::test_parse_point_query
```

### Eval suite only (requires DCL connection)

```bash
pytest tests/eval/
```

---

## Test Categories

### Unit Tests (no server, no API keys needed for most)

| File | What it tests |
|------|---------------|
| `test_parser.py` | Query parsing -- intent extraction, metric normalization, period detection (uses mock Claude client) |
| `test_resolver.py` | Period resolution -- relative dates (last_year, this_quarter), absolute parsing, edge cases like Q1 last-quarter rollover. Uses injected reference date, not system time |
| `test_confidence.py` | Confidence scoring -- bounded [0.0, 1.0] clamping, edge cases (NaN, negative, overflow) |
| `test_executor.py` | Query execution -- unknown metrics, missing periods, empty results return explicit errors |
| `test_fact_base.py` | FactBase loading and querying -- period formats, metric availability, annual aggregation from quarterly data. Requires `data/fact_base.json` |
| `test_llm.py` | LLM prompt validation and Claude client (mocked -- no API calls) |
| `test_synonyms.py` | Synonym normalization -- metric aliases and period aliases map to canonical names |
| `test_ambiguous.py` | Ambiguous query detection -- incomplete queries, casual language, vague metrics, yes/no questions. Requires `data/fact_base.json` |
| `test_visual_properties.py` | Galaxy visualization -- ring assignment, confidence bounds, data quality, semantic labels |
| `test_circuit_breaker.py` | Claude API circuit breaker -- state transitions (CLOSED/OPEN/HALF_OPEN), timeout handling, 5xx vs 4xx behavior |
| `test_session_store.py` | Dashboard session store -- TTL expiry, capacity eviction, stats |

### Integration Tests (mocked HTTP, no running server)

| File | What it tests |
|------|---------------|
| `test_dcl_adapter_integration.py` | DCL-NLQ adapter layer -- catalog parsing, metric resolution, query transform, provenance pipeline. Uses mock DCL payloads |
| `test_cross_module_contract.py` | AAM-DCL-NLQ data contracts -- validates payload shapes across all three modules using fixture payloads |
| `test_e2e.py` | End-to-end ground truth validation -- 100% of ground truth questions must pass. Tests full parse-resolve-execute pipeline without a server |
| `test_e2e_graph_resolution.py` | NLQ-to-DCL graph resolution pipeline -- intent parsing through DCL resolve to response formatting, with mocked DCL graph responses |
| `test_dcl_harness.py` | DCL capability tests -- entity extraction, filter passthrough, provenance, conflict surfacing, temporal warnings. Loads from `data/entity_test_scenarios.json` |

### Eval Tests (require real DCL connection)

These live in `tests/eval/` and use a real DCL client (no mocking). They fail if DCL is unavailable.

| File | What it tests |
|------|---------------|
| `test_ground_truth.py` | 175 ground truth tests -- base metrics, aliases, spelling errors, casual queries, dimension aliases, dashboard commands, negative tests |
| `test_superlatives.py` | Ranking queries -- largest, highest, best, top, worst, lowest, bottom |
| `test_metric_resolution.py` | Metric alias resolution against real DCL -- AR, ARR, eNPS, etc. |
| `test_dimension_validation.py` | Valid vs invalid metric+dimension combinations, helpful error messages |
| `test_negative_cases.py` | Error surfacing -- invalid inputs must fail with clear errors, not silent fallbacks |

### Live Harnesses (require NLQ server running)

These are standalone scripts that make real HTTP requests to a running NLQ instance. They are not discovered by `pytest` automatically.

| File | How to run | What it tests |
|------|-----------|---------------|
| `tests/test_30_ground_truth.py` | `python tests/test_30_ground_truth.py [--verbose]` | 30 binary ground truth questions via POST `/api/v1/query` |
| `tests/live_harness.py` | `python tests/live_harness.py [--verbose] [--md]` | 30 questions in live DCL mode, validates structural shape (not exact values) |
| `tests/harness/nlq_harness.py` | `python tests/harness/nlq_harness.py [--url URL] [--verbose] [--test ID]` | Cheatproof harness -- real HTTP only, no mocks, no fact_base.json |
| `tests/e2e_nlq_validation.py` | `python tests/e2e_nlq_validation.py` | 100 questions via real HTTP, anti-cheat rules enforced |
| `tests/demo_eval/demo_eval.py` | `python -m tests.demo_eval.demo_eval [--url URL] [--persona CFO]` | 40 scenarios (5 personas x 8 queries), qualitative scoring |
| `tests/demo_e2e_regression_check.py` | `python tests/demo_e2e_regression_check.py` | Regression check against baseline results |

Default server URL for live harnesses: `http://localhost:8005/api/v1/query` (some accept `--url` to override).

### Standalone Accuracy Test

| File | How to run | What it tests |
|------|-----------|---------------|
| `tests/test_nlq_accuracy.py` | `python tests/test_nlq_accuracy.py` | Exhaustive metric + period combinations through tiered resolution (no LLM calls) |

---

## Pytest Configuration

Defined in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
asyncio_mode = "auto"
```

## Data Fixtures

Several tests depend on data files in `data/`:

- `data/fact_base.json` -- financial fact base (metrics, periods, values)
- `data/nlq_test_questions.json` -- ground truth questions with expected answers
- `data/entity_test_scenarios.json` -- entity extraction test scenarios
- `tests/eval/ground_truth.json` -- 175-question ground truth for eval suite
