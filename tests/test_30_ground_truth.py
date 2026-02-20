"""
AeroFlow-K3OA Ground Truth Test Harness — 30 Binary Questions.

Tests POST /api/dcl/query and GET /api/dcl/ingest/* endpoints
against verified ground truth from the AeroFlow-K3OA tenant data.

Each test has a binary pass/fail: the returned value must match ground truth
within tolerance (1% for floats, exact for strings/ints).

Run:
    python tests/test_30_ground_truth.py
    # or
    python tests/test_30_ground_truth.py --verbose
"""

import json
import math
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:5000"
TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# Test case definition
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """One ground-truth question."""
    id: int
    persona: str
    question: str
    expected: Any  # The ground truth answer
    endpoint: str  # HTTP method + path
    payload: Optional[Dict[str, Any]] = None  # POST body or None for GET
    tolerance: float = 0.01  # 1% tolerance for floats
    match_type: str = "value"  # "value", "dimensional", "ranked", "ingest_stat"
    expected_dimensions: Optional[Dict[str, Any]] = None  # For dimensional queries
    expected_top: Optional[Dict[str, str]] = None  # For ranked queries {name_key: name, value_key: val}


# ---------------------------------------------------------------------------
# Ground truth questions
# ---------------------------------------------------------------------------

GROUND_TRUTH: List[TestCase] = [
    # === CFO Q1-Q2 ===
    TestCase(
        id=1, persona="CFO",
        question="What is our current ARR?",
        expected=47.5,
        endpoint="POST /api/dcl/query",
        payload={"metric": "arr", "persona": "cfo"},
        match_type="value",
    ),
    TestCase(
        id=2, persona="CFO",
        question="Show revenue by region",
        expected={"AMER": 25.0, "EMEA": 15.0, "APAC": 10.0},
        endpoint="POST /api/dcl/query",
        payload={"metric": "revenue", "dimensions": ["region"], "persona": "cfo"},
        match_type="dimensional",
    ),
    # === CRO Q3-Q4 ===
    TestCase(
        id=3, persona="CRO",
        question="What is our win rate?",
        expected=45.5,
        endpoint="POST /api/dcl/query",
        payload={"metric": "win_rate", "persona": "cro"},
        match_type="value",
    ),
    TestCase(
        id=4, persona="CRO",
        question="Which customer has the highest churn risk?",
        expected={"name": "RetailMax", "value": 72},
        endpoint="POST /api/dcl/query",
        payload={"metric": "churn_risk", "dimensions": ["customer"], "order_by": "desc", "limit": 1, "persona": "cro"},
        match_type="ranked",
    ),
    # === CTO Q5-Q6 ===
    TestCase(
        id=5, persona="CTO",
        question="What is our current uptime?",
        expected=99.82,
        endpoint="POST /api/dcl/query",
        payload={"metric": "uptime", "persona": "cto"},
        match_type="value",
    ),
    TestCase(
        id=6, persona="CTO",
        question="What is MTTR for P1 incidents?",
        expected=1.5,
        endpoint="POST /api/dcl/query",
        payload={"metric": "mttr", "persona": "cto"},
        match_type="value",
    ),
    # === CHRO Q7-Q8 ===
    TestCase(
        id=7, persona="CHRO",
        question="What is our current headcount?",
        expected=430,
        endpoint="POST /api/dcl/query",
        payload={"metric": "headcount", "persona": "chro"},
        match_type="value",
    ),
    TestCase(
        id=8, persona="CHRO",
        question="What is our attrition rate?",
        expected=1.2,
        endpoint="POST /api/dcl/query",
        payload={"metric": "attrition_rate", "persona": "chro"},
        match_type="value",
    ),
    # === COO Q9-Q10 (ingest) ===
    TestCase(
        id=9, persona="COO",
        question="How many data sources are connected?",
        expected=27,
        endpoint="GET /api/dcl/ingest/stats",
        match_type="ingest_stat",
    ),
    TestCase(
        id=10, persona="COO",
        question="Which source system has the most ingested rows?",
        expected={"name": "Zendesk", "value": 139200},
        endpoint="GET /api/dcl/ingest/runs",
        match_type="ranked",
    ),
    # === CFO Q11-Q15 ===
    TestCase(
        id=11, persona="CFO",
        question="What is our gross margin?",
        expected=67.0,
        endpoint="POST /api/dcl/query",
        payload={"metric": "gross_margin", "persona": "cfo"},
        match_type="value",
    ),
    TestCase(
        id=12, persona="CFO",
        question="Show revenue by segment",
        expected={"Enterprise": 27.5, "Mid-Market": 15.0, "SMB": 7.5},
        endpoint="POST /api/dcl/query",
        payload={"metric": "revenue", "dimensions": ["segment"], "persona": "cfo"},
        match_type="dimensional",
    ),
    TestCase(
        id=13, persona="CFO",
        question="What is DSO by segment?",
        expected={"Enterprise": 49, "Mid-Market": 38, "SMB": 25},
        endpoint="POST /api/dcl/query",
        payload={"metric": "dso", "dimensions": ["segment"], "persona": "cfo"},
        match_type="dimensional",
    ),
    TestCase(
        id=14, persona="CFO",
        question="Which product has the highest gross margin?",
        expected={"name": "Enterprise", "value": 21.44},
        endpoint="POST /api/dcl/query",
        payload={"metric": "gross_margin", "dimensions": ["product"], "order_by": "desc", "limit": 1, "persona": "cfo"},
        match_type="ranked",
    ),
    TestCase(
        id=15, persona="CFO",
        question="What is our cloud spend by category?",
        expected={"Compute": 0.376, "Storage": 0.188, "Database": 0.188, "Network": 0.094, "Other": 0.094},
        endpoint="POST /api/dcl/query",
        payload={"metric": "cloud_spend", "dimensions": ["category"], "persona": "cfo"},
        match_type="dimensional",
    ),
    # === CRO Q16-Q20 ===
    TestCase(
        id=16, persona="CRO",
        question="Show pipeline by stage",
        expected={"Lead": 28.75, "Qualified": 43.12, "Proposal": 35.94, "Negotiation": 21.56, "Closed-Won": 14.38},
        endpoint="POST /api/dcl/query",
        payload={"metric": "pipeline", "dimensions": ["stage"], "persona": "cro"},
        match_type="dimensional",
    ),
    TestCase(
        id=17, persona="CRO",
        question="What is churn rate by segment?",
        expected={"Enterprise": 4.0, "Mid-Market": 6.3, "SMB": 10.8},
        endpoint="POST /api/dcl/query",
        payload={"metric": "churn_rate", "dimensions": ["segment"], "persona": "cro"},
        match_type="dimensional",
    ),
    TestCase(
        id=18, persona="CRO",
        question="What is our NRR?",
        expected=121.5,
        endpoint="POST /api/dcl/query",
        payload={"metric": "nrr", "persona": "cro"},
        match_type="value",
    ),
    TestCase(
        id=19, persona="CRO",
        question="Show NRR by cohort",
        expected={"2022-H1": 111.3, "2023-H1": 118.3, "2024-H1": 123.3, "2025-H1": 127.3},
        endpoint="POST /api/dcl/query",
        payload={"metric": "nrr", "dimensions": ["cohort"], "persona": "cro"},
        match_type="dimensional",
    ),
    TestCase(
        id=20, persona="CRO",
        question="Which segment has the highest churn?",
        expected={"name": "SMB", "value": 10.8},
        endpoint="POST /api/dcl/query",
        payload={"metric": "churn_rate", "dimensions": ["segment"], "order_by": "desc", "limit": 1, "persona": "cro"},
        match_type="ranked",
    ),
    # === CTO Q21-Q25 ===
    TestCase(
        id=21, persona="CTO",
        question="What is deploy frequency by service?",
        expected={"Web App": 6.4, "API Gateway": 4.5, "Notification": 3.2, "Auth": 2.5, "Mobile": 2.5, "Payment": 1.9, "Data Pipeline": 1.3},
        endpoint="POST /api/dcl/query",
        payload={"metric": "deploy_frequency", "dimensions": ["service"], "persona": "cto"},
        match_type="dimensional",
    ),
    TestCase(
        id=22, persona="CTO",
        question="Show uptime by service",
        expected={"Auth": 99.999, "Payment": 99.999, "API Gateway": 99.975, "Web App": 99.955},
        endpoint="POST /api/dcl/query",
        payload={"metric": "uptime", "dimensions": ["service"], "persona": "cto"},
        match_type="dimensional",
        tolerance=0.005,  # Tighter for high-precision uptime
    ),
    TestCase(
        id=23, persona="CTO",
        question="Which service deploys the most?",
        expected={"name": "Web App", "value": 6.4},
        endpoint="POST /api/dcl/query",
        payload={"metric": "deploy_frequency", "dimensions": ["service"], "order_by": "desc", "limit": 1, "persona": "cto"},
        match_type="ranked",
    ),
    TestCase(
        id=24, persona="CTO",
        question="What is SLA compliance by team?",
        expected={"Frontend": 99.5, "Infra": 99.5, "Security": 99.5, "Platform": 98.3, "Backend": 97.6, "Mobile": 95.8, "Data": 95.3},
        endpoint="POST /api/dcl/query",
        payload={"metric": "sla_compliance", "dimensions": ["team"], "persona": "cto"},
        match_type="dimensional",
    ),
    TestCase(
        id=25, persona="CTO",
        question="Which team has the lowest SLA compliance?",
        expected={"name": "Data", "value": 95.3},
        endpoint="POST /api/dcl/query",
        payload={"metric": "sla_compliance", "dimensions": ["team"], "order_by": "asc", "limit": 1, "persona": "cto"},
        match_type="ranked",
    ),
    # === CHRO Q26-Q28 ===
    TestCase(
        id=26, persona="CHRO",
        question="What is headcount by department?",
        expected={"Engineering": 145, "Sales": 80, "CS": 60, "Marketing": 43, "Product": 34, "G&A": 24, "People": 22, "Finance": 22},
        endpoint="POST /api/dcl/query",
        payload={"metric": "headcount", "dimensions": ["department"], "persona": "chro"},
        match_type="dimensional",
    ),
    TestCase(
        id=27, persona="CHRO",
        question="What is our engagement score?",
        expected=86.0,
        endpoint="POST /api/dcl/query",
        payload={"metric": "engagement_score", "persona": "chro"},
        match_type="value",
    ),
    TestCase(
        id=28, persona="CHRO",
        question="What is our offer acceptance rate?",
        expected=93.0,
        endpoint="POST /api/dcl/query",
        payload={"metric": "offer_acceptance_rate", "persona": "chro"},
        match_type="value",
    ),
    # === COO Q29-Q30 ===
    TestCase(
        id=29, persona="COO",
        question="What is throughput by team?",
        expected={"Frontend": 110, "Platform": 102, "Backend": 93, "Data": 78, "Mobile": 66, "Infra": 54, "Security": 46},
        endpoint="POST /api/dcl/query",
        payload={"metric": "throughput", "dimensions": ["team"], "persona": "coo"},
        match_type="dimensional",
    ),
    TestCase(
        id=30, persona="COO",
        question="How many total rows have been ingested?",
        expected=589120,
        endpoint="GET /api/dcl/ingest/stats",
        match_type="ingest_stat",
    ),
]


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------

