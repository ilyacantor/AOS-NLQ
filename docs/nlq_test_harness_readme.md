# NLQ Ground Truth Test Suite

94 test cases. Zero dependencies. 4 endpoints. All 25 canonical metrics.

## Coverage

| Section | Count | What it tests |
|---|---|---|
| MR (Metric Resolution) | 25 | Every canonical metric resolves correctly via Galaxy |
| AL (Alias Traps) | 14 | Confusable aliases (top line, recurring revenue, ebit, FTE, etc.) |
| BD (Breakdowns) | 15 | metric-by-dimension routing incl unlisted dims (cost center, service, role, location) |
| TM (Temporal) | 8 | metric-by-quarter/over-time -- the revenue->ARR failure class |
| STD (Standard) | 5 | Same queries via /query for regression |
| DB (Dashboard Build) | 12 | Self-building dashboard via /query/dashboard |
| DR (Dashboard Refine) | 5 | Adjustment queries via /dashboard/refine |
| GD (Galaxy->Dashboard) | 4 | Dashboard-intent routing from Galaxy |
| NG (Guardrails) | 6 | Cross-metric confusion that must never happen |

## Usage

    # Run all 94 tests
    python run_tests.py --base-url http://localhost:8000

    # Run by section
    python run_tests.py --base-url http://localhost:8000 --tag galaxy
    python run_tests.py --base-url http://localhost:8000 --tag dashboard
    python run_tests.py --base-url http://localhost:8000 --tag breakdown
    python run_tests.py --base-url http://localhost:8000 --tag alias
    python run_tests.py --base-url http://localhost:8000 --tag guardrail

    # Run single test
    python run_tests.py --base-url http://localhost:8000 --id BD-001

    # Verbose (full response bodies)
    python run_tests.py --base-url http://localhost:8000 -v

    # Save results
    python run_tests.py --base-url http://localhost:8000 --json-out results.json

## CC workflow

Before any NLQ fix:

    python run_tests.py --base-url http://localhost:8000 --id BUG-001

After the fix:

    python run_tests.py --base-url http://localhost:8000

Exit code 1 = failures. Exit code 0 = all pass.

## Endpoints covered

- /api/v1/query/galaxy -- Galaxy Ask (what frontend uses)
- /api/v1/query -- raw NLQ
- /api/v1/query/dashboard -- dashboard self-build
- /api/v1/dashboard/refine -- dashboard adjustment chat
