#!/usr/bin/env python3
"""
NLQ Regression Test Harness

Run all tests:     python run_tests.py --base-url http://localhost:8000
Run by tag:        python run_tests.py --base-url http://localhost:8000 --tag galaxy
Run single test:   python run_tests.py --base-url http://localhost:8000 --id BUG-001
Verbose output:    python run_tests.py --base-url http://localhost:8000 -v
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


# ── Colors ──────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


# ── Load tests ──────────────────────────────────────────────────────

def load_tests(path: str) -> list:
    with open(path) as f:
        data = json.load(f)
    return data["test_cases"]


# ── HTTP call ───────────────────────────────────────────────────────

def post_json(url: str, payload: dict, timeout: int = 30) -> tuple:
    """Returns (status_code, response_dict, error_string)."""
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read()), None
    except HTTPError as e:
        try:
            resp_body = json.loads(e.read())
        except Exception:
            resp_body = {}
        return e.code, resp_body, str(e)
    except URLError as e:
        return 0, {}, f"Connection failed: {e.reason}"
    except Exception as e:
        return 0, {}, str(e)


# ── Deep search for a field value anywhere in a nested response ─────

def deep_search(obj, key: str):
    """Recursively search for a key in nested dicts/lists. Returns all found values."""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                results.append(v)
            results.extend(deep_search(v, key))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(deep_search(item, key))
    return results


def flatten_text(obj) -> str:
    """Flatten entire response to lowercase text for contains/not-contains checks."""
    if isinstance(obj, str):
        return obj.lower()
    if isinstance(obj, dict):
        return " ".join(flatten_text(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(flatten_text(item) for item in obj)
    return str(obj).lower()


# ── Assertion engine ────────────────────────────────────────────────

def check_expectations(expect: dict, status: int, body: dict) -> list:
    """Returns list of failure strings. Empty list = pass."""
    failures = []
    flat = flatten_text(body)

    # Status code
    if "status" in expect and status != expect["status"]:
        failures.append(f"Expected status {expect['status']}, got {status}")

    # Response text must contain
    for phrase in expect.get("response_must_contain", []):
        if phrase.lower() not in flat:
            failures.append(f"Response missing expected text: '{phrase}'")

    # Response text must NOT contain
    for phrase in expect.get("response_must_not_contain", []):
        if phrase.lower() in flat:
            failures.append(f"Response contains forbidden text: '{phrase}'")

    # Metric identity checks — search for metric/metric_id/metric_name fields
    if "metric_must_be" in expect:
        target = expect["metric_must_be"].lower()
        found_metrics = []
        for key in ["metric", "metric_id", "metric_name", "resolved_metric"]:
            found_metrics.extend(deep_search(body, key))
        found_lower = [str(m).lower() for m in found_metrics]
        if found_lower and target not in found_lower:
            failures.append(f"Expected metric '{target}', found: {found_metrics}")
        elif not found_lower:
            # Fall back to flat text check
            if target not in flat:
                failures.append(f"Expected metric '{target}' not found anywhere in response")

    if "metric_must_not_be" in expect:
        bad = expect["metric_must_not_be"].lower()
        found_metrics = []
        for key in ["metric", "metric_id", "metric_name", "resolved_metric"]:
            found_metrics.extend(deep_search(body, key))
        found_lower = [str(m).lower() for m in found_metrics]
        if bad in found_lower:
            failures.append(f"Metric resolved to forbidden value: '{bad}'")

    # Field checks (intent type, etc.)
    for field, allowed_values in expect.get("field_checks", {}).items():
        if field.endswith("_in"):
            actual_field = field[:-3]  # strip _in suffix
            found = deep_search(body, actual_field)
            found_lower = [str(v).lower() for v in found]
            allowed_lower = [str(v).lower() for v in allowed_values]
            if not any(f in allowed_lower for f in found_lower):
                failures.append(f"Field '{actual_field}' expected one of {allowed_values}, found: {found or '(not present)'}")

    return failures


# ── Runner ──────────────────────────────────────────────────────────

def run_tests(base_url: str, tests: list, verbose: bool = False) -> tuple:
    passed = 0
    failed = 0
    errors = 0
    skipped = 0
    results = []
    # Store responses by test ID for dependency chaining (e.g., DR tests need dashboard_id from DB tests)
    responses_by_id = {}

    print(f"\n{BOLD}NLQ Regression Tests{RESET}")
    print(f"Target: {base_url}")
    print(f"Cases:  {len(tests)}")
    print("─" * 72)

    for tc in tests:
        test_id = tc["id"]
        desc = tc["description"]

        # Skip tests marked as skip
        if tc.get("skip"):
            reason = tc.get("skip_reason", "")
            print(f"  {YELLOW}SKIP{RESET} {test_id}: {desc} {DIM}({reason}){RESET}")
            skipped += 1
            results.append({"id": test_id, "result": "SKIP", "reason": reason})
            continue

        url = base_url.rstrip("/") + tc["endpoint"]
        payload = dict(tc["payload"])  # copy so we can mutate
        expect = tc["expect"]

        # Dependency chaining: inject dashboard_id from a prior test's response
        dep_id = tc.get("depends_on")
        if dep_id:
            dep_resp = responses_by_id.get(dep_id)
            if not dep_resp:
                print(f"  {YELLOW}SKIP{RESET} {test_id}: {desc} {DIM}(dependency {dep_id} not available){RESET}")
                skipped += 1
                results.append({"id": test_id, "result": "SKIP", "reason": f"dependency {dep_id} not available"})
                continue
            # Extract dashboard_id from dependency response
            dash = dep_resp.get("dashboard") or {}
            dash_id = dash.get("id") if isinstance(dash, dict) else None
            if not dash_id:
                print(f"  {YELLOW}SKIP{RESET} {test_id}: {desc} {DIM}(no dashboard_id in {dep_id} response){RESET}")
                skipped += 1
                results.append({"id": test_id, "result": "SKIP", "reason": f"no dashboard_id from {dep_id}"})
                continue
            # Replace placeholder or set dashboard_id
            if payload.get("dashboard_id") == "__FROM_DEPENDENCY__":
                payload["dashboard_id"] = dash_id
            elif "dashboard_id" not in payload:
                payload["dashboard_id"] = dash_id

        t0 = time.time()
        status, body, err = post_json(url, payload)
        elapsed = time.time() - t0

        # Store response for potential dependents
        responses_by_id[test_id] = body

        if err and status == 0:
            # Connection error
            print(f"  {RED}ERR {RESET} {test_id}: {desc}")
            print(f"       {DIM}{err}{RESET}")
            errors += 1
            results.append({"id": test_id, "result": "ERROR", "error": err})
            continue

        failures = check_expectations(expect, status, body)

        if not failures:
            print(f"  {GREEN}PASS{RESET} {test_id}: {desc} {DIM}({elapsed:.1f}s){RESET}")
            passed += 1
            results.append({"id": test_id, "result": "PASS", "elapsed": round(elapsed, 2)})
        else:
            print(f"  {RED}FAIL{RESET} {test_id}: {desc} {DIM}({elapsed:.1f}s){RESET}")
            for f in failures:
                print(f"       {RED}✗{RESET} {f}")
            failed += 1
            results.append({"id": test_id, "result": "FAIL", "failures": failures, "elapsed": round(elapsed, 2)})

        if verbose:
            print(f"       {DIM}POST {tc['endpoint']} → {status}{RESET}")
            # Truncate body for readability
            body_str = json.dumps(body, indent=2)
            if len(body_str) > 500:
                body_str = body_str[:500] + "\n       ..."
            for line in body_str.split("\n"):
                print(f"       {DIM}{line}{RESET}")

    # Summary
    print("─" * 72)
    parts = []
    if passed:
        parts.append(f"{GREEN}{passed} passed{RESET}")
    if failed:
        parts.append(f"{RED}{failed} failed{RESET}")
    if skipped:
        parts.append(f"{YELLOW}{skipped} skipped{RESET}")
    if errors:
        parts.append(f"{YELLOW}{errors} errors{RESET}")
    print(f"  {', '.join(parts)}  |  {passed + failed + skipped + errors} total")
    print()

    return passed, failed, errors, results


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NLQ Regression Test Harness")
    parser.add_argument("--base-url", required=True, help="NLQ server base URL (e.g. http://localhost:8000)")
    parser.add_argument("--tests", default=str(Path(__file__).parent / "tests.json"), help="Path to tests.json")
    parser.add_argument("--tag", help="Only run tests with this tag")
    parser.add_argument("--id", help="Only run test with this ID")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show full response bodies")
    parser.add_argument("--json-out", help="Write results to JSON file")
    args = parser.parse_args()

    all_tests = [t for t in load_tests(args.tests) if "id" in t]

    # Filter
    if args.id:
        tests = [t for t in all_tests if t["id"] == args.id]
        if not tests:
            print(f"No test found with id: {args.id}")
            sys.exit(1)
    elif args.tag:
        tests = [t for t in all_tests if args.tag in t.get("tags", [])]
        if not tests:
            print(f"No tests found with tag: {args.tag}")
            sys.exit(1)
    else:
        tests = all_tests

    passed, failed, errors, results = run_tests(args.base_url, tests, verbose=args.verbose)

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "base_url": args.base_url,
                "summary": {"passed": passed, "failed": failed, "errors": errors},
                "results": results
            }, f, indent=2)
        print(f"Results written to {args.json_out}")

    sys.exit(1 if (failed or errors) else 0)


if __name__ == "__main__":
    main()