def values_match(actual: Any, expected: Any, tolerance: float = 0.01) -> bool:
    """Compare actual to expected with tolerance for floats."""
    if actual is None:
        return False
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if expected == 0:
            return abs(actual) < tolerance
        return abs(actual - expected) / abs(expected) <= tolerance
    return str(actual).strip().lower() == str(expected).strip().lower()


def check_dimensional(response: Dict, expected: Dict, tolerance: float = 0.01) -> tuple:
    """
    Check dimensional query results.
    Returns (pass: bool, details: str).
    """
    data = response.get("data", [])
    if not data:
        return False, f"No data returned. Response: {json.dumps(response)[:300]}"

    # Build actual map from response data
    actual_map = {}
    for row in data:
        # Find the dimension key (first non-value, non-period key)
        dim_key = None
        for k in row.keys():
            if k not in ("value", "period", "rank", "dimensions"):
                dim_key = k
                break
        if dim_key:
            actual_map[row[dim_key]] = row.get("value")

    if not actual_map:
        return False, f"Could not extract dimension map from data: {data[:3]}"

    # Check each expected value
    mismatches = []
    missing = []
    for exp_key, exp_val in expected.items():
        # Try exact key match first, then case-insensitive
        actual_val = actual_map.get(exp_key)
        if actual_val is None:
            # Case-insensitive match
            for ak, av in actual_map.items():
                if ak.lower() == exp_key.lower() or exp_key.lower() in ak.lower():
                    actual_val = av
                    break
        if actual_val is None:
            missing.append(exp_key)
        elif not values_match(actual_val, exp_val, tolerance):
            mismatches.append(f"{exp_key}: expected={exp_val}, got={actual_val}")

    if missing:
        return False, f"Missing dimensions: {missing}. Actual keys: {list(actual_map.keys())}"
    if mismatches:
        return False, f"Value mismatches: {mismatches}"
    return True, "OK"


