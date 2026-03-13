#!/usr/bin/env python3
"""
NLQ Structural Integrity Test Suite
Tests response shape, not specific values.
"""

import requests
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

BASE_URL = "https://aos-nlq.onrender.com"

@dataclass
class FieldCheck:
    """Single field validation."""
    name: str
    expected_type: str  # "currency", "percentage", "integer", "ratio"
    required: bool = True

@dataclass
class TestCase:
    """Structural test case."""
    id: int
    query: str
    category: str
    expected_fields: List[FieldCheck]

@dataclass
class TestResult:
    """Test result."""
    test_id: int
    query: str
    status: str  # PASS, FAIL, PARTIAL
    details: str
    response: Optional[Dict[str, Any]] = None

# Test suite definition
TEST_SUITE = [
    # FINANCIAL STRUCTURE
    TestCase(1, "2025 P&L", "FINANCIAL",
        [FieldCheck("revenue", "currency"),
         FieldCheck("cogs", "currency"),
         FieldCheck("gross_profit", "currency"),
         FieldCheck("operating_expense", "currency"),
         FieldCheck("net_income", "currency")]),

    TestCase(2, "what is our gross margin", "FINANCIAL",
        [FieldCheck("gross_margin_pct", "percentage")]),

    TestCase(3, "operating margin", "FINANCIAL",
        [FieldCheck("operating_margin_pct", "percentage")]),

    TestCase(4, "net margin", "FINANCIAL",
        [FieldCheck("net_margin_pct", "percentage")]),

    TestCase(5, "show me EBITDA", "FINANCIAL",
        [FieldCheck("ebitda", "currency")]),

    TestCase(6, "cash position", "FINANCIAL",
        [FieldCheck("cash", "currency")]),

    # REVENUE STRUCTURE
    TestCase(7, "ARR", "REVENUE",
        [FieldCheck("arr", "currency")]),

    TestCase(8, "MRR", "REVENUE",
        [FieldCheck("mrr", "currency")]),

    TestCase(9, "revenue by quarter", "REVENUE",
        [FieldCheck("quarterly_data", "timeseries")]),  # Special: needs at least 2 periods

    TestCase(10, "pipeline", "REVENUE",
        [FieldCheck("pipeline", "currency")]),

    # SALES STRUCTURE
    TestCase(11, "win rate", "SALES",
        [FieldCheck("win_rate", "percentage")]),

    TestCase(12, "quota attainment", "SALES",
        [FieldCheck("quota_attainment", "percentage")]),

    TestCase(13, "NRR", "SALES",
        [FieldCheck("nrr", "percentage")]),

    TestCase(14, "average deal size", "SALES",
        [FieldCheck("avg_deal_size", "currency")]),

    # PEOPLE STRUCTURE
    TestCase(15, "how many people do we have", "PEOPLE",
        [FieldCheck("headcount", "integer")]),

    TestCase(16, "attrition rate", "PEOPLE",
        [FieldCheck("attrition_rate", "percentage")]),

    TestCase(17, "time to fill", "PEOPLE",
        [FieldCheck("time_to_fill", "integer")]),

    # OPERATIONS STRUCTURE
    TestCase(18, "uptime", "OPERATIONS",
        [FieldCheck("uptime_pct", "percentage")]),

    TestCase(19, "incidents this quarter", "OPERATIONS",
        [FieldCheck("incident_count", "integer")]),

    TestCase(20, "burn rate", "OPERATIONS",
        [FieldCheck("burn_rate", "currency")]),
]

def query_nlq(question: str, data_mode: str = "live") -> Dict[str, Any]:
    """Execute NLQ query."""
    url = f"{BASE_URL}/api/v1/query"
    payload = {"question": question, "data_mode": data_mode}

    try:
        response = requests.post(url, json=payload, timeout=60)
        return response.json()
    except Exception as e:
        return {"error": str(e), "success": False}

def infer_unit_type(value: Any, unit: str, metric: str) -> str:
    """Infer unit type from response."""
    if unit in ("USD millions", "USD", "$"):
        return "currency"
    elif unit == "%":
        return "percentage"
    elif unit in ("count", "people", ""):
        if isinstance(value, int) or (isinstance(value, float) and value == int(value)):
            return "integer"
        return "count"
    elif unit in ("days", "hours"):
        return "integer"
    elif unit in ("ratio", ""):
        if isinstance(value, float) and 0 <= value <= 10:
            return "ratio"

    # Fallback: infer from metric name
    if "pct" in metric or "rate" in metric or "margin" in metric:
        return "percentage"
    if "count" in metric or "headcount" in metric:
        return "integer"
    if any(x in metric for x in ["revenue", "arr", "mrr", "cash", "ebitda", "pipeline"]):
        return "currency"

    return "unknown"

