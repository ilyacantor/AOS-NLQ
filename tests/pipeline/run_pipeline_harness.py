#!/usr/bin/env python3
"""
Pipeline Integration Test Harness
===================================
22-test HTTP-only harness (PI_001–PI_021, including PI_002B freshness gate)
validating the Farm → DCL → NLQ dual-entity pipeline end-to-end.

RULES:
  1. HTTP only — no cross-repo Python imports
  2. No fact_base.json — never imported, read, or referenced
  3. Loud failures — every fail prints expected vs actual, endpoint, latency
  4. Exit code 0 = all pass, 1 = any fail

Usage:
    python tests/pipeline/run_pipeline_harness.py
    python tests/pipeline/run_pipeline_harness.py --run-id farm_abc123
    python tests/pipeline/run_pipeline_harness.py --farm-url http://localhost:8003
    python tests/pipeline/run_pipeline_harness.py --test PI_001
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

HARNESS_DIR = Path(__file__).resolve().parent
TEST_CASES_FILE = HARNESS_DIR / "test_cases.yaml"
TIMEOUT = 120.0

# ═══════════════════════════════════════════════════════════════════════════════
# Terminal colours
# ═══════════════════════════════════════════════════════════════════════════════

class _C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ═══════════════════════════════════════════════════════════════════════════════
# Assertion evaluator
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_field(data: Any, field: str) -> Any:
    """Dot-path field resolution into nested dicts."""
    if field == "_body":
        return data if isinstance(data, str) else json.dumps(data)
    parts = field.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current


def _evaluate_assertion(
    data: Any, assertion: Dict, status_code: int, latency_ms: float
) -> tuple[bool, str]:
    """Evaluate a single assertion. Returns (passed, detail_message)."""
    field = assertion["field"]
    op = assertion["operator"]
    expected = assertion.get("expected")

    # Special fields
    if field == "_status":
        actual = status_code
    elif field == "_latency_ms":
        actual = latency_ms
    elif field == "_body":
        actual = data if isinstance(data, str) else json.dumps(data)
    else:
        actual = _resolve_field(data, field)

    # Operators
    if op == "not_null":
        passed = actual is not None
        return passed, f"{field}: {'present' if passed else 'NULL'}"

    elif op == "equals":
        passed = str(actual) == str(expected)
        return passed, f"{field}: {actual} {'==' if passed else '!='} {expected}"

    elif op == "not_equals":
        passed = str(actual) != str(expected)
        return passed, f"{field}: {actual} {'!=' if passed else '=='} {expected}"

    elif op == "greater_than":
        try:
            passed = float(actual) > float(expected)
        except (TypeError, ValueError):
            return False, f"{field}: cannot compare {actual} > {expected}"
        return passed, f"{field}: {actual} {'>' if passed else '<='} {expected}"

    elif op == "less_than":
        try:
            passed = float(actual) < float(expected)
        except (TypeError, ValueError):
            return False, f"{field}: cannot compare {actual} < {expected}"
        return passed, f"{field}: {actual} {'<' if passed else '>='} {expected}"

    elif op == "contains":
        actual_str = str(actual).lower() if actual else ""
        passed = str(expected).lower() in actual_str
        return passed, f"{field}: {'contains' if passed else 'missing'} '{expected}'"

    elif op == "contains_any":
        actual_str = str(actual).lower() if actual else ""
        matched = [e for e in expected if str(e).lower() in actual_str]
        passed = len(matched) > 0
        return passed, f"{field}: matched {matched} from {expected}" if passed else f"{field}: none of {expected} found"

    elif op == "not_in":
        passed = actual not in expected
        return passed, f"{field}: {actual} {'not in' if passed else 'in'} {expected}"

    elif op == "in_range":
        try:
            val = float(actual)
            lo, hi = float(expected[0]), float(expected[1])
            passed = lo <= val <= hi
        except (TypeError, ValueError, IndexError):
            return False, f"{field}: cannot evaluate range for {actual}"
        return passed, f"{field}: {actual} {'in' if passed else 'outside'} [{lo}, {hi}]"

    else:
        return False, f"Unknown operator: {op}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test runner
# ═══════════════════════════════════════════════════════════════════════════════

class PipelineHarness:
    def __init__(
        self,
        farm_url: str = "http://localhost:8003",
        dcl_url: str = "http://localhost:8004",
        nlq_url: str = "http://localhost:8005",
        run_id: Optional[str] = None,
        verbose: bool = False,
    ):
        self.urls = {"farm": farm_url, "dcl": dcl_url, "nlq": nlq_url}
        self.run_id = run_id
        self.verbose = verbose
        self.client = httpx.Client(timeout=TIMEOUT)
        self.captured: Dict[str, Any] = {}  # values captured across tests
        self.results: List[Dict] = []

    def _service_url(self, service: str) -> str:
        return self.urls.get(service, self.urls["nlq"])

    def _interpolate(self, s: str) -> str:
        """Replace {run_id} and other captured vars in strings."""
        if "{run_id}" in s:
            rid = self.captured.get("run_id", self.run_id or "MISSING_RUN_ID")
            s = s.replace("{run_id}", str(rid))
        for key, val in self.captured.items():
            s = s.replace(f"{{{key}}}", str(val))
        return s

    def _run_http_test(self, tc: Dict) -> Dict:
        """Execute a single HTTP-based test case."""
        test_id = tc["id"]
        method = tc.get("method", "GET").upper()
        service = tc.get("service", "nlq")
        path = self._interpolate(tc["path"])
        url = f"{self._service_url(service)}{path}"

        params = tc.get("params")
        body = tc.get("body")

        t0 = time.time()
        try:
            if method == "POST":
                r = self.client.post(url, json=body, params=params)
            else:
                r = self.client.get(url, params=params)
            latency_ms = (time.time() - t0) * 1000
        except Exception as exc:
            latency_ms = (time.time() - t0) * 1000
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round(latency_ms, 1),
                "error": f"HTTP {method} {url} failed: {type(exc).__name__}: {exc}",
                "assertions": [],
            }

        # Parse response
        try:
            data = r.json()
        except Exception:
            data = r.text

        # Capture values
        if "capture" in tc and isinstance(data, dict):
            for var_name, json_path in tc["capture"].items():
                val = _resolve_field(data, json_path)
                if val is not None:
                    self.captured[var_name] = val

        # Evaluate assertions
        assertion_results = []
        all_passed = True
        for assertion in tc.get("assertions", []):
            passed, detail = _evaluate_assertion(data, assertion, r.status_code, latency_ms)
            assertion_results.append({"passed": passed, "detail": detail})
            if not passed:
                all_passed = False

        return {
            "id": test_id,
            "name": tc.get("name", ""),
            "status": "PASS" if all_passed else "FAIL",
            "http_status": r.status_code,
            "latency_ms": round(latency_ms, 1),
            "url": url,
            "assertions": assertion_results,
        }

    def _run_freshness_gate(self, tc: Dict) -> Dict:
        """Verify DCL has ingested data consistent with the current Farm run.

        Queries DCL directly for a probe metric/entity/period and compares
        against the ground truth from the run captured by PI_001. If they
        don't match, DCL is serving stale data and all downstream
        reconciliation tests must fail (via depends_on).
        """
        test_id = tc["id"]
        probe_metric = tc["probe_metric"]
        probe_entity = tc["probe_entity"]
        probe_period = tc["probe_period"]
        tolerance = tc.get("tolerance_pct", 0.1)

        rid = self.captured.get("run_id", self.run_id)
        if not rid:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": 0,
                "error": "No run_id available — run PI_001 first or pass --run-id",
                "assertions": [],
            }

        t0 = time.time()

        # Step 1: Get expected value from Farm ground truth for THIS run
        gt_url = f"{self.urls['farm']}/api/business-data/ground-truth/{rid}"
        try:
            r = self.client.get(gt_url)
            gt_data = r.json()
        except Exception as exc:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": f"Failed to fetch ground truth from {gt_url}: {exc}",
                "assertions": [],
            }

        by_entity = gt_data.get("ground_truth_by_entity", {})
        entity_gt = by_entity.get(probe_entity, {})
        period_data = entity_gt.get(probe_period, {})
        metric_entry = period_data.get(probe_metric)

        if metric_entry is None:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": (
                    f"Probe metric '{probe_metric}' not found in ground truth "
                    f"for entity='{probe_entity}', period='{probe_period}', "
                    f"run_id='{rid}'"
                ),
                "assertions": [],
            }

        if isinstance(metric_entry, dict) and "value" in metric_entry:
            expected = metric_entry["value"]
        elif isinstance(metric_entry, (int, float)):
            expected = metric_entry
        else:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": f"Non-numeric ground truth for probe: {metric_entry}",
                "assertions": [],
            }

        # Step 2: Query DCL directly (NOT NLQ) for the same metric
        dcl_url = f"{self.urls['dcl']}/api/dcl/query"
        try:
            r = self.client.post(dcl_url, json={
                "metric": probe_metric,
                "entity_id": probe_entity,
                "time_range": {"start": probe_period, "end": probe_period},
            })
            dcl_data = r.json()
        except Exception as exc:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": f"DCL query failed: {exc}",
                "assertions": [],
            }

        data_list = dcl_data.get("data", [])
        if not data_list:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": (
                    f"DCL returned no data for {probe_metric}/{probe_entity}/{probe_period}. "
                    f"DCL may not have ingested run '{rid}' yet."
                ),
                "assertions": [],
            }

        actual = data_list[0].get("value")
        if actual is None:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": f"DCL data[0].value is null for probe metric",
                "assertions": [],
            }

        latency_ms = (time.time() - t0) * 1000

        # Step 3: Compare
        try:
            expected_f = float(expected)
            actual_f = float(actual)
        except (TypeError, ValueError):
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round(latency_ms, 1),
                "error": f"Non-numeric comparison: expected={expected}, actual={actual}",
                "assertions": [],
            }

        if expected_f != 0:
            pct_delta = abs(actual_f - expected_f) / abs(expected_f) * 100
        else:
            pct_delta = 0.0 if actual_f == 0 else 100.0

        passed = pct_delta <= tolerance
        detail = (
            f"Farm GT ({rid}): {probe_metric}/{probe_entity}/{probe_period} = {expected_f}, "
            f"DCL actual = {actual_f}, delta = {pct_delta:.2f}%, "
            f"tolerance = {tolerance}%"
        )

        if not passed:
            detail += (
                f" — DCL has STALE DATA. The value in DCL does not match "
                f"the ground truth from run '{rid}'. Reconciliation tests "
                f"will be skipped."
            )

        return {
            "id": test_id,
            "name": tc.get("name", ""),
            "status": "PASS" if passed else "FAIL",
            "latency_ms": round(latency_ms, 1),
            "assertions": [{"passed": passed, "detail": detail}],
        }

    def _run_reconciliation_test(self, tc: Dict) -> Dict:
        """Execute a ground truth reconciliation test."""
        test_id = tc["id"]
        entity_id = tc["entity_id"]
        metric = tc["metric"]
        period = tc["period"]
        tolerance = tc.get("tolerance_pct", 1.0)

        # Step 1: Get expected value from Farm ground truth
        rid = self.captured.get("run_id", self.run_id)
        if not rid:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": 0,
                "error": "No run_id available — run PI_001 first or pass --run-id",
                "assertions": [],
            }

        gt_url = f"{self.urls['farm']}/api/business-data/ground-truth/{rid}"
        t0 = time.time()
        try:
            r = self.client.get(gt_url)
            gt_data = r.json()
        except Exception as exc:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": f"Failed to fetch ground truth from {gt_url}: {exc}",
                "assertions": [],
            }

        # Extract expected value from v3.0 manifest
        by_entity = gt_data.get("ground_truth_by_entity", {})
        entity_gt = by_entity.get(entity_id, {})
        period_data = entity_gt.get(period, {})
        metric_entry = period_data.get(metric)

        if metric_entry is None:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": (
                    f"Metric '{metric}' not found in ground truth for "
                    f"entity='{entity_id}', period='{period}'. "
                    f"Available keys: {list(period_data.keys())[:20]}"
                ),
                "assertions": [],
            }

        if isinstance(metric_entry, dict) and "value" in metric_entry:
            expected = metric_entry["value"]
        elif isinstance(metric_entry, (int, float)):
            expected = metric_entry
        else:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": f"Non-numeric ground truth for {metric}: {metric_entry}",
                "assertions": [],
            }

        # Step 2: Query NLQ for actual value
        # Use the period format as-is from test_cases.yaml (e.g. "2025-Q1")
        # NLQ must handle both "2025-Q1" and "Q1 2025" identically.
        nlq_url = f"{self.urls['nlq']}/api/v1/query"
        try:
            r = self.client.post(nlq_url, json={
                "question": f"what is {metric} for {period}",
                "entity_id": entity_id,
                "data_mode": "live",
            })
            nlq_data = r.json()
            latency_ms = (time.time() - t0) * 1000
        except Exception as exc:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "error": f"NLQ query failed: {exc}",
                "assertions": [],
            }

        actual = nlq_data.get("value")
        if actual is None:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round(latency_ms, 1),
                "error": (
                    f"NLQ returned no value for {metric}/{entity_id}/{period}. "
                    f"data_source={nlq_data.get('data_source', 'unknown')}. "
                    f"Response keys: {list(nlq_data.keys())}"
                ),
                "assertions": [],
            }

        try:
            actual_f = float(actual)
            expected_f = float(expected)
        except (TypeError, ValueError) as exc:
            return {
                "id": test_id,
                "name": tc.get("name", ""),
                "status": "FAIL",
                "latency_ms": round(latency_ms, 1),
                "error": f"Non-numeric comparison: expected={expected}, actual={actual}",
                "assertions": [],
            }

        # Step 3: Compare within tolerance
        if expected_f != 0:
            pct_delta = abs(actual_f - expected_f) / abs(expected_f) * 100
        else:
            pct_delta = 0.0 if actual_f == 0 else 100.0

        passed = pct_delta <= tolerance
        detail = (
            f"expected={expected_f}, actual={actual_f}, "
            f"delta={abs(actual_f - expected_f):.4f}, pct={pct_delta:.2f}%, "
            f"tolerance={tolerance}%"
        )

        return {
            "id": test_id,
            "name": tc.get("name", ""),
            "status": "PASS" if passed else "FAIL",
            "latency_ms": round(latency_ms, 1),
            "assertions": [{"passed": passed, "detail": detail}],
        }

    def run(self, filter_id: Optional[str] = None) -> bool:
        """Run all tests (or a single test by ID). Returns True if all pass."""
        # Load test cases
        with open(TEST_CASES_FILE) as f:
            all_cases = yaml.safe_load(f)

        if filter_id:
            all_cases = [tc for tc in all_cases if tc["id"] == filter_id]
            if not all_cases:
                print(f"{_C.RED}[ERROR] Test '{filter_id}' not found{_C.RESET}")
                return False

        print(f"\n{_C.BOLD}{'=' * 72}{_C.RESET}")
        print(f"{_C.BOLD}{_C.CYAN}  PIPELINE INTEGRATION HARNESS — {len(all_cases)} tests{_C.RESET}")
        print(f"{_C.BOLD}{'=' * 72}{_C.RESET}")
        print(f"{_C.DIM}  Farm: {self.urls['farm']}{_C.RESET}")
        print(f"{_C.DIM}  DCL:  {self.urls['dcl']}{_C.RESET}")
        print(f"{_C.DIM}  NLQ:  {self.urls['nlq']}{_C.RESET}")
        if self.run_id:
            print(f"{_C.DIM}  Run:  {self.run_id}{_C.RESET}")
        print()

        for tc in all_cases:
            test_id = tc["id"]

            # Skip tests with unresolved dependencies
            depends = tc.get("depends_on")
            if depends:
                dep_result = next((r for r in self.results if r["id"] == depends), None)
                if dep_result and dep_result["status"] != "PASS":
                    result = {
                        "id": test_id,
                        "name": tc.get("name", ""),
                        "status": "SKIP",
                        "latency_ms": 0,
                        "error": f"Dependency {depends} did not pass",
                        "assertions": [],
                    }
                    self.results.append(result)
                    self._print_result(result)
                    continue

            # Dispatch to correct handler
            if tc.get("freshness_gate"):
                result = self._run_freshness_gate(tc)
            elif tc.get("reconciliation"):
                result = self._run_reconciliation_test(tc)
            else:
                result = self._run_http_test(tc)

            self.results.append(result)
            self._print_result(result)

        # Summary
        return self._print_summary()

    def _print_result(self, result: Dict) -> None:
        """Print a single test result."""
        status = result["status"]
        test_id = result["id"]
        name = result.get("name", "")
        latency = result.get("latency_ms", 0)

        if status == "PASS":
            icon = f"{_C.GREEN}[PASS]{_C.RESET}"
        elif status == "SKIP":
            icon = f"{_C.YELLOW}[SKIP]{_C.RESET}"
        else:
            icon = f"{_C.RED}[FAIL]{_C.RESET}"

        print(f"  {icon}  {test_id:8s}  {name:40s}  {latency:7.0f}ms")

        if status == "FAIL":
            error = result.get("error")
            if error:
                print(f"         {_C.RED}ERROR: {error}{_C.RESET}")
            for a in result.get("assertions", []):
                if not a["passed"]:
                    print(f"         {_C.RED}ASSERT: {a['detail']}{_C.RESET}")
            url = result.get("url", "")
            if url:
                print(f"         {_C.DIM}URL: {url}{_C.RESET}")

        elif status == "PASS" and self.verbose:
            for a in result.get("assertions", []):
                print(f"         {_C.DIM}{a['detail']}{_C.RESET}")

    def _print_summary(self) -> bool:
        """Print summary. Returns True if all passed."""
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        skipped = sum(1 for r in self.results if r["status"] == "SKIP")
        total = len(self.results)
        total_ms = sum(r.get("latency_ms", 0) for r in self.results)

        print(f"\n{_C.BOLD}{'=' * 72}{_C.RESET}")
        color = _C.GREEN if failed == 0 else _C.RED
        print(
            f"  {color}{_C.BOLD}"
            f"PASSED: {passed}  FAILED: {failed}  SKIPPED: {skipped}  "
            f"TOTAL: {total}  TIME: {total_ms/1000:.1f}s"
            f"{_C.RESET}"
        )
        print(f"{_C.BOLD}{'=' * 72}{_C.RESET}\n")

        return failed == 0

    def close(self):
        self.client.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline Integration Test Harness (PI_001–PI_021 + PI_002B)",
    )
    parser.add_argument("--farm-url", default="http://localhost:8003")
    parser.add_argument("--dcl-url", default="http://localhost:8004")
    parser.add_argument("--nlq-url", default="http://localhost:8005")
    parser.add_argument("--run-id", default=None,
                        help="Farm run_id (or auto-captured from PI_001)")
    parser.add_argument("--test", default=None,
                        help="Run a single test by ID (e.g. PI_001)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show assertion details for passing tests")
    args = parser.parse_args()

    harness = PipelineHarness(
        farm_url=args.farm_url,
        dcl_url=args.dcl_url,
        nlq_url=args.nlq_url,
        run_id=args.run_id,
        verbose=args.verbose,
    )

    try:
        all_passed = harness.run(filter_id=args.test)
    finally:
        harness.close()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