def check_ranked(response: Dict, expected: Dict, tolerance: float = 0.01) -> tuple:
    """
    Check ranked query results (top-1 or bottom-1).
    Returns (pass: bool, details: str).
    """
    data = response.get("data", [])
    if not data:
        return False, f"No data returned. Response: {json.dumps(response)[:300]}"

    top = data[0]
    exp_name = expected.get("name", "")
    exp_value = expected.get("value")

    # Find the name in the top result
    actual_name = None
    actual_value = top.get("value")
    for k, v in top.items():
        if k not in ("value", "period", "rank", "dimensions") and isinstance(v, str):
            actual_name = v
            break

    if actual_name is None:
        return False, f"Could not find name in top result: {top}"

    name_match = exp_name.lower() in actual_name.lower() or actual_name.lower() in exp_name.lower()
    val_match = values_match(actual_value, exp_value, tolerance) if exp_value is not None else True

    if not name_match:
        return False, f"Name mismatch: expected='{exp_name}', got='{actual_name}'"
    if not val_match:
        return False, f"Value mismatch: expected={exp_value}, got={actual_value}"
    return True, "OK"


def check_value(response: Dict, expected: Any, tolerance: float = 0.01) -> tuple:
    """
    Check simple value query results.
    Returns (pass: bool, details: str).
    """
    # Try response.value first, then data[0].value
    actual = response.get("value")
    if actual is None:
        data = response.get("data", [])
        if data and isinstance(data, list):
            if isinstance(data[0], dict):
                actual = data[0].get("value")
            else:
                actual = data[0]
    if actual is None:
        # Try formatted_value
        fv = response.get("formatted_value")
        if fv:
            try:
                actual = float(fv.replace("$", "").replace("M", "").replace("%", "").replace(",", "").strip())
            except (ValueError, TypeError):
                pass

    if actual is None:
        return False, f"No value in response. Keys: {list(response.keys())}. Response: {json.dumps(response)[:300]}"
    if not values_match(actual, expected, tolerance):
        return False, f"Value mismatch: expected={expected}, got={actual}"
    return True, "OK"


