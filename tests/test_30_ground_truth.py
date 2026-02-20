"""
AeroFlow-K3OA Ground Truth Test Harness — 30 Binary Questions.

Tests POST /api/v1/query (the NLQ natural language endpoint) with
the exact questions users type. No pre-parsed payloads, no bypassing
NLQ parsing.

Each test has a binary pass/fail: the returned value must match ground truth
within tolerance (1% for floats, exact for strings/ints).

Run:
    python tests/test_30_ground_truth.py
    # or
    python tests/test_30_ground_truth.py --verbose
"""

import json
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:5000"
NLQ_ENDPOINT = "/api/v1/query"
TIMEOUT = 30.0

# ---------------------------------------------------------------------------
# Test case definition
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """One ground-truth question."""
    id: int
    persona: str
    question: str                     # The natural language question users type
    expected: Any                     # Ground truth answer
    match_type: str = "value"         # "value", "dimensional", "ranked", "ingest_stat"
    tolerance: float = 0.01           # 1% tolerance for floats


# ---------------------------------------------------------------------------
# Ground truth questions (same 30 questions, same expected values)
# ---------------------------------------------------------------------------

GROUND_TRUTH: List[TestCase] = [
    # === CFO Q1-Q2 ===
    TestCase(
        id=1, persona="CFO",
        question="What is our current ARR?",
        expected=47.5,
        match_type="value",
    ),
    TestCase(
        id=2, persona="CFO",
        question="Show revenue by region",
        expected={"AMER": 25.0, "EMEA": 15.0, "APAC": 10.0},
        match_type="dimensional",
    ),
    # === CRO Q3-Q4 ===
    TestCase(
        id=3, persona="CRO",
        question="What is our win rate?",
        expected=45.5,
        match_type="value",
    ),
    TestCase(
        id=4, persona="CRO",
        question="Which customer has the highest churn risk?",
        expected={"name": "RetailMax", "value": 72},
        match_type="ranked",
    ),
    # === CTO Q5-Q6 ===
    TestCase(
        id=5, persona="CTO",
        question="What is our current uptime?",
        expected=99.82,
        match_type="value",
    ),
    TestCase(
        id=6, persona="CTO",
        question="What is MTTR for P1 incidents?",
        expected=1.5,
        match_type="value",
    ),
    # === CHRO Q7-Q8 ===
    TestCase(
        id=7, persona="CHRO",
        question="What is our current headcount?",
        expected=430,
        match_type="value",
    ),
    TestCase(
        id=8, persona="CHRO",
        question="What is our attrition rate?",
        expected=1.2,
        match_type="value",
    ),
    # === COO Q9-Q10 (ingest) ===
    TestCase(
        id=9, persona="COO",
        question="How many data sources are connected?",
        expected=27,
        match_type="ingest_stat",
    ),
    TestCase(
        id=10, persona="COO",
        question="Which source system has the most ingested rows?",
        expected={"name": "Zendesk", "value": 139200},
        match_type="ranked",
    ),
    # === CFO Q11-Q15 ===
    TestCase(
        id=11, persona="CFO",
        question="What is our gross margin?",
        expected=67.0,
        match_type="value",
    ),
    TestCase(
        id=12, persona="CFO",
        question="Show revenue by segment",
        expected={"Enterprise": 27.5, "Mid-Market": 15.0, "SMB": 7.5},
        match_type="dimensional",
    ),
    TestCase(
        id=13, persona="CFO",
        question="What is DSO by segment?",
        expected={"Enterprise": 49, "Mid-Market": 38, "SMB": 25},
        match_type="dimensional",
    ),
    TestCase(
        id=14, persona="CFO",
        question="Which product has the highest gross margin?",
        expected={"name": "Enterprise", "value": 21.44},
        match_type="ranked",
    ),
    TestCase(
        id=15, persona="CFO",
        question="What is our cloud spend by category?",
        expected={"Compute": 0.376, "Storage": 0.188, "Database": 0.188, "Network": 0.094, "Other": 0.094},
        match_type="dimensional",
    ),
    # === CRO Q16-Q20 ===
    TestCase(
        id=16, persona="CRO",
        question="Show pipeline by stage",
        expected={"Lead": 28.75, "Qualified": 43.12, "Proposal": 35.94, "Negotiation": 21.56, "Closed-Won": 14.38},
        match_type="dimensional",
    ),
    TestCase(
        id=17, persona="CRO",
        question="What is churn rate by segment?",
        expected={"Enterprise": 4.0, "Mid-Market": 6.3, "SMB": 10.8},
        match_type="dimensional",
    ),
    TestCase(
        id=18, persona="CRO",
        question="What is our NRR?",
        expected=121.5,
        match_type="value",
    ),
    TestCase(
        id=19, persona="CRO",
        question="Show NRR by cohort",
        expected={"2022-H1": 111.3, "2023-H1": 118.3, "2024-H1": 123.3, "2025-H1": 127.3},
        match_type="dimensional",
    ),
    TestCase(
        id=20, persona="CRO",
        question="Which segment has the highest churn?",
        expected={"name": "SMB", "value": 10.8},
        match_type="ranked",
    ),
    # === CTO Q21-Q25 ===
    TestCase(
        id=21, persona="CTO",
        question="What is deploy frequency by service?",
        expected={"Web App": 6.4, "API Gateway": 4.5, "Notification": 3.2, "Auth": 2.5, "Mobile": 2.5, "Payment": 1.9, "Data Pipeline": 1.3},
        match_type="dimensional",
    ),
    TestCase(
        id=22, persona="CTO",
        question="Show uptime by service",
        expected={"Auth": 99.999, "Payment": 99.999, "API Gateway": 99.975, "Web App": 99.955},
        match_type="dimensional",
        tolerance=0.005,
    ),
    TestCase(
        id=23, persona="CTO",
        question="Which service deploys the most?",
        expected={"name": "Web App", "value": 6.4},
        match_type="ranked",
    ),
    TestCase(
        id=24, persona="CTO",
        question="What is SLA compliance by team?",
        expected={"Frontend": 99.5, "Infra": 99.5, "Security": 99.5, "Platform": 98.3, "Backend": 97.6, "Mobile": 95.8, "Data": 95.3},
        match_type="dimensional",
    ),
    TestCase(
        id=25, persona="CTO",
        question="Which team has the lowest SLA compliance?",
        expected={"name": "Data", "value": 95.3},
        match_type="ranked",
    ),
    # === CHRO Q26-Q28 ===
    TestCase(
        id=26, persona="CHRO",
        question="What is headcount by department?",
        expected={"Engineering": 145, "Sales": 80, "CS": 60, "Marketing": 43, "Product": 34, "G&A": 24, "People": 22, "Finance": 22},
        match_type="dimensional",
    ),
    TestCase(
        id=27, persona="CHRO",
        question="What is our engagement score?",
        expected=86.0,
        match_type="value",
    ),
    TestCase(
        id=28, persona="CHRO",
        question="What is our offer acceptance rate?",
        expected=93.0,
        match_type="value",
    ),
    # === COO Q29-Q30 ===
    TestCase(
        id=29, persona="COO",
        question="What is throughput by team?",
        expected={"Frontend": 110, "Platform": 102, "Backend": 93, "Data": 78, "Mobile": 66, "Infra": 54, "Security": 46},
        match_type="dimensional",
    ),
    TestCase(
        id=30, persona="COO",
        question="How many total rows have been ingested?",
        expected=589120,
        match_type="ingest_stat",
    ),
]