def validate_response(response: Dict[str, Any], test_case: TestCase) -> TestResult:
    """Validate response structure."""
    if not response.get("success"):
        return TestResult(
            test_id=test_case.id,
            query=test_case.query,
            status="FAIL",
            details=f"Query failed: {response.get('error_message', 'Unknown error')}",
            response=response
        )

    # Check basic required fields
    value = response.get("value")
    unit = response.get("unit", "")
    confidence = response.get("confidence", 0)
    data_source = response.get("data_source")

    failures = []
    partials = []

    # 1. Field present and not null
    if value is None:
        failures.append("value is null")

    # 2. Confidence score > 0
    if confidence <= 0:
        failures.append(f"confidence={confidence} (must be > 0)")

    # 3. Source attribution present
    if not data_source:
        failures.append("no data_source attribution")

    # 4. Unit type validation
    if value is not None:
        actual_type = infer_unit_type(value, unit, response.get("resolved_metric", ""))

        # For simple queries, check against first expected field
        if len(test_case.expected_fields) == 1:
            expected = test_case.expected_fields[0]
            if actual_type != expected.expected_type:
                partials.append(f"unit type mismatch: expected {expected.expected_type}, got {actual_type} (unit='{unit}')")

    # Special case: timeseries queries
    if test_case.id == 9:  # "revenue by quarter"
        # Check if we have multiple data points
        related_metrics = response.get("related_metrics", [])
        if not related_metrics or len(related_metrics) < 2:
            failures.append(f"timeseries query returned {len(related_metrics) if related_metrics else 0} periods (expected >= 2)")

    # Determine status
    if failures:
        status = "FAIL"
        details = "; ".join(failures)
    elif partials:
        status = "PARTIAL"
        details = "; ".join(partials)
    else:
        status = "PASS"
        details = f"value={value}, unit={unit}, confidence={confidence}, source={data_source}"

    return TestResult(
        test_id=test_case.id,
        query=test_case.query,
        status=status,
        details=details,
        response=response
    )

def run_test_suite():
    """Run all structural tests."""
    print("=" * 80)
    print("NLQ STRUCTURAL INTEGRITY TEST SUITE")
    print("=" * 80)
    print(f"Testing against: {BASE_URL}")
    print(f"Mode: data_mode=live")
    print(f"Total tests: {len(TEST_SUITE)}\n")

    results = []

    for test_case in TEST_SUITE:
        print(f"\n[Test {test_case.id:2d}] {test_case.category}: \"{test_case.query}\"")
        print("-" * 80)

        response = query_nlq(test_case.query, data_mode="live")
        result = validate_response(response, test_case)
        results.append(result)

        # Print result
        status_symbol = {"PASS": "[PASS]", "FAIL": "[FAIL]", "PARTIAL": "[PART]"}[result.status]
        print(f"{status_symbol} {result.details}")

        # Print response excerpt for failures
        if result.status != "PASS" and result.response:
            print(f"   Response: success={result.response.get('success')}, "
                  f"value={result.response.get('value')}, "
                  f"unit={result.response.get('unit')}, "
                  f"error={result.response.get('error_message')}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    pass_count = sum(1 for r in results if r.status == "PASS")
    fail_count = sum(1 for r in results if r.status == "FAIL")
    partial_count = sum(1 for r in results if r.status == "PARTIAL")

    print(f"PASS:    {pass_count:2d} / {len(results)}")
    print(f"PARTIAL: {partial_count:2d} / {len(results)}")
    print(f"FAIL:    {fail_count:2d} / {len(results)}")
    print(f"Score:   {pass_count / len(results) * 100:.1f}%\n")

    # Failure summary
    if fail_count > 0 or partial_count > 0:
        print("\nFAILURES AND PARTIALS:")
        print("-" * 80)
        for r in results:
            if r.status in ("FAIL", "PARTIAL"):
                print(f"[{r.test_id:2d}] {r.status:7s} | {r.query:30s} | {r.details}")

    return results

if __name__ == "__main__":
    run_test_suite()