def check_ingest_stat(tc: TestCase, response: Dict) -> tuple:
    """
    Check ingest stat results.
    """
    if tc.id == 9:
        # Q9: How many data sources? → unique_sources count
        count = response.get("unique_sources")
        if count is None:
            count = response.get("source_count")
        if count is None:
            count = len(response.get("sources", []))
        if values_match(count, tc.expected):
            return True, "OK"
        return False, f"Expected {tc.expected} sources, got {count}. Response: {json.dumps(response)[:200]}"
    elif tc.id == 30:
        # Q30: Total rows ingested
        total = response.get("total_rows_buffered")
        if total is None:
            total = response.get("total_rows")
        if values_match(total, tc.expected):
            return True, "OK"
        return False, f"Expected {tc.expected} rows, got {total}. Response: {json.dumps(response)[:200]}"
    return False, f"Unknown ingest stat test id={tc.id}"


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    tc_id: int
    persona: str
    question: str
    passed: bool
    details: str
    response_time_ms: float = 0.0
    error: Optional[str] = None


def run_test(client: httpx.Client, tc: TestCase) -> TestResult:
    """Execute a single test case."""
    parts = tc.endpoint.split(" ", 1)
    method = parts[0]
    path = parts[1] if len(parts) > 1 else parts[0]
    url = f"{BASE_URL}{path}"

    try:
        start = time.monotonic()
        if method == "POST":
            resp = client.post(url, json=tc.payload, timeout=TIMEOUT)
        else:
            resp = client.get(url, timeout=TIMEOUT)
        elapsed = (time.monotonic() - start) * 1000

        if resp.status_code >= 400:
            return TestResult(
                tc_id=tc.id, persona=tc.persona, question=tc.question,
                passed=False, details=f"HTTP {resp.status_code}: {resp.text[:200]}",
                response_time_ms=elapsed,
            )

        body = resp.json()

        # Route to appropriate checker
        if tc.match_type == "value":
            ok, detail = check_value(body, tc.expected, tc.tolerance)
        elif tc.match_type == "dimensional":
            ok, detail = check_dimensional(body, tc.expected, tc.tolerance)
        elif tc.match_type == "ranked":
            if tc.id == 10:
                # Special: ingest runs ranked
                ok, detail = check_ranked_ingest(body, tc.expected, tc.tolerance)
            else:
                ok, detail = check_ranked(body, tc.expected, tc.tolerance)
        elif tc.match_type == "ingest_stat":
            ok, detail = check_ingest_stat(tc, body)
        else:
            ok, detail = False, f"Unknown match_type: {tc.match_type}"

        return TestResult(
            tc_id=tc.id, persona=tc.persona, question=tc.question,
            passed=ok, details=detail, response_time_ms=elapsed,
        )

    except Exception as e:
        return TestResult(
            tc_id=tc.id, persona=tc.persona, question=tc.question,
            passed=False, details=str(e), error=str(e),
        )


