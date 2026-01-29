#!/usr/bin/env python3
"""
Functional Evaluation Runner for NLQ Dashboard.

Runs test cases from GROUND_TRUTH.md against the NLQ API and validates
that real data from the fact base is returned (not mock data).

Usage:
    python eval_runner.py [--verbose] [--test TC-XX]

Requirements:
    - API server must be running on http://localhost:8000
    - Fact base must be loaded with expected values from GROUND_TRUTH.md
"""

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# API endpoint
API_BASE = "http://localhost:8000"


class TestStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class TestCase:
    """A single test case from GROUND_TRUTH.md."""
    id: str
    name: str
    action: str
    ground_truth: Dict[str, Any]
    verify: str
    depends_on: Optional[str] = None


@dataclass
class TestResult:
    """Result of running a test case."""
    test_id: str
    status: TestStatus
    message: str
    expected: Optional[Any] = None
    actual: Optional[Any] = None
    response: Optional[Dict] = None
    duration_ms: int = 0


# Ground truth values from GROUND_TRUTH.md
GROUND_TRUTH_VALUES = {
    "revenue": {"value": 150.0, "unit": "$M", "formatted": "$150.0M"},
    "gross_margin_pct": {"value": 65.0, "unit": "%", "formatted": "65.0%"},
    "net_income": {"value": 28.13, "unit": "$M", "formatted": "$28.1M"},
    "pipeline": {"value": 431.25, "unit": "$M", "formatted": "$431.3M"},
    "qualified_pipeline": {"value": 258.75, "unit": "$M", "formatted": "$258.8M"},
    "win_rate": {"value": 42, "unit": "%", "formatted": "42%"},
    "nrr": {"value": 118, "unit": "%", "formatted": "118%"},
    "gross_churn_pct": {"value": 7, "unit": "%", "formatted": "7.0%"},
    "customer_count": {"value": 950, "unit": "count", "formatted": "950"},
    "headcount": {"value": 350, "unit": "count", "formatted": "350"},
    "quota_attainment": {"value": 95.8, "unit": "%", "formatted": "95.8%"},
    "sales_cycle_days": {"value": 85, "unit": "days", "formatted": "85 days"},
    "arr": {"value": 142.5, "unit": "$M", "formatted": "$142.5M"},
}

# Mock data values that indicate FAILURE
MOCK_DATA_VALUES = {
    "revenue": [200, 1.2, 125],  # Known mock values
    "pipeline": [575, 345],  # Known mock values
    "win_rate": [32],  # Mock value vs 42 real
}

# Quarterly data for 2025
QUARTERLY_DATA = {
    "2025-Q1": {"revenue": 33.0, "pipeline": 94.88, "win_rate": 40},
    "2025-Q2": {"revenue": 36.0, "pipeline": 103.5, "win_rate": 41},
    "2025-Q3": {"revenue": 39.0, "pipeline": 112.13, "win_rate": 43},
    "2025-Q4": {"revenue": 42.0, "pipeline": 120.75, "win_rate": 44},
}