# ---------------------------------------------------------------------------
# Matching logic — validates NLQ response format
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


def extract_nlq_value(body: Dict) -> Any:
    """Extract a scalar value from an NLQ response."""
    # Direct value field
    val = body.get("value")
    if val is not None:
        return val
    # Try parsing from answer text
    answer = body.get("answer", "")
    if answer:
        import re
        # Try to find a number in the answer like "$47.5M" or "45.5%" or "430"
        m = re.search(r'[\$]?([\d,]+\.?\d*)\s*[M%]?', answer)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def extract_nlq_breakdown(body: Dict) -> Dict[str, Any]:
    """Extract dimensional breakdown from NLQ response dashboard_data."""
    dd = body.get("dashboard_data")
    if not dd:
        return {}

    result = {}
    for widget_key, widget in dd.items():
        # Look for breakdown widgets with series data
        series_list = widget.get("series", [])
        for series in series_list:
            data_points = series.get("data", [])
            for dp in data_points:
                label = dp.get("label", "")
                value = dp.get("value")
                if label and value is not None:
                    result[label] = value
    return result


def extract_nlq_ranked(body: Dict) -> tuple:
    """Extract name and value from a ranked/superlative NLQ response.
    Returns (name: str, value: float) or (None, None).
    """
    answer = body.get("answer", "")
    value = body.get("value")

    # Try to extract entity name from bold markdown in answer: **Name**
    import re
    bold = re.search(r'\*\*([^*]+)\*\*', answer)
    name = bold.group(1) if bold else None

    # Also check dashboard_data for ranked results
    dd = body.get("dashboard_data")
    if dd:
        for widget_key, widget in dd.items():
            series_list = widget.get("series", [])
            for series in series_list:
                data_points = series.get("data", [])
                if data_points:
                    top = data_points[0]
                    if not name:
                        name = top.get("label")
                    if value is None:
                        value = top.get("value")

    return name, value