def check_ranked_ingest(response: Dict, expected: Dict, tolerance: float) -> tuple:
    """Check Q10: which source has most rows — from ingest runs."""
    runs = response.get("runs", response.get("data", []))
    if not runs:
        return False, f"No runs data. Response: {json.dumps(response)[:300]}"

    # Aggregate by source_system
    source_totals: Dict[str, int] = {}
    for run in runs:
        src = run.get("source_system", "unknown")
        rows = run.get("row_count", 0)
        source_totals[src] = source_totals.get(src, 0) + rows

    if not source_totals:
        return False, "No source totals computed"

    top_source = max(source_totals, key=source_totals.get)
    top_rows = source_totals[top_source]

    exp_name = expected.get("name", "")
    exp_value = expected.get("value", 0)

    name_ok = exp_name.lower() in top_source.lower() or top_source.lower() in exp_name.lower()
    val_ok = values_match(top_rows, exp_value, tolerance)

    if not name_ok:
        return False, f"Top source mismatch: expected='{exp_name}', got='{top_source}' ({top_rows} rows). All: {source_totals}"
    if not val_ok:
        return False, f"Row count mismatch: expected={exp_value}, got={top_rows}"
    return True, "OK"


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print("=" * 72)
    print("  AeroFlow-K3OA Ground Truth Test Harness")
    print(f"  {len(GROUND_TRUTH)} questions | Target: 100% accuracy")
    print("=" * 72)

    # Health check
    try:
        client = httpx.Client(timeout=5.0)
        resp = client.get(f"{BASE_URL}/api/dcl/health")
        if resp.status_code != 200:
            print(f"\n  ERROR: Server not healthy (status={resp.status_code})")
            sys.exit(1)
        print(f"\n  Server healthy at {BASE_URL}")
    except Exception as e:
        print(f"\n  ERROR: Cannot reach server at {BASE_URL}: {e}")
        print("  Start the server first: uvicorn src.nlq.main:app --host 0.0.0.0 --port 5000")
        sys.exit(1)

    # Run tests
    results: List[TestResult] = []
    passed = 0
    failed = 0

    print()
    for tc in GROUND_TRUTH:
        result = run_test(client, tc)
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        icon = "✓" if result.passed else "✗"

        if result.passed:
            passed += 1
        else:
            failed += 1

        # Always print summary line
        print(f"  Q{tc.id:02d} [{tc.persona:4s}] {icon} {status} | {tc.question}")
        if verbose or not result.passed:
            if not result.passed:
                print(f"       → {result.details}")

    # Summary
    total = len(results)
    pct = (passed / total * 100) if total > 0 else 0

    print()
    print("=" * 72)
    print(f"  RESULTS: {passed}/{total} passed ({pct:.1f}%)")
    print(f"  PASSED: {passed} | FAILED: {failed}")
    print("=" * 72)

    # Detailed failures
    if failed > 0:
        print("\n  FAILURES:")
        for r in results:
            if not r.passed:
                print(f"    Q{r.tc_id:02d} [{r.persona}] {r.question}")
                print(f"      → {r.details}")
        print()

    # Return exit code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
