#!/usr/bin/env python3
"""
Demo E2E Regression Checker
============================
Compares current demo_e2e_results.json against demo_e2e_baseline.json.
Blocks if any locked test regressed.

Usage:
    python tests/demo_e2e_regression_check.py
"""

import json
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
RESULTS = TESTS_DIR / "demo_e2e_results.json"
BASELINE = TESTS_DIR / "demo_e2e_baseline.json"
LOCKS = TESTS_DIR / "demo_regression_locks.json"


def main():
    if not RESULTS.exists():
        print("ERROR: demo_e2e_results.json not found. Run the harness first.")
        sys.exit(1)
    if not BASELINE.exists():
        print("ERROR: demo_e2e_baseline.json not found.")
        sys.exit(1)
    if not LOCKS.exists():
        print("ERROR: demo_regression_locks.json not found.")
        sys.exit(1)

    with open(RESULTS) as f:
        results = {r["id"]: r for r in json.load(f)}
    with open(BASELINE) as f:
        baseline = {r["id"]: r for r in json.load(f)}
    with open(LOCKS) as f:
        locks = json.load(f)

    # Handle both formats: list of ints or list of dicts
    if locks and isinstance(locks[0], int):
        locked_ids = set(locks)
    else:
        locked_ids = {l["id"] for l in locks}

    regressions = []
    improvements = []
    new_passes = []

    for tid in locked_ids:
        current = results.get(tid)
        base = baseline.get(tid)
        if not current:
            regressions.append(f"  [{tid}] {lock['name']} — MISSING from results")
            continue
        if base and base["passed"] and not current["passed"]:
            failed_checks = {k: v["detail"] for k, v in current["checks"].items() if not v["passed"]}
            regressions.append(f"  [{tid}] {lock['name']} — REGRESSED: {failed_checks}")

    # Check for improvements (new passes not in baseline)
    for tid, current in results.items():
        base = baseline.get(tid)
        if current["passed"] and base and not base["passed"]:
            improvements.append(f"  [{tid}] {current['name']} — NEW PASS")

    current_passed = sum(1 for r in results.values() if r["passed"])
    baseline_passed = sum(1 for r in baseline.values() if r["passed"])

    print("=" * 60)
    print("DEMO REGRESSION CHECK")
    print("=" * 60)
    print(f"Baseline: {baseline_passed}/100")
    print(f"Current:  {current_passed}/100")
    print(f"Delta:    {current_passed - baseline_passed:+d}")
    print(f"Locked:   {len(locked_ids)} tests")
    print()

    if improvements:
        print(f"IMPROVEMENTS ({len(improvements)}):")
        for imp in improvements:
            print(imp)
        print()

    if regressions:
        print(f"REGRESSIONS ({len(regressions)}) — BLOCKING:")
        for reg in regressions:
            print(reg)
        print()
        print("RESULT: BLOCKED — locked test(s) regressed")
        sys.exit(1)
    else:
        print("RESULT: OK — no regressions in locked tests")
        sys.exit(0)


if __name__ == "__main__":
    main()