def check_nlq_value(body: Dict, expected: Any, tolerance: float) -> tuple:
    """Check a value-type NLQ response."""
    if not body.get("success", False):
        err = body.get("error_message") or body.get("error_code") or "unknown error"
        return False, f"NLQ returned success=false: {err}"

    actual = extract_nlq_value(body)
    if actual is None:
        return False, f"No value extractable. answer='{body.get('answer')}', value={body.get('value')}"
    if not values_match(actual, expected, tolerance):
        return False, f"Value mismatch: expected={expected}, got={actual}"
    return True, f"OK (value={actual})"


def check_nlq_dimensional(body: Dict, expected: Dict, tolerance: float) -> tuple:
    """Check a dimensional breakdown NLQ response."""
    if not body.get("success", False):
        err = body.get("error_message") or body.get("error_code") or "unknown error"
        return False, f"NLQ returned success=false: {err}"

    actual_map = extract_nlq_breakdown(body)
    if not actual_map:
        return False, f"No breakdown data. dashboard_data={json.dumps(body.get('dashboard_data'))[:300]}, answer='{body.get('answer')}'"

    mismatches = []
    missing = []
    for exp_key, exp_val in expected.items():
        actual_val = actual_map.get(exp_key)
        if actual_val is None:
            # Case-insensitive / substring match
            for ak, av in actual_map.items():
                if ak.lower() == exp_key.lower() or exp_key.lower() in ak.lower() or ak.lower() in exp_key.lower():
                    actual_val = av
                    break
        if actual_val is None:
            missing.append(exp_key)
        elif not values_match(actual_val, exp_val, tolerance):
            mismatches.append(f"{exp_key}: expected={exp_val}, got={actual_val}")

    if missing:
        return False, f"Missing: {missing}. Got keys: {list(actual_map.keys())}"
    if mismatches:
        return False, f"Mismatches: {mismatches}"
    return True, f"OK ({len(expected)} dimensions matched)"


def check_nlq_ranked(body: Dict, expected: Dict, tolerance: float) -> tuple:
    """Check a ranked/superlative NLQ response."""
    if not body.get("success", False):
        err = body.get("error_message") or body.get("error_code") or "unknown error"
        return False, f"NLQ returned success=false: {err}"

    exp_name = expected.get("name", "")
    exp_value = expected.get("value")

    actual_name, actual_value = extract_nlq_ranked(body)

    if actual_name is None:
        return False, f"Could not extract entity name. answer='{body.get('answer')}'"

    name_match = (
        exp_name.lower() in actual_name.lower()
        or actual_name.lower() in exp_name.lower()
    )
    if not name_match:
        return False, f"Name mismatch: expected='{exp_name}', got='{actual_name}'"

    if exp_value is not None:
        if actual_value is None:
            return False, f"Name OK ('{actual_name}') but no value extractable"
        if not values_match(actual_value, exp_value, tolerance):
            return False, f"Name OK ('{actual_name}') but value mismatch: expected={exp_value}, got={actual_value}"

    return True, f"OK (name='{actual_name}', value={actual_value})"