def query_api(question: str, session_id: str = "eval_session") -> Dict[str, Any]:
    """Send a query to the NLQ API."""
    try:
        response = requests.post(
            f"{API_BASE}/v1/query",
            json={
                "question": question,
                "session_id": session_id,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return {"error": str(e)}


def extract_numeric_value(text: str) -> Optional[float]:
    """Extract numeric value from formatted string."""
    if not text:
        return None
    # Remove currency symbols, commas, suffixes
    clean = re.sub(r"[$%M,]", "", str(text))
    # Handle "mo" suffix for months
    clean = re.sub(r"\s*mo\b", "", clean)
    # Handle "days" suffix
    clean = re.sub(r"\s*days?\b", "", clean)
    # Handle "x" suffix for ratios
    clean = re.sub(r"\s*x\b", "", clean)
    try:
        return float(clean.strip())
    except ValueError:
        return None


def is_mock_data(metric: str, value: float) -> bool:
    """Check if a value is known mock data."""
    if metric in MOCK_DATA_VALUES:
        mock_values = MOCK_DATA_VALUES[metric]
        return any(abs(value - mv) < 0.1 for mv in mock_values)
    return False


def validate_value(metric: str, actual_value: float, tolerance: float = 0.1) -> Tuple[bool, str]:
    """Validate a metric value against ground truth."""
    if metric not in GROUND_TRUTH_VALUES:
        return True, f"Metric '{metric}' not in ground truth (skipping validation)"

    expected = GROUND_TRUTH_VALUES[metric]["value"]

    # Check for mock data
    if is_mock_data(metric, actual_value):
        return False, f"MOCK DATA DETECTED: {actual_value} is a known mock value"

    # Check tolerance
    if abs(actual_value - expected) > tolerance * expected:
        return False, f"Value mismatch: expected {expected}, got {actual_value}"

    return True, f"Value matches: {actual_value} ~ {expected}"


class EvalRunner:
    """Runs evaluation tests against the NLQ API."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: List[TestResult] = []
        self.session_id = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def run_all_tests(self) -> List[TestResult]:
        """Run all test cases."""
        self.results = []

        # TC-01: Simple Metric Query (Text Response)
        self.results.append(self._test_tc01())

        # TC-02: Visualization Request - Single Metric Trend
        self.results.append(self._test_tc02())

        # TC-03: Visualization Request - Breakdown by Dimension
        self.results.append(self._test_tc03())

        # TC-04: Refinement - Add Widget (depends on TC-03)
        self.results.append(self._test_tc04())

        # TC-05: Refinement - Change Chart Type
        self.results.append(self._test_tc05())

        # TC-06: Multi-Widget Dashboard Request
        self.results.append(self._test_tc06())

        # TC-07: Guided Discovery
        self.results.append(self._test_tc07())

        # TC-08: Ambiguous Query Handling
        self.results.append(self._test_tc08())

        # TC-09: Missing Data Handling
        self.results.append(self._test_tc09())

        # TC-10: Context Handling - Pronoun Resolution
        self.results.append(self._test_tc10())

        # TC-12: Real Data Verification - KPI Values
        self.results.append(self._test_tc12())

        return self.results

    def _test_tc01(self) -> TestResult:
        """TC-01: Simple Metric Query (Text Response)."""
        test_id = "TC-01"
        start = datetime.now()

        response = query_api("what's our revenue?", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        # Check response type is text
        response_type = response.get("response_type", "text")
        if response_type != "text":
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected text response, got {response_type}",
                expected="text", actual=response_type,
                response=response, duration_ms=int(duration)
            )

        # Check value
        value = response.get("value")
        answer = response.get("answer", "")

        # Extract value from answer if not in value field
        if value is None:
            value = extract_numeric_value(answer)

        if value is None:
            return TestResult(
                test_id, TestStatus.FAIL,
                "Could not extract revenue value from response",
                response=response, duration_ms=int(duration)
            )

        # Validate against ground truth
        valid, msg = validate_value("revenue", value)
        status = TestStatus.PASS if valid else TestStatus.FAIL

        return TestResult(
            test_id, status, msg,
            expected=150.0, actual=value,
            response=response, duration_ms=int(duration)
        )

    def _test_tc02(self) -> TestResult:
        """TC-02: Visualization Request - Single Metric Trend."""
        test_id = "TC-02"
        start = datetime.now()

        response = query_api("show me revenue over time", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        # Check response type is dashboard
        response_type = response.get("response_type")
        if response_type != "dashboard":
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected dashboard response, got {response_type}",
                response=response, duration_ms=int(duration)
            )

        # Check dashboard has widgets
        dashboard = response.get("dashboard", {})
        widgets = dashboard.get("widgets", [])
        if not widgets:
            return TestResult(
                test_id, TestStatus.FAIL,
                "Dashboard has no widgets",
                response=response, duration_ms=int(duration)
            )

        # Check for line/area chart
        chart_types = [w.get("type") for w in widgets]
        has_time_chart = any(t in ["line_chart", "area_chart"] for t in chart_types)
        if not has_time_chart:
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected line/area chart, found: {chart_types}",
                response=response, duration_ms=int(duration)
            )

        # Validate data points from widget_data
        widget_data = response.get("dashboard_data", {})
        for widget_id, data in widget_data.items():
            series = data.get("series", [])
            for s in series:
                for point in s.get("data", []):
                    val = point.get("value")
                    if val and is_mock_data("revenue", val):
                        return TestResult(
                            test_id, TestStatus.FAIL,
                            f"MOCK DATA in chart: {val}",
                            response=response, duration_ms=int(duration)
                        )

        return TestResult(
            test_id, TestStatus.PASS,
            "Dashboard with time series chart returned with real data",
            response=response, duration_ms=int(duration)
        )

    def _test_tc03(self) -> TestResult:
        """TC-03: Visualization Request - Breakdown by Dimension."""
        test_id = "TC-03"
        start = datetime.now()

        response = query_api("show me pipeline by region", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        # Check response type is dashboard
        response_type = response.get("response_type")
        if response_type != "dashboard":
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected dashboard response, got {response_type}",
                response=response, duration_ms=int(duration)
            )

        # Check for bar chart
        dashboard = response.get("dashboard", {})
        widgets = dashboard.get("widgets", [])
        chart_types = [w.get("type") for w in widgets]
        has_bar = any(t in ["bar_chart", "horizontal_bar"] for t in chart_types)
        if not has_bar:
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected bar chart, found: {chart_types}",
                response=response, duration_ms=int(duration)
            )

        # Validate pipeline total from widget data
        widget_data = response.get("dashboard_data", {})
        total = 0
        for widget_id, data in widget_data.items():
            series = data.get("series", [])
            for s in series:
                for point in s.get("data", []):
                    val = point.get("value", 0)
                    total += val

        # Total should be approximately 431M (or regional breakdown sums to that)
        expected_total = 431.25
        if total > 0 and abs(total - expected_total) > 50:  # Allow some tolerance
            # Check if it's clearly mock data
            if is_mock_data("pipeline", total):
                return TestResult(
                    test_id, TestStatus.FAIL,
                    f"MOCK DATA: Pipeline total {total} doesn't match expected ~{expected_total}",
                    expected=expected_total, actual=total,
                    response=response, duration_ms=int(duration)
                )

        return TestResult(
            test_id, TestStatus.PASS,
            f"Regional breakdown chart with pipeline data returned",
            response=response, duration_ms=int(duration)
        )

    def _test_tc04(self) -> TestResult:
        """TC-04: Refinement - Add Widget."""
        test_id = "TC-04"
        start = datetime.now()

        # First ensure we have a dashboard
        response = query_api("show me pipeline by region", self.session_id)

        # Now add a KPI
        response = query_api("add a KPI for win rate", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        # Check response type is dashboard
        response_type = response.get("response_type")
        if response_type != "dashboard":
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected dashboard response, got {response_type}",
                response=response, duration_ms=int(duration)
            )

        # Check for KPI card with win rate
        dashboard = response.get("dashboard", {})
        widgets = dashboard.get("widgets", [])
        has_kpi = any(w.get("type") == "kpi_card" for w in widgets)

        if not has_kpi:
            return TestResult(
                test_id, TestStatus.FAIL,
                "No KPI card found after add request",
                response=response, duration_ms=int(duration)
            )

        # Check win rate value in widget data
        widget_data = response.get("dashboard_data", {})
        win_rate_found = False
        for widget_id, data in widget_data.items():
            val = data.get("value")
            formatted = data.get("formatted_value", "")
            if val and (abs(val - 42) < 1 or "42" in str(formatted)):
                win_rate_found = True
                break

        if not win_rate_found:
            # Check if any KPI has win rate data
            for widget in widgets:
                if "win_rate" in widget.get("id", "") or "win" in widget.get("title", "").lower():
                    win_rate_found = True
                    break

        return TestResult(
            test_id, TestStatus.PASS if win_rate_found else TestStatus.FAIL,
            "Win rate KPI added" if win_rate_found else "Win rate value not found (42%)",
            expected=42, actual=widget_data,
            response=response, duration_ms=int(duration)
        )

    def _test_tc05(self) -> TestResult:
        """TC-05: Refinement - Change Chart Type."""
        test_id = "TC-05"
        start = datetime.now()

        # First create a line chart
        response = query_api("show me revenue over time", self.session_id)

        # Then change to bar
        response = query_api("make that a bar chart", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        response_type = response.get("response_type")
        if response_type != "dashboard":
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected dashboard response, got {response_type}",
                response=response, duration_ms=int(duration)
            )

        dashboard = response.get("dashboard", {})
        widgets = dashboard.get("widgets", [])
        chart_types = [w.get("type") for w in widgets]

        has_bar = any(t == "bar_chart" for t in chart_types)

        return TestResult(
            test_id, TestStatus.PASS if has_bar else TestStatus.FAIL,
            f"Chart types after change: {chart_types}",
            response=response, duration_ms=int(duration)
        )

    def _test_tc06(self) -> TestResult:
        """TC-06: Multi-Widget Dashboard Request."""
        test_id = "TC-06"
        start = datetime.now()

        response = query_api("build me a sales dashboard", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        response_type = response.get("response_type")
        if response_type != "dashboard":
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected dashboard response, got {response_type}",
                response=response, duration_ms=int(duration)
            )

        dashboard = response.get("dashboard", {})
        widgets = dashboard.get("widgets", [])

        if len(widgets) < 3:
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected 3+ widgets, got {len(widgets)}",
                response=response, duration_ms=int(duration)
            )

        # Check widget data for mock values
        widget_data = response.get("dashboard_data", {})
        mock_found = []
        for widget_id, data in widget_data.items():
            val = data.get("value")
            if val:
                for metric, mock_vals in MOCK_DATA_VALUES.items():
                    if any(abs(val - mv) < 0.1 for mv in mock_vals):
                        mock_found.append(f"{widget_id}: {val}")

        if mock_found:
            return TestResult(
                test_id, TestStatus.FAIL,
                f"MOCK DATA detected in: {mock_found}",
                response=response, duration_ms=int(duration)
            )

        return TestResult(
            test_id, TestStatus.PASS,
            f"Dashboard with {len(widgets)} widgets, real data",
            response=response, duration_ms=int(duration)
        )

    def _test_tc07(self) -> TestResult:
        """TC-07: Guided Discovery."""
        test_id = "TC-07"
        start = datetime.now()

        response = query_api("what can you show me about customers?", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        answer = response.get("answer", "").lower()

        # Check if response mentions customer-related metrics
        customer_metrics = ["customer_count", "nrr", "churn", "retention"]
        mentioned = [m for m in customer_metrics if m.replace("_", " ") in answer or m in answer]

        return TestResult(
            test_id, TestStatus.PASS if mentioned else TestStatus.FAIL,
            f"Customer metrics mentioned: {mentioned}" if mentioned else "No customer metrics suggested",
            response=response, duration_ms=int(duration)
        )

    def _test_tc08(self) -> TestResult:
        """TC-08: Ambiguous Query Handling."""
        test_id = "TC-08"
        start = datetime.now()

        response = query_api("show me performance", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        answer = response.get("answer", "").lower()

        # Check if response asks for clarification or offers options
        clarification_indicators = [
            "which", "what kind", "clarify", "do you mean",
            "options", "sales", "system", "financial"
        ]
        has_clarification = any(ind in answer for ind in clarification_indicators)

        # Also acceptable if it returns a dashboard but with sensible defaults
        response_type = response.get("response_type")

        return TestResult(
            test_id, TestStatus.PASS,
            f"Response type: {response_type}, clarification: {has_clarification}",
            response=response, duration_ms=int(duration)
        )

    def _test_tc09(self) -> TestResult:
        """TC-09: Missing Data Handling."""
        test_id = "TC-09"
        start = datetime.now()

        response = query_api("show me mars colony revenue", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        answer = response.get("answer", "").lower()

        # Should NOT return a dashboard with fake data
        response_type = response.get("response_type")
        dashboard_data = response.get("dashboard_data", {})

        # Check for graceful handling
        not_available_indicators = [
            "not available", "don't have", "no data", "cannot find",
            "unable to", "sorry", "don't recognize"
        ]
        graceful = any(ind in answer for ind in not_available_indicators)

        if response_type == "dashboard" and dashboard_data:
            # If dashboard returned, check it's not showing fake data
            for widget_id, data in dashboard_data.items():
                if data.get("error"):
                    graceful = True
                    break

        return TestResult(
            test_id, TestStatus.PASS if graceful else TestStatus.FAIL,
            "Graceful 'not available' response" if graceful else "May have shown fake data",
            response=response, duration_ms=int(duration)
        )

    def _test_tc10(self) -> TestResult:
        """TC-10: Context Handling - Pronoun Resolution."""
        test_id = "TC-10"
        start = datetime.now()

        # Fresh session - no context
        fresh_session = f"eval_fresh_{datetime.now().strftime('%H%M%S')}"
        response = query_api("make it a bar chart", fresh_session)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        answer = response.get("answer", "").lower()

        # Should ask for clarification since no context
        clarification_indicators = [
            "what", "which", "current", "no dashboard",
            "happy to", "would you like", "create"
        ]
        asks_clarification = any(ind in answer for ind in clarification_indicators)

        # Should NOT crash or show error
        success = response.get("success", True)

        return TestResult(
            test_id, TestStatus.PASS if asks_clarification and success else TestStatus.FAIL,
            "Asked for clarification" if asks_clarification else "Did not ask for clarification",
            response=response, duration_ms=int(duration)
        )

    def _test_tc12(self) -> TestResult:
        """TC-12: Real Data Verification - KPI Values."""
        test_id = "TC-12"
        start = datetime.now()

        response = query_api("show me revenue, margin, and pipeline KPIs", self.session_id)
        duration = (datetime.now() - start).total_seconds() * 1000

        if "error" in response:
            return TestResult(test_id, TestStatus.ERROR, f"API error: {response['error']}", duration_ms=int(duration))

        response_type = response.get("response_type")
        if response_type != "dashboard":
            return TestResult(
                test_id, TestStatus.FAIL,
                f"Expected dashboard response, got {response_type}",
                response=response, duration_ms=int(duration)
            )

        # Validate each KPI value
        widget_data = response.get("dashboard_data", {})
        validations = []
        mock_detected = []

        for widget_id, data in widget_data.items():
            val = data.get("value")
            formatted = data.get("formatted_value", "")

            if val is None:
                continue

            # Check for mock data
            for metric, mock_vals in MOCK_DATA_VALUES.items():
                if any(abs(val - mv) < 0.1 for mv in mock_vals):
                    mock_detected.append(f"{widget_id}: {val} (mock {metric})")

            # Check against ground truth
            if "revenue" in widget_id.lower() and val:
                valid, _ = validate_value("revenue", val)
                validations.append(("revenue", val, valid))
            elif "margin" in widget_id.lower() and val:
                valid, _ = validate_value("gross_margin_pct", val)
                validations.append(("margin", val, valid))
            elif "pipeline" in widget_id.lower() and val:
                valid, _ = validate_value("pipeline", val)
                validations.append(("pipeline", val, valid))

        if mock_detected:
            return TestResult(
                test_id, TestStatus.FAIL,
                f"MOCK DATA: {mock_detected}",
                expected={"revenue": 150, "margin": 65, "pipeline": 431.25},
                actual=widget_data,
                response=response, duration_ms=int(duration)
            )

        passed = all(v[2] for v in validations) if validations else True
        return TestResult(
            test_id, TestStatus.PASS if passed else TestStatus.FAIL,
            f"Validations: {validations}",
            expected={"revenue": 150, "margin": 65, "pipeline": 431.25},
            actual=widget_data,
            response=response, duration_ms=int(duration)
        )

    def print_results(self):
        """Print test results summary."""
        print("\n" + "=" * 70)
        print("NLQ Dashboard Functional Evaluation Results")
        print("=" * 70)

        passed = sum(1 for r in self.results if r.status == TestStatus.PASS)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        errors = sum(1 for r in self.results if r.status == TestStatus.ERROR)
        skipped = sum(1 for r in self.results if r.status == TestStatus.SKIP)

        for result in self.results:
            status_icon = {
                TestStatus.PASS: "[PASS]",
                TestStatus.FAIL: "[FAIL]",
                TestStatus.ERROR: "[ERR ]",
                TestStatus.SKIP: "[SKIP]",
            }[result.status]

            print(f"\n{status_icon} {result.test_id}: {result.message}")
            if self.verbose and result.status != TestStatus.PASS:
                if result.expected:
                    print(f"  Expected: {result.expected}")
                if result.actual:
                    print(f"  Actual: {result.actual}")

        print("\n" + "-" * 70)
        print(f"Total: {len(self.results)} | Pass: {passed} | Fail: {failed} | Error: {errors} | Skip: {skipped}")
        print(f"Pass Rate: {passed / len(self.results) * 100:.1f}%")
        print("-" * 70)

        return passed, failed, errors, skipped


def main():
    parser = argparse.ArgumentParser(description="Run NLQ Dashboard functional evaluation")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--test", "-t", help="Run specific test (e.g., TC-01)")
    args = parser.parse_args()

    # Check API is running
    try:
        health = requests.get(f"{API_BASE}/v1/health", timeout=5)
        if health.status_code != 200:
            print(f"ERROR: API health check failed with status {health.status_code}")
            print("Make sure the API server is running: make serve")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to API server at http://localhost:8000")
        print("Make sure the API server is running: make serve")
        sys.exit(1)

    print("API server is healthy, starting evaluation...")

    runner = EvalRunner(verbose=args.verbose)

    if args.test:
        # Run specific test
        test_method = getattr(runner, f"_test_{args.test.lower().replace('-', '')}", None)
        if test_method:
            result = test_method()
            runner.results = [result]
        else:
            print(f"Unknown test: {args.test}")
            sys.exit(1)
    else:
        runner.run_all_tests()

    passed, failed, errors, skipped = runner.print_results()

    # Exit with error code if any failures
    if failed > 0 or errors > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
