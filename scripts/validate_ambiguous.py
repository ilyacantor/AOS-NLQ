#!/usr/bin/env python3
"""
Validate all 20 ambiguous questions against ground truth.
Outputs a side-by-side comparison table.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.nlq.core.ambiguity import detect_ambiguity
from src.nlq.api.routes import _handle_ambiguous_query_text
from src.nlq.knowledge.fact_base import FactBase


def load_ground_truth():
    """Load the ground truth questions."""
    with open("nlq_docs/nlq_ambiguous_questions.json") as f:
        return json.load(f)


def validate_all_questions():
    """Run all 20 questions and compare to ground truth."""
    # Load ground truth
    gt = load_ground_truth()
    questions = gt["questions"]

    # Load fact base with data
    fact_base = FactBase()
    fact_base.load("data/fact_base.json")

    results = []
    passed = 0
    failed = 0

    print("\n" + "=" * 120)
    print("AMBIGUOUS QUESTION VALIDATION - 20 QUESTIONS")
    print("=" * 120)
    print(f"{'ID':<4} {'Question':<35} {'Ground Truth':<40} {'Actual Answer':<40} {'Status':<8}")
    print("-" * 120)

    for q in questions:
        qid = q["id"]
        question = q["question"]
        ground_truth = q["ground_truth"]
        amb_type = q.get("ambiguity_type", "unknown")

        # Detect ambiguity
        ambiguity_type, candidates, clarification = detect_ambiguity(question)

        # Get response
        if ambiguity_type:
            response = _handle_ambiguous_query_text(
                question,
                ambiguity_type,
                candidates,
                clarification,
                fact_base,
            )
            actual = response.answer
        else:
            actual = "NOT DETECTED AS AMBIGUOUS"

        # Check if passes (key parts match)
        status = check_match(ground_truth, actual, amb_type)

        if status == "PASS":
            passed += 1
        else:
            failed += 1

        # Truncate for display
        gt_short = ground_truth[:38] + ".." if len(ground_truth) > 40 else ground_truth
        actual_short = actual[:38] + ".." if len(actual) > 40 else actual

        print(f"{qid:<4} {question:<35} {gt_short:<40} {actual_short:<40} {status:<8}")

        results.append({
            "id": qid,
            "question": question,
            "ground_truth": ground_truth,
            "actual": actual,
            "status": status,
            "ambiguity_type": amb_type,
        })

    print("-" * 120)
    print(f"\nRESULTS: {passed}/{len(questions)} PASSED ({passed/len(questions)*100:.0f}%)")
    print("=" * 120)

    # Show failed questions in detail
    if failed > 0:
        print("\n\nFAILED QUESTIONS - DETAIL:")
        print("-" * 80)
        for r in results:
            if r["status"] != "PASS":
                print(f"\nQ{r['id']}: {r['question']}")
                print(f"  Type: {r['ambiguity_type']}")
                print(f"  Ground Truth: {r['ground_truth']}")
                print(f"  Actual:       {r['actual']}")
                print(f"  Status:       {r['status']}")

    return results, passed, len(questions)


def check_match(ground_truth: str, actual: str, amb_type: str) -> str:
    """Check if actual answer matches ground truth (flexible matching)."""
    gt = ground_truth.lower()
    act = actual.lower()

    # Special case: NOT_APPLICABLE
    if amb_type == "not_applicable":
        if "not applicable" in act and "profitable" in act:
            return "PASS"
        return "FAIL"

    # Special case: Yes/No questions
    if gt.startswith("yes") and act.startswith("yes"):
        return "PASS"
    if gt.startswith("no") and act.startswith("no"):
        return "PASS"

    # Extract key values from ground truth
    import re

    # Check for dollar amounts
    gt_amounts = re.findall(r'\$[\d.]+m', gt, re.IGNORECASE)
    act_amounts = re.findall(r'\$[\d.]+m', act, re.IGNORECASE)

    # Check for percentages
    gt_pcts = re.findall(r'[\d.]+%', gt)
    act_pcts = re.findall(r'[\d.]+%', act)

    # For margin questions, check all three percentages present
    if "margin" in amb_type or ("gross" in gt and "operating" in gt and "net" in gt):
        if "gross" in act and "operating" in act and "net" in act:
            return "PASS"

    # For revenue/income questions, check values match
    if gt_amounts and act_amounts:
        # At least one amount should match
        for ga in gt_amounts:
            for aa in act_amounts:
                if abs(float(ga[1:-1]) - float(aa[1:-1])) < 1:  # Within $1M
                    return "PASS"

    # For percentage questions
    if gt_pcts and act_pcts:
        for gp in gt_pcts:
            for ap in act_pcts:
                if abs(float(gp[:-1]) - float(ap[:-1])) < 1:  # Within 1%
                    return "PASS"

    # Check for key terms
    key_terms = {
        "p&l": ["revenue", "cogs", "gross profit", "sg&a", "net income"],
        "comparison": ["vs", "versus", "+"],
        "summary": ["revenue", "net income", "yoy"],
        "shorthand": ["$"],
        "judgment_call": ["cogs", "sg&a", "%"],
        "implied_context": ["revenue", "$"],
        "context_dependent": ["q2", "revenue", "+"],
        "casual_language": ["$", "forecast", "revenue", "ar"],
        "incomplete": ["$", "revenue", "q4"],
        "broad_request": ["revenue", "cogs", "gross", "sg&a", "net"],
        "yes_no": ["yes", "no", "%", "growth"],
        "vague_metric": ["gross", "operating", "net", "revenue", "income"],
    }

    if amb_type in key_terms:
        matches = sum(1 for term in key_terms[amb_type] if term in act)
        if matches >= 2:
            return "PASS"

    # Generic check - significant overlap in content
    gt_words = set(gt.split())
    act_words = set(act.split())
    overlap = len(gt_words & act_words)
    if overlap >= 3:
        return "PASS"

    return "FAIL"


if __name__ == "__main__":
    results, passed, total = validate_all_questions()

    # Exit with error if not 100%
    if passed < total:
        sys.exit(1)
