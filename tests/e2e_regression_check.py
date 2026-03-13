#!/usr/bin/env python3
"""Compare baseline and current E2E results. Block commit if regressions found.

Usage:
    python tests/e2e_regression_check.py

Expects:
    tests/e2e_baseline.json  - snapshot taken BEFORE code changes
    tests/e2e_results.json   - snapshot taken AFTER code changes
    tests/regression_locks.json - tests that must never regress

Exit codes:
    0 - CLEAR (no regressions, all locks hold)
    1 - BLOCKED (regressions or locked test failures detected)
"""

import json
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASELINE_PATH = os.path.join(SCRIPT_DIR, "e2e_baseline.json")
CURRENT_PATH = os.path.join(SCRIPT_DIR, "e2e_results.json")
LOCKS_PATH = os.path.join(SCRIPT_DIR, "regression_locks.json")


def load_json(path, encoding="utf-8"):
    """Load a JSON file with explicit encoding to avoid cp1252 issues on Windows."""
    with open(path, encoding=encoding) as f:
        return json.load(f)


def main():
    # ── Load files ──────────────────────────────────────────────────────
    if not os.path.exists(BASELINE_PATH):
        print(f"ERROR: Baseline file not found at {BASELINE_PATH}")
        print("Run the E2E harness and copy results to e2e_baseline.json first.")
        sys.exit(1)

    if not os.path.exists(CURRENT_PATH):
        print(f"ERROR: Current results file not found at {CURRENT_PATH}")
        print("Run the E2E harness first: python tests/e2e_nlq_validation.py")
        sys.exit(1)

    baseline = {r["id"]: r for r in load_json(BASELINE_PATH)}
    current = {r["id"]: r for r in load_json(CURRENT_PATH)}

    # Load regression locks
    try:
        locks = load_json(LOCKS_PATH)
    except FileNotFoundError:
        locks = []

    # ── Compare ─────────────────────────────────────────────────────────
    regressions = []
    improvements = []
    locked_failures = []

    for test_id in baseline:
        b = baseline[test_id]
        c = current.get(test_id)
        if not c:
            regressions.append(
                f"Test {test_id} ({b['name']}): MISSING from current run"
            )
            continue

        was_pass = b["passed"]
        now_pass = c["passed"]

        if was_pass and not now_pass:
            regressions.append(
                f"Test {test_id} ({b['name']}): REGRESSED (was PASS, now FAIL)"
            )

        if not was_pass and now_pass:
            improvements.append(
                f"Test {test_id} ({b['name']}): IMPROVED (was FAIL, now PASS)"
            )

    # Check locked tests — these must ALWAYS pass regardless of baseline
    for lock in locks:
        test_id = lock["id"]
        c = current.get(test_id)
        if c and not c["passed"]:
            locked_failures.append(
                f"LOCKED Test {test_id} ({lock['name']}): FAILED "
                f"-- this test was previously fixed and must not regress. "
                f"Lock set on {lock['locked_date']}."
            )

    # ── Report ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("REGRESSION CHECK REPORT")
    print("=" * 60)

    # Summary counts
    baseline_pass = sum(1 for r in baseline.values() if r["passed"])
    current_pass = sum(1 for r in current.values() if r["passed"])
    print(f"\nBaseline: {baseline_pass}/{len(baseline)} passing")
    print(f"Current:  {current_pass}/{len(current)} passing")
    print(f"Locked:   {len(locks)} tests")

    if improvements:
        print(f"\nIMPROVEMENTS ({len(improvements)}):")
        for i in improvements:
            print(f"  + {i}")

    if regressions:
        print(f"\nREGRESSIONS ({len(regressions)}):")
        for r in regressions:
            print(f"  - {r}")

    if locked_failures:
        print(f"\nLOCKED TEST FAILURES ({len(locked_failures)}):")
        for lf in locked_failures:
            print(f"  !! {lf}")

    # ── Verdict ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    if locked_failures:
        print("VERDICT: BLOCKED -- Locked tests have regressed. REVERT CHANGES.")
        print(f"  {len(locked_failures)} locked test(s) failed.")
        if regressions:
            print(f"  {len(regressions)} additional regression(s) detected.")
        sys.exit(1)
    elif regressions:
        print(f"VERDICT: WARNING -- {len(regressions)} regression(s) detected.")
        print("Review regressions. If acceptable tradeoff, proceed. Otherwise revert.")
        sys.exit(1)
    else:
        print(
            f"VERDICT: CLEAR -- {len(improvements)} improvement(s), 0 regressions."
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
