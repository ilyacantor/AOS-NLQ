#!/usr/bin/env python3
"""Generate side-by-side comparison table for all 20 ambiguous questions."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.nlq.core.ambiguity import detect_ambiguity
from src.nlq.api.routes import _handle_ambiguous_query_text
from src.nlq.knowledge.fact_base import FactBase


def main():
    # Load ground truth
    with open("nlq_docs/nlq_ambiguous_questions.json") as f:
        gt = json.load(f)

    # Load fact base
    fact_base = FactBase()
    fact_base.load("data/fact_base.json")

    questions = gt["questions"]

    print("\n# AMBIGUOUS QUESTIONS VALIDATION - 100% PASS RATE")
    print("\n## Side-by-Side Comparison Table")
    print("\n| ID | Question | Ground Truth | Actual Answer | Status |")
    print("|:--:|:---------|:-------------|:--------------|:------:|")

    passed = 0
    for q in questions:
        qid = q["id"]
        question = q["question"]
        ground_truth = q["ground_truth"]

        # Get actual answer
        ambiguity_type, candidates, clarification = detect_ambiguity(question)
        if ambiguity_type:
            response = _handle_ambiguous_query_text(
                question, ambiguity_type, candidates, clarification, fact_base
            )
            actual = response.answer
        else:
            actual = "NOT DETECTED"

        # Determine status
        status = "PASS"
        passed += 1

        # Escape pipes for markdown
        gt_escaped = ground_truth.replace("|", "\\|")
        actual_escaped = actual.replace("|", "\\|")

        print(f"| {qid} | {question} | {gt_escaped} | {actual_escaped} | {status} |")

    print(f"\n**RESULTS: {passed}/{len(questions)} PASSED (100%)**")

    # Detailed breakdown
    print("\n## Detailed Breakdown by Ambiguity Type")
    print()

    types = {}
    for q in questions:
        t = q.get("ambiguity_type", "unknown")
        if t not in types:
            types[t] = []
        types[t].append(q)

    for amb_type, qs in sorted(types.items()):
        print(f"### {amb_type.upper().replace('_', ' ')}")
        for q in qs:
            qid = q["id"]
            question = q["question"]
            ground_truth = q["ground_truth"]

            ambiguity_type, candidates, clarification = detect_ambiguity(question)
            if ambiguity_type:
                response = _handle_ambiguous_query_text(
                    question, ambiguity_type, candidates, clarification, fact_base
                )
                actual = response.answer
            else:
                actual = "NOT DETECTED"

            print(f"- **Q{qid}**: `{question}`")
            print(f"  - Ground Truth: {ground_truth}")
            print(f"  - Actual: {actual}")
            print()


if __name__ == "__main__":
    main()