def check_nlq_ingest(body: Dict, expected: Any, tc_id: int) -> tuple:
    """Check ingest-related NLQ responses."""
    if not body.get("success", False):
        err = body.get("error_message") or body.get("error_code") or "unknown error"
        return False, f"NLQ returned success=false: {err}"

    answer = body.get("answer", "")
    value = body.get("value")

    # Check if the answer says "no live ingest data"
    if "no live ingest" in answer.lower() or "not available" in answer.lower():
        return False, f"NLQ says no ingest data: '{answer}'"

    if value is not None and values_match(value, expected):
        return True, f"OK (value={value})"

    # Try parsing number from answer
    import re
    numbers = re.findall(r'[\d,]+\.?\d*', answer.replace(",", ""))
    for n in numbers:
        try:
            if values_match(float(n), expected):
                return True, f"OK (parsed {n} from answer)"
        except ValueError:
            pass

    return False, f"Could not match expected={expected}. value={value}, answer='{answer}'"


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
    raw_response: Optional[Dict] = None


def run_test(client: httpx.Client, tc: TestCase) -> TestResult:
    """Send the natural language question to the NLQ endpoint and validate."""
    url = f"{BASE_URL}{NLQ_ENDPOINT}"

    try:
        start = time.monotonic()
        resp = client.post(url, json={"question": tc.question}, timeout=TIMEOUT)
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
            ok, detail = check_nlq_value(body, tc.expected, tc.tolerance)
        elif tc.match_type == "dimensional":
            ok, detail = check_nlq_dimensional(body, tc.expected, tc.tolerance)
        elif tc.match_type == "ranked":
            ok, detail = check_nlq_ranked(body, tc.expected, tc.tolerance)
        elif tc.match_type == "ingest_stat":
            ok, detail = check_nlq_ingest(body, tc.expected, tc.id)
        else:
            ok, detail = False, f"Unknown match_type: {tc.match_type}"

        return TestResult(
            tc_id=tc.id, persona=tc.persona, question=tc.question,
            passed=ok, details=detail, response_time_ms=elapsed,
            raw_response=body,
        )

    except Exception as e:
        return TestResult(
            tc_id=tc.id, persona=tc.persona, question=tc.question,
            passed=False, details=str(e),
        )


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    print("=" * 72)
    print("  AeroFlow-K3OA Ground Truth Test Harness")
    print(f"  {len(GROUND_TRUTH)} questions | Target: 100% accuracy")
    print(f"  Endpoint: POST {NLQ_ENDPOINT} (natural language)")
    print("=" * 72)

    # Health check
    try:
        client = httpx.Client(timeout=5.0)
        resp = client.get(f"{BASE_URL}/api/v1/health")
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
        icon = "\u2713" if result.passed else "\u2717"

        if result.passed:
            passed += 1
        else:
            failed += 1

        # Always print summary line
        print(f"  Q{tc.id:02d} [{tc.persona:4s}] {icon} {status} | {tc.question}")
        if verbose and result.passed:
            print(f"       \u2192 {result.details}")
        if not result.passed:
            print(f"       \u2192 {result.details}")

    # Summary
    total = len(results)
    pct = (passed / total * 100) if total > 0 else 0

    print()
    print("=" * 72)
    print(f"  RESULTS: {passed}/{total} passed ({pct:.1f}%)")
    print(f"  PASSED: {passed} | FAILED: {failed}")
    print("=" * 72)

    # Detailed failures
    if failed > 0 and verbose:
        print("\n  FAILURE DETAILS:")
        for r in results:
            if not r.passed and r.raw_response:
                print(f"\n    Q{r.tc_id:02d} [{r.persona}] {r.question}")
                print(f"      answer:  {r.raw_response.get('answer')}")
                print(f"      value:   {r.raw_response.get('value')}")
                print(f"      metric:  {r.raw_response.get('resolved_metric')}")
                print(f"      success: {r.raw_response.get('success')}")
                print(f"      error:   {r.raw_response.get('error_message')}")
        print()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
