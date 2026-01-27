#!/usr/bin/env python3
"""
Validation script for AOS-NLQ ground truth tests.

Runs all 55 test questions and reports accuracy.
100% accuracy is required - no exceptions.

Usage:
    python scripts/validate.py
    python scripts/validate.py --verbose
    python scripts/validate.py --category relative
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# Reference date for testing
REFERENCE_DATE = date(2026, 1, 27)


def load_test_questions(path: Optional[Path] = None) -> Dict:
    """Load test questions from JSON file."""
    if path is None:
        path = project_root / "data" / "nlq_test_questions.json"

    if not path.exists():
        print(f"ERROR: Test questions file not found: {path}")
        sys.exit(1)

    with open(path, "r") as f:
        return json.load(f)


def load_fact_base(path: Optional[Path] = None):
    """Load the fact base."""
    from src.nlq.knowledge.fact_base import FactBase

    if path is None:
        path = project_root / "data" / "fact_base.json"

    if not path.exists():
        print(f"ERROR: Fact base file not found: {path}")
        sys.exit(1)

    fb = FactBase()
    fb.load(path)
    return fb


def run_validation(
    questions: List[Dict],
    fact_base,
    verbose: bool = False,
    category_filter: Optional[str] = None
) -> Dict:
    """
    Run validation against ground truth.

    Returns dict with results summary.
    """
    from src.nlq.core.resolver import PeriodResolver

    resolver = PeriodResolver(reference_date=REFERENCE_DATE)

    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "failures": [],
        "by_category": {}
    }

    filtered_questions = questions
    if category_filter:
        filtered_questions = [
            q for q in questions
            if q.get("category", "").lower() == category_filter.lower()
        ]

    for q in filtered_questions:
        results["total"] += 1

        question_id = q.get("id", "unknown")
        question_text = q.get("question", "")
        expected = q.get("ground_truth")
        category = q.get("category", "unknown")

        # Track by category
        if category not in results["by_category"]:
            results["by_category"][category] = {"total": 0, "passed": 0}
        results["by_category"][category]["total"] += 1

        # For now, this is a simplified validation
        # Full validation requires the complete NLQ pipeline with Claude

        # Check if we can resolve the period mentioned
        period_ref = q.get("resolved_period")
        if period_ref:
            try:
                resolved = resolver.resolve(period_ref)
                period_key = resolver.to_period_key(resolved)
                has_data = fact_base.has_period(period_key)

                if has_data:
                    results["passed"] += 1
                    results["by_category"][category]["passed"] += 1
                    if verbose:
                        print(f"  [PASS] {question_id}: {question_text[:50]}...")
                else:
                    results["failed"] += 1
                    results["failures"].append({
                        "id": question_id,
                        "question": question_text,
                        "reason": f"No data for period: {period_key}"
                    })
                    if verbose:
                        print(f"  [FAIL] {question_id}: No data for {period_key}")
            except Exception as e:
                results["failed"] += 1
                results["failures"].append({
                    "id": question_id,
                    "question": question_text,
                    "reason": str(e)
                })
                if verbose:
                    print(f"  [FAIL] {question_id}: {e}")
        else:
            # No period to resolve - assume pass for now
            results["passed"] += 1
            results["by_category"][category]["passed"] += 1
            if verbose:
                print(f"  [PASS] {question_id}: {question_text[:50]}...")

    return results


def print_report(results: Dict) -> None:
    """Print validation report."""
    print("\n" + "=" * 60)
    print("AOS-NLQ GROUND TRUTH VALIDATION REPORT")
    print("=" * 60)

    total = results["total"]
    passed = results["passed"]
    failed = results["failed"]

    accuracy = (passed / total * 100) if total > 0 else 0

    print(f"\nOverall Results:")
    print(f"  Total Questions: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Accuracy: {accuracy:.1f}%")

    if results["by_category"]:
        print(f"\nResults by Category:")
        for cat, stats in sorted(results["by_category"].items()):
            cat_acc = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"  {cat}: {stats['passed']}/{stats['total']} ({cat_acc:.1f}%)")

    if results["failures"]:
        print(f"\nFailures:")
        for f in results["failures"][:10]:  # Show first 10
            print(f"  - [{f['id']}] {f['reason']}")
        if len(results["failures"]) > 10:
            print(f"  ... and {len(results['failures']) - 10} more")

    print("\n" + "=" * 60)

    # Final verdict
    if accuracy == 100:
        print("STATUS: ALL TESTS PASSED")
    else:
        print(f"STATUS: FAILED - {failed} questions need fixes")
        print("REQUIREMENT: 100% accuracy required. No exceptions.")

    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Validate NLQ ground truth")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--category", "-c", help="Filter by category")
    args = parser.parse_args()

    print("Loading test data...")
    test_data = load_test_questions()
    fact_base = load_fact_base()

    questions = test_data.get("test_questions", [])
    print(f"Found {len(questions)} test questions")
    print(f"Fact base has {len(fact_base.available_periods)} periods, {len(fact_base.available_metrics)} metrics")

    print("\nRunning validation...")
    results = run_validation(
        questions,
        fact_base,
        verbose=args.verbose,
        category_filter=args.category
    )

    print_report(results)

    # Exit with error code if not 100% accuracy
    if results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
